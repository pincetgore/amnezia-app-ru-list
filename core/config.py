"""Configuration loading and parsing for amnezia-app-ru-list.

config.yaml is parsed once, here: everything past parse_config gets typed, checked values.
"""

import logging
import sys
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
from typing import Any

import yaml

from core.models import (
    DEFAULT_DNS_MAX_WORKERS,
    DEFAULT_DNS_TIMEOUT,
    DEFAULT_NAMESERVERS,
    AppConfig,
    DnsConfig,
    ServiceConfig,
)

logger = logging.getLogger(__name__)

ALLOWED_ROOT_KEYS: frozenset[str] = frozenset({"services", "dns"})
ALLOWED_DNS_KEYS: frozenset[str] = frozenset({"nameservers", "timeout", "max_workers", "exclude_asn"})
ALLOWED_SERVICE_KEYS: frozenset[str] = frozenset({"name", "asn", "domains", "ip_ranges"})


def _is_positive_int(value: Any) -> bool:
    """ASN and worker counts: a positive int; bool is an int subclass in Python, so it is rejected explicitly."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _list_field(raw: dict[str, Any], field: str, where: str) -> list[Any]:
    """Value of an optional list field: missing or null means an empty list."""
    value = raw.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"'{field}' for {where} must be a list")
    return value


def _check_domain(domain: Any, name: str) -> None:
    if not isinstance(domain, str) or not domain.strip() or " " in domain or domain != domain.strip():
        raise ValueError(f"Invalid domain for service '{name}': {domain!r}")
    if domain.startswith("*"):
        raise ValueError(f"Wildcard domains are not supported in service '{name}': {domain!r}")
    if "/" in domain:  # Ловит и схему URL: в "https://" тоже есть слеш.
        raise ValueError(f"Domain must not contain a URL scheme, path or slash in service '{name}': {domain!r}")


def _parse_network(value: Any, name: str) -> IPv4Network:
    if not isinstance(value, str):
        raise ValueError(f"Invalid IP range for service '{name}': {value!r}")
    try:
        return IPv4Network(value, strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid IP range for service '{name}': {value!r}") from exc


def _check_asns(asns: list[Any], where: str) -> None:
    for asn in asns:
        if not _is_positive_int(asn):
            raise ValueError(f"Invalid ASN {where}: {asn!r}")


def _service_name(index: int, raw: Any) -> str:
    """Name of a service mapping that has only known keys."""
    if not isinstance(raw, dict):
        raise ValueError(f"Service at index {index} must be a mapping")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Service at index {index} must have a non-empty string 'name'")
    extra_keys = set(raw) - ALLOWED_SERVICE_KEYS
    if extra_keys:
        raise ValueError(f"Service '{name}' has unknown fields: {sorted(extra_keys)}")
    return name


def _parse_service(index: int, raw: Any) -> ServiceConfig:
    name = _service_name(index, raw)
    where = f"service '{name}'"
    asns = _list_field(raw, "asn", where)
    domains = _list_field(raw, "domains", where)
    ip_ranges = _list_field(raw, "ip_ranges", where)
    if not (asns or domains or ip_ranges):
        raise ValueError(f"Service '{name}' must define ASN, domains, or IP ranges")

    _check_asns(asns, f"for {where}")
    for domain in domains:
        _check_domain(domain, name)
    networks = [_parse_network(ip_range, name) for ip_range in ip_ranges]
    return ServiceConfig(name=name, asn=list(asns), domains=list(domains), ip_ranges=networks)


def _parse_nameservers(nameservers: Any) -> list[str]:
    if not isinstance(nameservers, list) or not nameservers:
        raise ValueError("'dns.nameservers' must be a non-empty list")
    for nameserver in nameservers:
        # Только строки: IPv4Address(int) принял бы число как адрес.
        if not isinstance(nameserver, str):
            raise ValueError(f"Invalid DNS nameserver: {nameserver!r}")
        try:
            IPv4Address(nameserver)
        except ValueError as exc:
            raise ValueError(f"Invalid DNS nameserver: {nameserver!r}") from exc
    return list(nameservers)


def _parse_dns(raw: Any) -> DnsConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("'dns' must be a mapping")
    extra_keys = set(raw) - ALLOWED_DNS_KEYS
    if extra_keys:
        raise ValueError(f"'dns' has unknown fields: {sorted(extra_keys)}")

    nameservers = _parse_nameservers(raw.get("nameservers", DEFAULT_NAMESERVERS))
    timeout = raw.get("timeout", DEFAULT_DNS_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("'dns.timeout' must be a positive number")
    max_workers = raw.get("max_workers", DEFAULT_DNS_MAX_WORKERS)
    if not _is_positive_int(max_workers):
        raise ValueError("'dns.max_workers' must be a positive integer")

    exclude_asn = _list_field(raw, "exclude_asn", "'dns'")
    _check_asns(exclude_asn, "in 'dns.exclude_asn'")

    return DnsConfig(
        nameservers=nameservers,
        timeout=float(timeout),
        max_workers=max_workers,
        exclude_asn=list(exclude_asn),
    )


def parse_config(config: Any) -> AppConfig:
    """Parses the raw YAML mapping into AppConfig; raises ValueError on the first invalid value."""
    if not isinstance(config, dict):
        raise ValueError("Config root must be a mapping")
    extra_keys = set(config) - ALLOWED_ROOT_KEYS
    if extra_keys:
        raise ValueError(f"Config root has unknown fields: {sorted(extra_keys)}")
    services = config.get("services")
    if not isinstance(services, list):
        raise ValueError("'services' must be a list")
    return AppConfig(
        services=[_parse_service(index, service) for index, service in enumerate(services)],
        dns=_parse_dns(config.get("dns")),
    )


def load_raw_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Loads raw dictionary from YAML file, handling file errors gracefully."""
    str_path = str(path)
    try:
        with open(str_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.critical("Config file '%s' not found.", str_path)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.critical("Failed to parse YAML in '%s': %s", str_path, e)
        sys.exit(1)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Loads and parses the YAML config file into AppConfig; exits with code 1 if it is invalid."""
    raw = load_raw_config(path)
    try:
        return parse_config(raw)
    except ValueError as exc:
        logger.critical("Invalid configuration: %s", exc)
        sys.exit(1)
