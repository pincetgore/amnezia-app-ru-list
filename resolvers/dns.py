"""
Резолвер DNS доменов.

Получает IPv4-адреса для списка доменных имен через запросы DNS A-записей.
Каждый полученный IP-адрес возвращается как сеть /32. Это дополняет
получение префиксов на основе ASN для сервисов, которые не имеют выделенной ASN
или используют общий/облачный хостинг.
"""

import logging
import concurrent.futures
import ipaddress
from ipaddress import IPv4Network
from typing import List, Optional, Tuple

import dns.resolver

logger = logging.getLogger(__name__)


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> Tuple[List[IPv4Network], Optional[str]]:
    """Вспомогательная функция для получения IP-адресов одного домена."""
    networks = []
    warning = None
    try:
        answers = resolver.resolve(domain, "A")
        for rdata in answers:
            ip = str(rdata)
            net = IPv4Network(f"{ip}/32", strict=False)
            networks.append(net)
            logger.debug("DNS %s -> %s", domain, ip)
        logger.info("DNS %s: resolved %d A records", domain, len(answers))
    except dns.resolver.NXDOMAIN:
        logger.warning("DNS domain does not exist (NXDOMAIN) for %s", domain)
        warning = domain
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers) as e:
        logger.warning("DNS resolution failed for %s: %s", domain, e)
        warning = domain
    except dns.exception.Timeout:
        logger.warning("DNS timeout for %s", domain)
        warning = domain
    except Exception as e:
        logger.warning("DNS error for %s: %s", domain, e)
        warning = domain
    return networks, warning


def resolve_domains(
    domains: List[str],
    timeout: int = 10,
    max_workers: int = 20,
    nameservers: Optional[List[str]] = None,
) -> Tuple[List[IPv4Network], List[str]]:
    """Получает IPv4-сети /32 для списка доменов и возвращает предупреждения.

    Параметры:
    - domains: список доменов для резолвинга
    - timeout: таймаут в секундах
    - max_workers: макс количество параллельных воркеров
    - nameservers: список DNS серверов (если None, использует Яндекс.DNS)

    Ошибки для отдельных доменов логируются и пропускаются — функция
    возвращает кортеж (сети, домены_с_предупреждениями) без вызова исключений.
    Запросы выполняются параллельно с использованием пула потоков.
    """
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("DNS timeout must be a positive number")
    if not isinstance(max_workers, int) or isinstance(max_workers, bool) or max_workers < 1:
        raise ValueError("max_workers must be an integer of at least 1")

    configured_nameservers = (
        ['77.88.8.8', '77.88.8.1', '8.8.8.8', '1.1.1.1']
        if nameservers is None else list(nameservers)
    )
    if not configured_nameservers:
        raise ValueError("At least one DNS nameserver is required")
    for nameserver in configured_nameservers:
        try:
            ipaddress.ip_address(nameserver)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid DNS nameserver: {nameserver!r}") from e

    def create_resolver() -> dns.resolver.Resolver:
        # Resolver создаётся на каждый worker: это не зависит от thread-safety
        # конкретной версии dnspython.
        worker_resolver = dns.resolver.Resolver()
        worker_resolver.nameservers = configured_nameservers
        worker_resolver.timeout = timeout / len(configured_nameservers)
        worker_resolver.lifetime = timeout
        return worker_resolver

    # Создаём и настраиваем resolver здесь также, чтобы конфигурация проверялась
    # до запуска пула потоков.
    create_resolver()

    networks = []
    warnings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_resolve_single_domain, domain, create_resolver())
            for domain in domains
        ]
        future_domains = dict(zip(futures, domains))

        for future in concurrent.futures.as_completed(futures):
            try:
                nets, warn = future.result()
            except Exception:
                domain = future_domains[future]
                logger.exception("Unexpected DNS worker failure for %s", domain)
                warnings.append(domain)
                continue
            networks.extend(nets)
            if warn:
                warnings.append(warn)

    return networks, warnings
