"""
Output formatter for AmneziaVPN and plain-text formats.

Takes per-service resolution results (domains + IP networks) and produces
either an AmneziaVPN-compatible JSON file or a plain-text CIDR list.

AmneziaVPN format:
  A JSON array of objects: [{"hostname": "<domain_or_cidr>", "ip": ""}, ...]
  Domains are listed first (human-readable labels in the app UI),
  followed by aggregated CIDR ranges.
"""

import json
from ipaddress import IPv4Network, collapse_addresses
from pathlib import Path


def aggregate_networks(networks: list[IPv4Network]) -> list[IPv4Network]:
    """Deduplicate and aggregate networks.

    Uses stdlib collapse_addresses() to merge overlapping/adjacent subnets
    and remove individual IPs already covered by a wider prefix.
    """
    if not networks:
        return []
    return list(collapse_addresses(networks))


def format_amnezia(service_results: list[dict]) -> tuple[list, list]:
    """Build AmneziaVPN JSON structure from per-service results.

    Output layout:
      1. Domain entries (readable names shown in AmneziaVPN UI)
      2. Aggregated CIDR entries (actual routing rules)

    Returns (entries_list, aggregated_networks) tuple.
    """
    entries = []
    seen_domains = set()
    all_networks = []

    # Collect unique domains from all services (displayed as labels in the app)
    for svc in service_results:
        for domain in svc.get("domains", []):
            if domain not in seen_domains:
                entries.append({"hostname": domain, "ip": ""})
                seen_domains.add(domain)
        all_networks.extend(svc.get("networks", []))

    # Aggregate all CIDR ranges across services and append after domains
    aggregated = aggregate_networks(all_networks)
    sorted_nets = sorted(aggregated, key=lambda n: (n.network_address, n.prefixlen))

    for net in sorted_nets:
        entries.append({"hostname": str(net), "ip": ""})

    return entries, aggregated


def format_plain(service_results: list[dict]) -> tuple[str, list]:
    """Build a plain-text CIDR list (one prefix per line)."""
    all_networks = []
    for svc in service_results:
        all_networks.extend(svc.get("networks", []))

    aggregated = aggregate_networks(all_networks)
    sorted_nets = sorted(aggregated, key=lambda n: (n.network_address, n.prefixlen))
    text = "\n".join(str(n) for n in sorted_nets) + "\n"
    return text, aggregated


def write_output(service_results: list[dict], output_path: str, fmt: str = "amnezia"):
    """Write the formatted output to a file.

    Supported formats:
      - "amnezia": JSON array for AmneziaVPN import
      - "plain":   one CIDR per line (for other VPN clients or firewalls)

    Returns the list of aggregated IPv4Network objects.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "amnezia":
        data, aggregated = format_amnezia(service_results)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    elif fmt == "plain":
        text, aggregated = format_plain(service_results)
        path.write_text(text)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    return aggregated
