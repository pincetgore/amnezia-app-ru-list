"""
DNS domain resolver.

Resolves a list of domain names to their IPv4 addresses via DNS A-record
queries. Each resolved IP is returned as a /32 network. This supplements
ASN-based prefix resolution for services that don't have a dedicated ASN
or use shared/cloud hosting.
"""

import logging
import concurrent.futures
from ipaddress import IPv4Network

import dns.resolver

logger = logging.getLogger(__name__)


def _resolve_single_domain(domain: str, resolver: dns.resolver.Resolver) -> tuple[list[IPv4Network], str | None]:
    """Helper function to resolve a single domain."""
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
    """Resolve a list of domains to /32 IPv4 networks and return warnings.

    Errors for individual domains are logged and skipped — the function
    returns a tuple of (networks, warning_domains) without raising.
    Queries are executed concurrently using a thread pool.
    """
    resolver = dns.resolver.Resolver()
    # Используем публичные DNS-серверы (Google, Cloudflare) вместо системных
    resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4', '1.0.0.1']
    resolver.timeout = timeout
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
