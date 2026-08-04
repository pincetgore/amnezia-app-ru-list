#!/usr/bin/env python3
"""
Читает определения сервисов из config.yaml, получает их IP-диапазоны
через запросы ASN (RIPE NCC API) и DNS A-записи, затем выводит
агрегированный ip-list.json, совместимый с раздельным туннелированием AmneziaVPN.
"""

import argparse
import logging
import signal
import sys
from ipaddress import IPv4Address, IPv4Network
from typing import Any, Dict, List

import yaml
from tqdm import tqdm

from output.formatter import aggregate_networks, write_output
from resolvers.asn import resolve_asn
from resolvers.dns import resolve_domains

logger = logging.getLogger(__name__)

DEFAULT_NAMESERVERS = ["77.88.8.8", "77.88.8.1", "8.8.8.8", "1.1.1.1"]


def validate_config(config: Dict[str, Any]) -> None:
    """Проверяет структуру конфигурации до выполнения сетевых запросов."""
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
            if not isinstance(domain, str) or not domain.strip():
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


def _handle_sigint(sig, frame):
    """Graceful shutdown при Ctrl+C."""
    logger.info("Received interrupt signal, shutting down...")
    sys.exit(130)


def main():
    """Главная функция: загружает сервисы из config.yaml, резолвит их IP через ASN/DNS и генерирует список.
    
    Алгоритм:
    1. Загружает конфигурацию сервисов из config.yaml
    2. Для каждого сервиса получает IP-префиксы через RIPE API/bgp.he.net по ASN
    3. Резолвит A-записи доменов параллельно
    4. Добавляет явно заданные IP-диапазоны
    5. Агрегирует все CIDR-диапазоны (удаляет дубли и вложенные подсети)
    6. Записывает результат в JSON/plain формат
    7. Выводит статистику
    """
    # Регистрация обработчика для graceful shutdown
    signal.signal(signal.SIGINT, _handle_sigint)
    
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

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    # -- Загрузка определений сервисов --
    config = load_config(args.config) or {}
    try:
        validate_config(config)
    except ValueError as exc:
        logger.critical("Invalid configuration: %s", exc)
        sys.exit(1)

    services = config["services"]

    # -- Загрузка DNS конфигурации --
    dns_config = config.get("dns") or {}
    dns_nameservers = dns_config.get("nameservers", DEFAULT_NAMESERVERS)
    dns_timeout = dns_config.get("timeout", 10)
    dns_max_workers = dns_config.get("max_workers", 20)

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
            for asn in asns:
                try:
                    prefixes = resolve_asn(asn)
                    if not prefixes:
                        logger.error("No prefixes resolved for AS%s (%s)", asn, name)
                        errors += 1
                    service_networks.extend(prefixes)
                except Exception as e:
                    logger.error("Failed to resolve AS%s for %s: %s", asn, name, e)
                    logger.debug("Exception details:", exc_info=True)
                    errors += 1

        # Шаг 2: Резолв A-записей доменов для дополнения данных ASN IP-адресами /32
        if domains:
            try:
                dns_networks, dns_warnings = resolve_domains(
                    domains,
                    timeout=dns_timeout,
                    max_workers=dns_max_workers,
                    nameservers=dns_nameservers,
                )
                service_networks.extend(dns_networks)
                all_dns_warnings.extend(dns_warnings)
                errors += len(dns_warnings)
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

    # -- Вывод сводной статистики --
    print("\n" + "=" * 50)
    print("Statistics:")
    print("=" * 50)
    for name, count in stats:
        print(f"  {name}: {count} raw prefixes")
    print("-" * 50)
    print(f"  Services processed: {len(stats)}")
    print(f"  Total raw prefixes: {sum(c for _, c in stats)}")
    if errors:
        print(f"  Errors:             {errors}")
    if all_dns_warnings:
        print(f"  DNS warnings:       {len(all_dns_warnings)}")
        print("\nDomains that could not be resolved:")
        for domain in sorted(set(all_dns_warnings)):
            print(f"  ⚠️  {domain}")
    
    # Не публикуем частичный список: он может заменить корректный предыдущий релиз.
    if errors:
        logger.error("Collection completed with errors; output was not written.")
        sys.exit(1)

    # Не создаём даже пустой выходной файл при полном отсутствии данных.
    aggregated = aggregate_networks(
        [network for result in service_results for network in result["networks"]]
    )
    if not aggregated:
        logger.error("No IP prefixes were collected; output was not written.")
        sys.exit(1)

    # -- Запись выходного файла только после успешного сбора всех данных --
    write_output(service_results, args.output, args.format)

    print(f"  After aggregation:  {len(aggregated)}")
    print(f"  Total entries:      {len(aggregated)}")
    print(f"\nOutput: {args.output}")


if __name__ == "__main__":
    main()
