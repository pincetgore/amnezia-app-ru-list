"""
Резолвер DNS доменов.

Получает IPv4-адреса для списка доменных имен через запросы DNS A-записей.
Каждый полученный валидный IP-адрес возвращается как сеть /32. Это дополняет
получение префиксов на основе ASN для сервисов, которые не имеют выделенной ASN
или используют общий/облачный хостинг.
"""

import concurrent.futures
import logging
from ipaddress import IPv4Network

import dns.exception
import dns.resolver

from core.models import DEFAULT_NAMESERVERS
from resolvers.asn import is_valid_prefix

logger = logging.getLogger(__name__)


def _to_ascii_domain(domain: str) -> str:
    """Нормализует IDN (кириллические домены в punycode) для DNS-резолвинга."""
    clean_domain = domain.strip()
    try:
        return clean_domain.encode("idna").decode("ascii")
    except Exception:
        return clean_domain


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> tuple[list[IPv4Network], str | None]:
    """Вспомогательная функция для получения IP-адресов одного домена."""
    networks: list[IPv4Network] = []
    warning: str | None = None
    ascii_domain = _to_ascii_domain(domain)
    try:
        answers = resolver.resolve(ascii_domain, "A")
        for rdata in answers:
            ip = str(rdata)
            try:
                net = IPv4Network(f"{ip}/32", strict=False)
                if is_valid_prefix(net):
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


class DNSResolver:
    """Многопоточный DNS-резолвер с настраиваемыми DNS-серверами и пулом воркеров."""

    def __init__(
        self,
        nameservers: list[str] | None = None,
        timeout: float = 10.0,
        max_workers: int = 20,
    ) -> None:
        if timeout <= 0:
            raise ValueError("DNS timeout must be positive")
        if max_workers <= 0:
            raise ValueError("DNS max_workers must be positive")
        if nameservers is not None and not nameservers:
            raise ValueError("At least one DNS nameserver must be configured")

        self.nameservers = list(nameservers) if nameservers is not None else list(DEFAULT_NAMESERVERS)
        self.timeout = float(timeout)
        self.max_workers = int(max_workers)

    def _create_resolver(self) -> dns.resolver.Resolver:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = list(self.nameservers)
        resolver.timeout = max(1.0, self.timeout / len(resolver.nameservers))
        resolver.lifetime = self.timeout
        return resolver

    def _resolve_one(self, domain: str) -> tuple[list[IPv4Network], str | None]:
        # Свой Resolver на каждый домен: объект не делится между потоками.
        return _resolve_single_domain(domain, self._create_resolver())

    def resolve(self, domains: list[str]) -> dict[str, tuple[list[IPv4Network], str | None]]:
        """Резолвит уникальные домены одним общим пулом: {домен: (сети, предупреждение)}."""
        unique = list(dict.fromkeys(domains))
        if not unique:
            return {}
        workers = min(self.max_workers, len(unique))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            return dict(zip(unique, executor.map(self._resolve_one, unique), strict=True))
