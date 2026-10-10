#!/usr/bin/env python3
"""
Читает определения сервисов из config.yaml, получает их IP-диапазоны
через запросы ASN (RIPE NCC API) и DNS A-записи, затем выводит
агрегированный ip-list.json, совместимый с раздельным туннелированием AmneziaVPN.
"""

import argparse
import logging
import sys

from tqdm import tqdm

from core.config import load_config
from core.pipeline import ListBuilderPipeline
from core.reporter import print_aggregation_summary, print_statistics_report
from output.formatter import write_output
from resolvers.asn import resolve_asn

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    """Создает парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Generate IP bypass list for Russian services (AmneziaVPN split tunneling)"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="ip-list.json",
        help="Output file path (default: ip-list.json)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["amnezia", "plain"],
        default="amnezia",
        help="Output format (default: amnezia)",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> None:
    """Главная функция: загружает сервисы из config.yaml, резолвит их IP через ASN/DNS и генерирует список."""
    args = build_arg_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    config = load_config(args.config)
    # resolve_asn берётся из модуля main, чтобы тесты могли подменить его через monkeypatch.
    pipeline = ListBuilderPipeline(asn_resolve=resolve_asn)

    with tqdm(
        total=len(config.services), desc="Processing services", unit="svc", disable=not sys.stdout.isatty()
    ) as pbar:
        pipeline_result = pipeline.run(config, progress_callback=lambda _name, _idx, _total: pbar.update(1))

    print_statistics_report(pipeline_result)

    # Не публикуем список при массовом сбое RIPE/DNS: статические ip_ranges
    # резолвятся всегда, и иначе почти пустой файл заменил бы рабочий.
    failure = pipeline_result.failure_reason()
    if failure:
        logger.error("Too many lookups failed, output was not written: %s", failure)
        sys.exit(1)

    sorted_nets = write_output(pipeline_result.collect_all_networks(), args.output, args.format)
    if not sorted_nets:
        logger.error("No valid IP prefixes after aggregation; output was not written.")
        sys.exit(1)

    print_aggregation_summary(len(sorted_nets), args.output)


if __name__ == "__main__":
    main()
