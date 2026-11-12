"""
Форматтер вывода для AmneziaVPN и простых текстовых форматов (plain-text).

Агрегирует IP-сети всех сервисов и создает либо совместимый с AmneziaVPN
JSON-файл, либо простой текстовый список CIDR.

Формат AmneziaVPN:
  Массив объектов JSON: [{"hostname": "<cidr>", "ip": ""}, ...]
"""

import json
from ipaddress import IPv4Network, collapse_addresses
from pathlib import Path


def aggregate_networks(networks: list[IPv4Network]) -> list[IPv4Network]:
    """Удаляет дубликаты, сливает перекрывающиеся и смежные сети, возвращает их по возрастанию.

    0.0.0.0/0 отбрасывается на входе. Если сети всё равно слились в 0.0.0.0/0
    (например, 0.0.0.0/1 + 128.0.0.0/1), это ошибка: весь трафик ушёл бы мимо VPN.
    """
    aggregated = list(collapse_addresses(net for net in networks if net.prefixlen > 0))
    if any(net.prefixlen == 0 for net in aggregated):
        raise ValueError("Networks merge into 0.0.0.0/0: check ip_ranges in config")
    return aggregated


def format_amnezia(sorted_nets: list[IPv4Network]) -> list[dict[str, str]]:
    """Формирует JSON-структуру для AmneziaVPN: одна запись CIDR на сеть."""
    return [{"hostname": str(net), "ip": ""} for net in sorted_nets]


def format_plain(sorted_nets: list[IPv4Network]) -> str:
    """Формирует простой текстовый список CIDR (один префикс на строку)."""
    return "\n".join(str(n) for n in sorted_nets) + "\n"


def write_output(networks: list[IPv4Network], output_path: str, fmt: str = "amnezia") -> list[IPv4Network]:
    """Агрегирует сети и записывает их в файл в формате "amnezia" (JSON) или "plain" (CIDR на строку).

    Возвращает агрегированные сети. Если сетей нет, файл не трогается и возвращается [].
    """
    sorted_nets = aggregate_networks(networks)
    if not sorted_nets:
        return []

    if fmt == "amnezia":
        content = json.dumps(format_amnezia(sorted_nets), indent=2, ensure_ascii=False) + "\n"
    elif fmt == "plain":
        content = format_plain(sorted_nets)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Без атомарной замены: CI публикует файл, только если скрипт завершился с кодом 0.
    path.write_text(content, encoding="utf-8")
    return sorted_nets
