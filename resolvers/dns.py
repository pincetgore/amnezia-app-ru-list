"""
Резолвер DNS доменов.

Получает IPv4-адреса для списка доменных имен через запросы DNS A-записей.
Каждый полученный валидный IP-адрес возвращается как сеть /32. Это дополняет
получение префиксов на основе ASN для сервисов, которые не имеют выделенной ASN
или используют общий/облачный хостинг.
"""

import concurrent.futures
import logging
import threading
from ipaddress import IPv4Network

import dns.exception
import dns.resolver

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def _is_valid_ip(net: IPv4Network) -> bool:
    """Проверяет валидность полученного через DNS IPv4-адреса.

    Исключает:
    - Неопределенные адреса (0.0.0.0/8, 0.0.0.0/32)
    - Loopback адреса (127.0.0.0/8, 127.0.0.1)
    - Multicast / Class E (>= 224.0.0.0/4)
    """
    if net.is_unspecified or net.is_loopback or net.is_multicast:
        return False
    return not str(net.network_address).startswith("0.")


def _to_ascii_domain(domain: str) -> str:
    """Нормализует IDN (кириллические домены в punycode) для DNS-резолвинга."""
    clean_domain = domain.strip()
    try:
        return clean_domain.encode("idna").decode("ascii")
    except Exception:
        return clean_domain


def _get_worker_resolver(base_resolver: dns.resolver.Resolver) -> dns.resolver.Resolver:
    """Возвращает локальный для потока Resolver во избежание race conditions."""
    res = getattr(_thread_local, "resolver", None)
    if res is None:
        try:
            res = dns.resolver.Resolver(configure=False)
        except Exception:
            res = base_resolver
        _thread_local.resolver = res

    if res is not base_resolver:
        res.nameservers = list(base_resolver.nameservers)
        res.timeout = base_resolver.timeout
        res.lifetime = base_resolver.lifetime
    return res


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> tuple[list[IPv4Network], str | None]:
    """Вспомогательная функция для получения IP-адресов одного домена."""
    networks = []
    warning = None
    ascii_domain = _to_ascii_domain(domain)
    try:
        answers = resolver.resolve(ascii_domain, "A")
        for rdata in answers:
            ip = str(rdata)
            try:
                net = IPv4Network(f"{ip}/32", strict=False)
                if _is_valid_ip(net):
                    networks.append(net)
                    logger.debug("DNS %s -> %s", domain, ip)
                else:
                    logger.warning("Ignoring invalid/sinkholed IP %s for %s", ip, domain)
            except ValueError:
                logger.warning("Invalid IP %s returned for %s", ip, domain)
        logger.debug("DNS %s: resolved %d valid A records", domain, len(networks))
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


def _worker_resolve(domain: str, base_resolver: dns.resolver.Resolver) -> tuple[list[IPv4Network], str | None]:
    """Воркер с получением потокобезопасного экземпляра Resolver."""
    resolver = _get_worker_resolver(base_resolver)
    return _resolve_single_domain(domain, resolver)


def resolve_domains(
    domains: list[str],
    timeout: int = 10,
    max_workers: int = 20,
    nameservers: list[str] | None = None,
) -> tuple[list[IPv4Network], list[str]]:
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
