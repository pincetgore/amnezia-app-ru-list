"""
Резолвер DNS доменов.

Получает IPv4-адреса для списка доменных имен через запросы DNS A-записей.
Каждый полученный IP-адрес возвращается как сеть /32. Это дополняет
получение префиксов на основе ASN для сервисов, которые не имеют выделенной ASN
или используют общий/облачный хостинг.
"""

import concurrent.futures
import logging
import threading
from ipaddress import IPv4Network
from typing import List, Optional, Tuple

import dns.resolver

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def _to_ascii_domain(domain: str) -> str:
    """Нормализует IDN (кириллические домены в punycode) для DNS-резолвинга."""
    try:
        return domain.encode("idna").decode("ascii")
    except Exception:
        return domain


def _get_worker_resolver(base_resolver: dns.resolver.Resolver) -> dns.resolver.Resolver:
    """Возвращает локальный для потока Resolver во избежание race conditions."""
    res = getattr(_thread_local, "resolver", None)
    if res is None:
        try:
            res = dns.resolver.Resolver(configure=False)
            res.nameservers = list(base_resolver.nameservers)
            res.timeout = base_resolver.timeout
            res.lifetime = base_resolver.lifetime
        except Exception:
            res = base_resolver
        _thread_local.resolver = res
    return res


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> Tuple[List[IPv4Network], Optional[str]]:
    """Вспомогательная функция для получения IP-адресов одного домена."""
    networks = []
    warning = None
    ascii_domain = _to_ascii_domain(domain)
    try:
        answers = resolver.resolve(ascii_domain, "A")
        for rdata in answers:
            ip = str(rdata)
            net = IPv4Network(f"{ip}/32", strict=False)
            networks.append(net)
            logger.debug("DNS %s -> %s", domain, ip)
        logger.debug("DNS %s: resolved %d A records", domain, len(answers))
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


def _worker_resolve(domain: str, base_resolver: dns.resolver.Resolver) -> Tuple[List[IPv4Network], Optional[str]]:
    """Воркер с получением потокобезопасного экземпляра Resolver."""
    resolver = _get_worker_resolver(base_resolver)
    return _resolve_single_domain(domain, resolver)


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
    if timeout <= 0:
        raise ValueError("DNS timeout must be positive")
    if max_workers <= 0:
        raise ValueError("DNS max_workers must be positive")
    if nameservers is not None and not nameservers:
        raise ValueError("At least one DNS nameserver must be configured")

    target_nameservers = nameservers if nameservers is not None else ["77.88.8.8", "77.88.8.1", "8.8.8.8", "1.1.1.1"]
    if not target_nameservers:
        raise ValueError("At least one DNS nameserver must be configured")

    resolver = dns.resolver.Resolver(configure=False)
    # Используем Яндекс.DNS первыми, так как многие RU-домены (ВТБ, VK, X5)
    # блокируют запросы от зарубежных DNS (Google/Cloudflare) для защиты от DDoS.
    resolver.nameservers = target_nameservers

    # Таймаут на один сервер делаем пропорциональным, но не менее 1.0 с
    resolver.timeout = max(1.0, timeout / len(resolver.nameservers))
    # Общее время на все попытки резолвинга
    resolver.lifetime = timeout

    networks = []
    warnings = []
    # Оптимизация: не создаем 20 потоков, если доменов всего 1-2
    effective_workers = min(max_workers, len(domains)) if domains else max_workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = [executor.submit(_worker_resolve, domain, resolver) for domain in domains]
        
        for future in concurrent.futures.as_completed(futures):
            nets, warn = future.result()
            networks.extend(nets)
            if warn:
                warnings.append(warn)

    return networks, warnings
