#!/usr/bin/env python3
"""
Entry point for ru-bypass-list generator.

Reads service definitions from config.yaml, resolves their IP ranges
via ASN lookups (RIPE NCC API) and DNS A-record queries, then outputs
an aggregated ip-list.json compatible with AmneziaVPN split tunneling.
"""

import argparse
import logging
import sys
from typing import Any, Dict

import yaml
from tqdm import tqdm

from output.formatter import write_output
from resolvers.asn import resolve_asn
from resolvers.dns import resolve_domains

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    """Load service definitions from a YAML config file."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.critical("Config file '%s' not found.", path)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.critical("Failed to parse YAML in '%s': %s", path, e)
        sys.exit(1)


def main():
    # -- CLI argument parsing --
    parser = argparse.ArgumentParser(
        description="Generate IP bypass list for Russian services (AmneziaVPN split tunneling)"
    )
    parser.add_argument(
        "--output", "-o",
        default="ip-list.json",
        help="Output file path (default: ip-list.json)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["amnezia", "plain"],
        default="amnezia",
        help="Output format (default: amnezia)",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # -- Load service definitions --
    config = load_config(args.config)
    services = config.get("services", [])

    service_results = []
    stats = []
    errors = 0
    all_dns_warnings = []

    # -- Process each service: resolve ASN prefixes + DNS records --
    for service in tqdm(services, desc="Processing services", unit="svc"):
        name = service["name"]
        service_networks = []
        domains = service.get("domains", [])

        # Step 1: Fetch all announced IP prefixes for each ASN via RIPE API
        for asn in service.get("asn", []):
            try:
                prefixes = resolve_asn(asn)
                service_networks.extend(prefixes)
            except Exception as e:
                logger.error("Failed to resolve AS%d for %s: %s", asn, name, e)
                logger.debug("Exception details:", exc_info=True)
                errors += 1

        # Step 2: Resolve domain A-records to supplement ASN data with /32 IPs
        if domains:
            try:
                dns_networks, dns_warnings = resolve_domains(domains)
                service_networks.extend(dns_networks)
                all_dns_warnings.extend(dns_warnings)
            except Exception as e:
                logger.error("Failed DNS resolution for %s: %s", name, e)
                logger.debug("Exception details:", exc_info=True)
                errors += 1

        count = len(service_networks)
        stats.append((name, count))
        service_results.append({
            "name": name,
            "domains": domains,
            "networks": service_networks,
        })
        tqdm.write(f"  {name}: {count} prefixes")

    # -- Write output file in the chosen format --
    aggregated = write_output(service_results, args.output, args.format)

    # -- Print summary statistics --
    print("\n" + "=" * 50)
    print("Statistics:")
    print("=" * 50)
    for name, count in stats:
        print(f"  {name}: {count} raw prefixes")
    print("-" * 50)
    print(f"  Services processed: {len(stats)}")
    print(f"  Total raw prefixes: {sum(c for _, c in stats)}")
    print(f"  After aggregation:  {len(aggregated)}")
    print(f"  Total entries:      {len(aggregated)}")
    if errors:
        print(f"  Errors:             {errors}")
    if all_dns_warnings:
        print(f"  DNS Warnings:       {len(all_dns_warnings)}")
        print("\nDomains with DNS warnings:")
        for w in sorted(set(all_dns_warnings)):
            print(f"  - {w}")
    print(f"\nOutput: {args.output}")


if __name__ == "__main__":
    main()
