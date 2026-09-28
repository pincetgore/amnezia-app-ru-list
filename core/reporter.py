"""Console and summary reporting for list generation runs."""

import io
import sys
from typing import TextIO

from core.models import PipelineResult


def format_statistics_report(result: PipelineResult) -> str:
    """Formats the statistical overview and warning sections as a string."""
    buf = io.StringIO()
    buf.write("\n" + "=" * 50 + "\n")
    buf.write("Statistics:\n")
    buf.write("=" * 50 + "\n")

    for stat in result.stats:
        buf.write(f"  {stat.name}: {stat.raw_prefix_count} raw prefixes\n")

    buf.write("-" * 50 + "\n")
    buf.write(f"  Services processed: {len(result.stats)}\n")
    buf.write(f"  Total raw prefixes: {result.total_raw_prefixes}\n")

    if result.asn_warnings:
        buf.write(f"  ASN warnings:       {len(result.asn_warnings)}\n")
        buf.write("\nASNs that could not be resolved or returned no prefixes:\n")
        for item in sorted(set(result.asn_warnings)):
            buf.write(f"  ⚠️  {item}\n")

    if result.dns_warnings:
        buf.write(f"  DNS warnings:       {len(result.dns_warnings)}\n")
        buf.write("\nDomains that could not be resolved:\n")
        for domain in sorted(set(result.dns_warnings)):
            buf.write(f"  ⚠️  {domain}\n")

    return buf.getvalue()


def print_statistics_report(result: PipelineResult, file: TextIO | None = None) -> None:
    """Prints the statistics report to stdout or a designated stream."""
    stream = file if file is not None else sys.stdout
    stream.write(format_statistics_report(result))
    stream.flush()


def print_aggregation_summary(
    aggregated_count: int,
    output_path: str,
    file: TextIO | None = None,
) -> None:
    """Prints post-aggregation stats and destination output path."""
    stream = file if file is not None else sys.stdout
    stream.write(f"  After aggregation:  {aggregated_count}\n")
    stream.write(f"\nOutput: {output_path}\n")
    stream.flush()
