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
from types import FrameType

from tqdm import tqdm

from core.config import ALLOWED_SERVICE_KEYS, load_config, load_raw_config, parse_config, validate_config
from core.models import DEFAULT_NAMESERVERS, AppConfig
from core.pipeline import ListBuilderPipeline
from core.reporter import print_aggregation_summary, print_statistics_report
from output.formatter import write_output
from resolvers.asn import resolve_asn
from resolvers.dns import resolve_domains

__all__ = [
    "ALLOWED_SERVICE_KEYS",
    "DEFAULT_NAMESERVERS",
    "ListBuilderPipeline",
    "build_arg_parser",
    "load_config",
    "load_raw_config",
    "main",
    "parse_config",
    "resolve_asn",
    "resolve_domains",
    "validate_config",
]

logger = logging.getLogger(__name__)


def _handle_sigint(sig: int, frame: FrameType | None) -> None:
    """Graceful shutdown при Ctrl+C."""
    logger.info("Received interrupt signal, shutting down...")
    sys.exit(130)


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
    # Регистрация обработчика для graceful shutdown
    signal.signal(signal.SIGINT, _handle_sigint)

    # -- Парсинг аргументов командной строки (CLI) --
    parser = build_arg_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # -- Загрузка и валидация конфигурации --
    config: AppConfig = load_config(args.config)

    # -- Инициализация пайплайна --
    pipeline = ListBuilderPipeline(
        asn_resolver=lambda asn: resolve_asn(asn),
        dns_resolver_factory=lambda cfg: (
            lambda domains: resolve_domains(
                domains,
                timeout=int(cfg.timeout),
                max_workers=cfg.max_workers,
                nameservers=cfg.nameservers,
            )
        ),
    )

    # -- Обработка сервисов через пайплайн с отображением tqdm --
    pbar = tqdm(
        config.services,
        desc="Processing services",
        unit="svc",
        disable=not sys.stdout.isatty(),
    )
    progress_cb = (lambda _name, _idx, _total: pbar.update(1)) if hasattr(pbar, "update") else None
    pipeline_result = pipeline.run(config, progress_callback=progress_cb)
    if hasattr(pbar, "close"):
        pbar.close()

    # -- Вывод сводной статистики --
    print_statistics_report(pipeline_result)

    # Проверяем наличие собранных префиксов до записи
    if not pipeline_result.has_networks:
        logger.error("No IP prefixes were collected; output was not written.")
        sys.exit(1)

    # -- Запись выходного файла только после успешного сбора всех данных --
    sorted_nets = write_output(pipeline_result.service_results, args.output, args.format)
    if not sorted_nets:
        logger.error("No valid IP prefixes after aggregation; output was not written.")
        sys.exit(1)

    print_aggregation_summary(len(sorted_nets), args.output)


if __name__ == "__main__":
    main()
