"""
Output formatter for AmneziaVPN and plain-text formats.

Takes per-service resolution results (domains + IP networks) and produces
either an AmneziaVPN-compatible JSON file or a plain-text CIDR list.

AmneziaVPN format:
  A JSON array of objects: [{"hostname": "<domain_or_cidr>", "ip": ""}, ...]
"""

import json
from ipaddress import IPv4Network, collapse_addresses
from pathlib import Path
from typing import Any, Dict, List


def aggregate_networks(networks: List[IPv4Network]) -> List[IPv4Network]:
    """Deduplicate and aggregate networks.

    Uses stdlib collapse_addresses() to merge overlapping/adjacent subnets
    and remove individual IPs already covered by a wider prefix.
    """
    if not networks:
        return []
    return list(collapse_addresses(networks))


def format_amnezia(sorted_nets: List[IPv4Network]) -> List[Dict[str, str]]:
    """Build AmneziaVPN JSON structure from per-service results.

    Output layout:
      1. Aggregated CIDR entries (actual routing rules)
    """
    return [{"hostname": str(net), "ip": ""} for net in sorted_nets]


def format_plain(sorted_nets: List[IPv4Network]) -> str:
    """Build a plain-text CIDR list (one prefix per line)."""
    return "\n".join(str(n) for n in sorted_nets) + "\n"


def write_output(
    service_results: List[Dict[str, Any]],
    output_path: str,
    fmt: str = "amnezia"
) -> List[IPv4Network]:
    """Write the formatted output to a file.

    Supported formats:
      - "amnezia": JSON array for AmneziaVPN import
      - "plain":   one CIDR per line (for other VPN clients or firewalls)

    Returns the list of aggregated IPv4Network objects.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Collect networks from all services
    all_networks = []
    for svc in service_results:
        all_networks.extend(svc.get("networks", []))

    # Aggregate all CIDR ranges across services and sort them
    aggregated = aggregate_networks(all_networks)
    sorted_nets = sorted(aggregated, key=lambda n: (n.network_address, n.prefixlen))

    if fmt == "amnezia":
        data = format_amnezia(sorted_nets)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    elif fmt == "plain":
        text = format_plain(sorted_nets)
        path.write_text(text)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    return aggregated
