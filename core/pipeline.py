"""Pipeline for resolving services into IP prefix lists."""

import logging
from collections.abc import Callable
from ipaddress import IPv4Network
from typing import Any

from core.models import (
    AppConfig,
    DnsConfig,
    PipelineResult,
    ServiceConfig,
    ServiceResult,
    ServiceStats,
)
from resolvers.asn import ASNResolver, resolve_asn
from resolvers.dns import DNSResolver

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]
ASNResolveCallable = Callable[[Any], list[IPv4Network]]
DNSResolveCallable = Callable[[list[str]], tuple[list[IPv4Network], list[str]]]


class ListBuilderPipeline:
    """Orchestrates resolution of ASN prefixes, DNS domain names, and static IP ranges."""

    def __init__(
        self,
        asn_resolver: ASNResolveCallable | ASNResolver | None = None,
        dns_resolver_factory: Callable[[DnsConfig], DNSResolveCallable | DNSResolver] | None = None,
    ) -> None:
        self._asn_resolver = asn_resolver
        self._dns_resolver_factory = dns_resolver_factory

    def _get_asn_resolver_func(self) -> ASNResolveCallable:
        if self._asn_resolver is None:
            return resolve_asn
        if isinstance(self._asn_resolver, ASNResolver):
            return self._asn_resolver.resolve
        return self._asn_resolver

    def _get_dns_resolver_func(self, dns_cfg: DnsConfig) -> DNSResolveCallable:
        if self._dns_resolver_factory is not None:
            resolved = self._dns_resolver_factory(dns_cfg)
            if isinstance(resolved, DNSResolver):
                return resolved.resolve
            return resolved

        resolver = DNSResolver(
            nameservers=dns_cfg.nameservers,
            timeout=dns_cfg.timeout,
            max_workers=dns_cfg.max_workers,
        )
        return resolver.resolve

    def resolve_service(
        self,
        service: ServiceConfig,
        asn_resolver_func: ASNResolveCallable,
        dns_resolver_func: DNSResolveCallable,
    ) -> tuple[ServiceResult, ServiceStats, list[str], list[str]]:
        """Resolves IP prefixes and collects warnings for a single service."""
        service_networks: list[IPv4Network] = []
        asn_warnings: list[str] = []
        dns_warnings: list[str] = []

        # 1. Resolve ASN prefixes
        if service.asn:
            for asn in service.asn:
                try:
                    prefixes = asn_resolver_func(asn)
                    if not prefixes:
                        logger.warning("No prefixes resolved for AS%s (%s)", asn, service.name)
                        asn_warnings.append(f"AS{asn} ({service.name})")
                    else:
                        service_networks.extend(prefixes)
                except Exception as e:
                    logger.warning("Failed to resolve AS%s for %s: %s", asn, service.name, e)
                    logger.debug("Exception details:", exc_info=True)
                    asn_warnings.append(f"AS{asn} ({service.name}) - error: {e}")

        # 2. Resolve DNS domain names
        if service.domains:
            try:
                dns_networks, domain_warnings = dns_resolver_func(service.domains)
                service_networks.extend(dns_networks)
                dns_warnings.extend(domain_warnings)
            except Exception as e:
                logger.warning("Failed DNS resolution for %s: %s", service.name, e)
                logger.debug("Exception details:", exc_info=True)
                dns_warnings.append(f"{service.name} (DNS error: {e})")

        # 3. Add explicit static IP ranges
        if service.ip_ranges:
            for ip_str in service.ip_ranges:
                try:
                    service_networks.append(IPv4Network(ip_str, strict=False))
                except ValueError as e:
                    logger.warning("Invalid IP range '%s' for %s: %s", ip_str, service.name, e)

        result = ServiceResult(
            name=service.name,
            domains=list(service.domains),
            networks=service_networks,
        )
        stats = ServiceStats(
            name=service.name,
            raw_prefix_count=len(service_networks),
        )
        return result, stats, asn_warnings, dns_warnings

    def run(
        self,
        config: AppConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Executes the pipeline over all services in the configuration."""
        asn_func = self._get_asn_resolver_func()
        dns_func = self._get_dns_resolver_func(config.dns)

        service_results: list[ServiceResult] = []
        stats: list[ServiceStats] = []
        all_asn_warnings: list[str] = []
        all_dns_warnings: list[str] = []

        total_services = len(config.services)
        for index, service in enumerate(config.services):
            if progress_callback is not None:
                progress_callback(service.name, index, total_services)

            res, st, asn_warns, dns_warns = self.resolve_service(
                service,
                asn_resolver_func=asn_func,
                dns_resolver_func=dns_func,
            )
            service_results.append(res)
            stats.append(st)
            all_asn_warnings.extend(asn_warns)
            all_dns_warnings.extend(dns_warns)

        return PipelineResult(
            service_results=service_results,
            stats=stats,
            asn_warnings=all_asn_warnings,
            dns_warnings=all_dns_warnings,
        )
