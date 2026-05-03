"""
Форматтер вывода для AmneziaVPN и простых текстовых форматов (plain-text).

Принимает результаты резолвинга по сервисам (домены + IP-сети) и создает
либо совместимый с AmneziaVPN JSON-файл, либо простой текстовый список CIDR.

Формат AmneziaVPN:
  Массив объектов JSON: [{"hostname": "<domain_or_cidr>", "ip": ""}, ...]
"""

import json
from ipaddress import IPv4Network, collapse_addresses
from pathlib import Path
from typing import Any, Dict, List


def aggregate_networks(networks: List[IPv4Network]) -> List[IPv4Network]:
    """Удаляет дубликаты и агрегирует сети.

    Использует collapse_addresses() из стандартной библиотеки для слияния перекрывающихся/смежных подсетей
    и удаления отдельных IP-адресов, которые уже покрыты более широким префиксом.
    """
    if not networks:
        return []
    return list(collapse_addresses(networks))


def format_amnezia(sorted_nets: List[IPv4Network]) -> List[Dict[str, str]]:
    """Формирует JSON-структуру для AmneziaVPN из результатов по каждому сервису.

    Структура вывода:
      1. Агрегированные записи CIDR (фактические правила маршрутизации)
    """
    return [{"hostname": str(net), "ip": ""} for net in sorted_nets]


def format_plain(sorted_nets: List[IPv4Network]) -> str:
    """Формирует простой текстовый список CIDR (один префикс на строку)."""
    return "\n".join(str(n) for n in sorted_nets) + "\n"


def write_output(
    service_results: List[Dict[str, Any]],
    output_path: str,
    fmt: str = "amnezia"
) -> List[IPv4Network]:
    """Записывает отформатированный вывод в файл.

    Поддерживаемые форматы:
      - "amnezia": массив JSON для импорта в AmneziaVPN
      - "plain":   один CIDR на строку (для других VPN-клиентов или брандмауэров)

    Возвращает список агрегированных объектов IPv4Network.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Собираем сети со всех сервисов
    all_networks = []
    for svc in service_results:
        all_networks.extend(svc.get("networks", []))

    # Агрегируем все CIDR-диапазоны из всех сервисов и сортируем их
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
