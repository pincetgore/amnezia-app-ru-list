"""
Резолвер DNS доменов.

Получает IPv4-адреса для списка доменных имен через запросы DNS A-записей.
Каждый полученный IP-адрес возвращается как сеть /32. Это дополняет
получение префиксов на основе ASN для сервисов, которые не имеют выделенной ASN
или используют общий/облачный хостинг.
"""

import logging
import concurrent.futures
from ipaddress import IPv4Network

import dns.resolver

logger = logging.getLogger(__name__)


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> tuple[list[IPv4Network], str | None]:
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
        logger.debug("DNS domain does not exist (NXDOMAIN) for %s", domain)
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


def resolve_domains(domains: list[str], timeout: int = 10, max_workers: int = 20) -> tuple[list[IPv4Network], list[str]]:
    """Получает IPv4-сети /32 для списка доменов и возвращает предупреждения.

    Ошибки для отдельных доменов логируются и пропускаются — функция
    возвращает кортеж (сети, домены_с_предупреждениями) без вызова исключений.
    Запросы выполняются параллельно с использованием пула потоков.
    """
    resolver = dns.resolver.Resolver()
    # Используем Яндекс.DNS первыми, так как многие RU-домены (ВТБ, VK, X5) 
    # блокируют запросы от зарубежных DNS (Google/Cloudflare) для защиты от DDoS
    resolver.nameservers = ['77.88.8.8', '77.88.8.1', '8.8.8.8', '1.1.1.1']
    
    # Таймаут на один сервер делаем пропорциональным количеству серверов (2.5 сек)
    resolver.timeout = timeout / len(resolver.nameservers)
    # Общее время на все попытки резолвинга
    resolver.lifetime = timeout

    networks = []
    warnings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_resolve_single_domain, domain, resolver) for domain in domains]
        
        for future in concurrent.futures.as_completed(futures):
            nets, warn = future.result()
            networks.extend(nets)
            if warn:
                warnings.append(warn)

    return networks, warnings
