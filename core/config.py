"""Configuration loading and validation for amnezia-app-ru-list."""

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

ALLOWED_SERVICE_KEYS: frozenset[str] = frozenset({"name", "asn", "domains", "ip_ranges"})


def validate_config(config: dict[str, Any]) -> None:
    """Validates the configuration mapping structure before performing network calls."""
    if not isinstance(config, dict):
        raise ValueError("Config root must be a mapping")

    services = config.get("services")
    if not isinstance(services, list):
        raise ValueError("'services' must be a list")

    for index, service in enumerate(services):
        if not isinstance(service, dict):
            raise ValueError(f"Service at index {index} must be a mapping")
        name = service.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Service at index {index} must have a non-empty string 'name'")

        extra_keys = set(service.keys()) - ALLOWED_SERVICE_KEYS
        if extra_keys:
            raise ValueError(f"Service '{name}' has unknown fields: {sorted(extra_keys)}")

        for field in ("asn", "domains", "ip_ranges"):
            value = service.get(field)
            if value is not None and not isinstance(value, list):
                raise ValueError(f"'{field}' for service '{name}' must be a list")
        if not any(service.get(field) for field in ("asn", "domains", "ip_ranges")):
            raise ValueError(f"Service '{name}' must define ASN, domains, or IP ranges")

        for asn in service.get("asn") or []:
            if isinstance(asn, bool) or not isinstance(asn, int) or asn <= 0:
                raise ValueError(f"Invalid ASN for service '{name}': {asn!r}")
        for domain in service.get("domains") or []:
            if not isinstance(domain, str) or not domain.strip() or " " in domain or domain != domain.strip():
                raise ValueError(f"Invalid domain for service '{name}': {domain!r}")
        for ip_range in service.get("ip_ranges") or []:
            if not isinstance(ip_range, str):
                raise ValueError(f"Invalid IP range for service '{name}': {ip_range!r}")
            try:
                IPv4Network(ip_range, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid IP range for service '{name}': {ip_range!r}") from exc

    dns_config = config.get("dns", {})
    if dns_config is not None and not isinstance(dns_config, dict):
        raise ValueError("'dns' must be a mapping")
    dns_config = dns_config or {}
    if "nameservers" in dns_config:
        nameservers = dns_config["nameservers"]
        if not isinstance(nameservers, list) or not nameservers:
            raise ValueError("'dns.nameservers' must be a non-empty list")
        for nameserver in nameservers:
            if not isinstance(nameserver, str):
                raise ValueError(f"Invalid DNS nameserver: {nameserver!r}")
            try:
                IPv4Address(nameserver)
            except ValueError as exc:
                raise ValueError(f"Invalid DNS nameserver: {nameserver!r}") from exc
    for field in ("timeout", "max_workers"):
        if field in dns_config:
            value = dns_config[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"'dns.{field}' must be a positive number")


def parse_config(config: dict[str, Any]) -> AppConfig:
    """Parses a validated raw config dictionary into typed domain dataclasses."""
    services_raw = config.get("services", [])
    parsed_services: list[ServiceConfig] = []

    for svc in services_raw:
        parsed_services.append(
            ServiceConfig(
                name=svc["name"],
                asn=list(svc.get("asn") or []),
                domains=list(svc.get("domains") or []),
                ip_ranges=list(svc.get("ip_ranges") or []),
            )
        )

    dns_raw = config.get("dns") or {}
    dns_nameservers = dns_raw.get("nameservers", DEFAULT_NAMESERVERS)
    dns_timeout = float(dns_raw.get("timeout", DEFAULT_DNS_TIMEOUT))
    dns_max_workers = int(dns_raw.get("max_workers", DEFAULT_DNS_MAX_WORKERS))

    dns_cfg = DnsConfig(
        nameservers=list(dns_nameservers),
        timeout=dns_timeout,
        max_workers=dns_max_workers,
    )

    return AppConfig(services=parsed_services, dns=dns_cfg)


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
    """Loads, validates, and parses YAML config file into AppConfig."""
    raw = load_raw_config(path)
    try:
        validate_config(raw)
    except ValueError as exc:
        logger.critical("Invalid configuration: %s", exc)
        sys.exit(1)
    return parse_config(raw)
