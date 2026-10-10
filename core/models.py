"""Domain models for amnezia-app-ru-list."""

from dataclasses import dataclass, field
from ipaddress import IPv4Network

DEFAULT_NAMESERVERS: list[str] = ["77.88.8.8", "77.88.8.1", "8.8.8.8", "1.1.1.1"]
DEFAULT_DNS_TIMEOUT: float = 10.0
DEFAULT_DNS_MAX_WORKERS: int = 20


@dataclass(slots=True, frozen=True)
class DnsConfig:
    """DNS resolver configuration parameters."""

    nameservers: list[str] = field(default_factory=lambda: list(DEFAULT_NAMESERVERS))
    timeout: float = DEFAULT_DNS_TIMEOUT
    max_workers: int = DEFAULT_DNS_MAX_WORKERS


@dataclass(slots=True, frozen=True)
class ServiceConfig:
    """Service definition containing identifiers to resolve."""

    name: str
    asn: list[int] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    ip_ranges: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Complete application configuration."""

    services: list[ServiceConfig] = field(default_factory=list)
    dns: DnsConfig = field(default_factory=DnsConfig)


@dataclass(slots=True)
class ServiceResult:
    """Result of resolving a single service."""

    name: str
    domains: list[str] = field(default_factory=list)
    networks: list[IPv4Network] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ServiceStats:
    """Raw metrics for a processed service."""

    name: str
    raw_prefix_count: int


@dataclass(slots=True)
class PipelineResult:
    """Aggregated output from running the list generation pipeline."""

    service_results: list[ServiceResult] = field(default_factory=list)
    stats: list[ServiceStats] = field(default_factory=list)
    asn_warnings: list[str] = field(default_factory=list)
    dns_warnings: list[str] = field(default_factory=list)
    asn_total: int = 0
    domain_total: int = 0

    @property
    def total_raw_prefixes(self) -> int:
        """Sum of all raw prefixes collected across services."""
        return sum(s.raw_prefix_count for s in self.stats)

    def failure_reason(self, max_failed_share: float = 0.5) -> str | None:
        """Returns why the run must not be published, or None if it is healthy.

        Static ip_ranges always resolve, so "some networks collected" does not prove
        that RIPE or DNS worked. A mass failure would publish a near-empty list.
        """
        checks = (
            ("ASN", len(self.asn_warnings), self.asn_total),
            ("domain", len(self.dns_warnings), self.domain_total),
        )
        for kind, failed, total in checks:
            if total and failed / total > max_failed_share:
                return f"{failed} of {total} {kind} lookups failed (limit {max_failed_share:.0%})"
        return None

    def collect_all_networks(self) -> list[IPv4Network]:
        """Flatten and return all collected networks."""
        networks: list[IPv4Network] = []
        for res in self.service_results:
            networks.extend(res.networks)
        return networks
