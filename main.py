#!/usr/bin/env python3
"""
Читает определения сервисов из config.yaml, получает их IP-диапазоны
через запросы ASN (RIPE NCC API) и DNS A-записи, затем выводит
агрегированный ip-list.json, совместимый с раздельным туннелированием AmneziaVPN.
"""

import argparse
import concurrent.futures
import logging
import sys
from typing import Any, Dict

import yaml
from tqdm import tqdm
from ipaddress import IPv4Network

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
    """Загружает определения сервисов из конфигурационного файла YAML."""
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
    # -- Парсинг аргументов командной строки (CLI) --
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

    # -- Загрузка определений сервисов --
    config = load_config(args.config)
    services = config.get("services", [])

    service_results = []
    stats = []
    errors = 0
    all_dns_warnings = []

    # -- Обработка каждого сервиса: получение префиксов ASN и DNS-записей --
    for service in tqdm(services, desc="Processing services", unit="svc"):
        name = service["name"]
        service_networks = []
        # Безопасное извлечение: защищает от случаев, когда в YAML указано 'domains: null'
        domains = service.get("domains") or []
        asns = service.get("asn") or []
        ip_ranges = service.get("ip_ranges") or []

        # Шаг 1: Получение всех анонсированных IP-префиксов для каждой ASN через RIPE API
        if asns:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_asn = {executor.submit(resolve_asn, asn): asn for asn in asns}
                for future in concurrent.futures.as_completed(future_to_asn):
                    asn = future_to_asn[future]
                    try:
                        prefixes = future.result()
                        service_networks.extend(prefixes)
                    except Exception as e:
                        logger.error("Failed to resolve AS%d for %s: %s", asn, name, e)
                        logger.debug("Exception details:", exc_info=True)
                        errors += 1

        # Шаг 2: Резолв A-записей доменов для дополнения данных ASN IP-адресами /32
        if domains:
            try:
                dns_networks, dns_warnings = resolve_domains(domains)
                service_networks.extend(dns_networks)
                all_dns_warnings.extend(dns_warnings)
            except Exception as e:
                logger.error("Failed DNS resolution for %s: %s", name, e)
                logger.debug("Exception details:", exc_info=True)
                errors += 1

        # Шаг 3: Добавление явно заданных IP-диапазонов
        if ip_ranges:
            for ip_str in ip_ranges:
                try:
                    service_networks.append(IPv4Network(ip_str, strict=False))
                except ValueError as e:
                    logger.error("Invalid IP range '%s' for %s: %s", ip_str, name, e)
                    errors += 1

        count = len(service_networks)
        stats.append((name, count))
        service_results.append({
            "name": name,
            "domains": domains,
            "networks": service_networks,
        })
        tqdm.write(f"  {name}: {count} prefixes")

    # -- Запись выходного файла в выбранном формате --
    aggregated = write_output(service_results, args.output, args.format)

    # -- Вывод сводной статистики --
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

    # Опционально: Для строгих CI/CD пайплайнов можно возвращать код ошибки,
    # если произошли сбои: if errors > 0: sys.exit(1)


if __name__ == "__main__":
    main()
