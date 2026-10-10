"""Pipeline for resolving services into IP prefix lists."""

import logging
from collections.abc import Callable, Mapping
from ipaddress import IPv4Network
from typing import Any

from core.models import (
    AppConfig,
    PipelineResult,
    ServiceResult,
    ServiceStats,
)
from resolvers.asn import resolve_asn
from resolvers.dns import DNSResolver

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], object]
ASNResolve = Callable[[Any], list[IPv4Network]]
DNSResolve = Callable[[list[str]], Mapping[str, tuple[list[IPv4Network], str | None]]]


class ListBuilderPipeline:
    """Orchestrates resolution of ASN prefixes, DNS domain names, and static IP ranges."""

    def __init__(self, asn_resolve: ASNResolve = resolve_asn, dns_resolve: DNSResolve | None = None) -> None:
        self._asn_resolve = asn_resolve
        self._dns_resolve = dns_resolve

    def _resolve_all_domains(self, config: AppConfig) -> Mapping[str, tuple[list[IPv4Network], str | None]]:
        """Resolves every domain of every service in one shared worker pool."""
        all_domains = [domain for service in config.services for domain in service.domains]
        if not all_domains:
            return {}
        dns_resolve = self._dns_resolve
        if dns_resolve is None:
            dns_resolve = DNSResolver(
                nameservers=config.dns.nameservers,
                timeout=config.dns.timeout,
                max_workers=config.dns.max_workers,
            ).resolve
        try:
            return dns_resolve(all_domains)
        except Exception as e:
            logger.warning("DNS resolution failed: %s", e)
            logger.debug("Exception details:", exc_info=True)
            return {domain: ([], domain) for domain in all_domains}

    def run(
        self,
        config: AppConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Executes the pipeline over all services in the configuration."""
        dns_results = self._resolve_all_domains(config)
        result = PipelineResult(
            asn_total=sum(len(s.asn) for s in config.services),
            dns_warnings=[warning for _nets, warning in dns_results.values() if warning],
            domain_total=len(dns_results),
        )

        total_services = len(config.services)
        for index, service in enumerate(config.services):
            if progress_callback is not None:
                progress_callback(service.name, index, total_services)

            networks: list[IPv4Network] = []
            for asn in service.asn:
                try:
                    prefixes = self._asn_resolve(asn)
                except Exception as e:
                    logger.warning("Failed to resolve AS%s for %s: %s", asn, service.name, e)
                    logger.debug("Exception details:", exc_info=True)
                    result.asn_warnings.append(f"AS{asn} ({service.name}) - error: {e}")
                    continue
                if prefixes:
                    networks.extend(prefixes)
                else:
                    logger.warning("No prefixes resolved for AS%s (%s)", asn, service.name)
                    result.asn_warnings.append(f"AS{asn} ({service.name})")

            for domain in service.domains:
                networks.extend(dns_results[domain][0])

            # Validated by core.config.validate_config before the pipeline runs.
            networks.extend(IPv4Network(ip_range, strict=False) for ip_range in service.ip_ranges)

            result.service_results.append(
                ServiceResult(name=service.name, domains=list(service.domains), networks=networks)
            )
            result.stats.append(ServiceStats(name=service.name, raw_prefix_count=len(networks)))

        return result
