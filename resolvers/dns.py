"""
DNS domain resolver.

Resolves a list of domain names to their IPv4 addresses via DNS A-record
queries. Each resolved IP is returned as a /32 network. This supplements
ASN-based prefix resolution for services that don't have a dedicated ASN
or use shared/cloud hosting.
"""

import logging
from ipaddress import IPv4Network

import dns.resolver

logger = logging.getLogger(__name__)


def resolve_domains(domains: list[str], timeout: int = 10) -> list[IPv4Network]:
    """Resolve a list of domains to /32 IPv4 networks via DNS A-records.

    Errors for individual domains are logged and skipped — the function
    always returns a (possibly empty) list without raising.
    """
    resolver = dns.resolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout

    networks = []
    for domain in domains:
        try:
            answers = resolver.resolve(domain, "A")
            for rdata in answers:
                ip = str(rdata)
                net = IPv4Network(f"{ip}/32", strict=False)
                networks.append(net)
                logger.debug("DNS %s -> %s", domain, ip)
            logger.info("DNS %s: resolved %d A records", domain, len(answers))
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers) as e:
            logger.warning("DNS resolution failed for %s: %s", domain, e)
        except dns.exception.Timeout:
            logger.warning("DNS timeout for %s", domain)
        except Exception as e:
            logger.warning("DNS error for %s: %s", domain, e)

    return networks
