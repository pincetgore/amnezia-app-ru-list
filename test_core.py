"""Unit tests for core architecture components (models, config, pipeline, reporter)."""

import io
from ipaddress import IPv4Network
from unittest.mock import MagicMock

import pytest

from core.config import parse_config, validate_config
from core.models import (
    AppConfig,
    DnsConfig,
    PipelineResult,
    ServiceConfig,
    ServiceResult,
    ServiceStats,
)
from core.pipeline import ListBuilderPipeline
from core.reporter import format_statistics_report, print_aggregation_summary, print_statistics_report
from resolvers.asn import ASNResolver
from resolvers.dns import DNSResolver


class TestCoreModels:
    """Tests domain models and their backwards-compatibility behaviors."""

    def test_dns_config_defaults(self):
        dns_cfg = DnsConfig()
        assert len(dns_cfg.nameservers) == 4
        assert "77.88.8.8" in dns_cfg.nameservers
        assert dns_cfg.timeout == 10.0
        assert dns_cfg.max_workers == 20

    def test_service_result_dict_access_compatibility(self):
        net = IPv4Network("192.0.2.0/24")
        result = ServiceResult(name="TestSvc", domains=["test.ru"], networks=[net])

        assert result["name"] == "TestSvc"
        assert result["domains"] == ["test.ru"]
        assert result["networks"] == [net]
        assert result.get("name") == "TestSvc"
        assert result.get("unknown_key", "default") == "default"

        with pytest.raises(KeyError):
            _ = result["non_existent"]

        legacy_dict = result.to_dict()
        assert legacy_dict == {
            "name": "TestSvc",
            "domains": ["test.ru"],
            "networks": [net],
        }

    def test_pipeline_result_metrics(self):
        res1 = ServiceResult(name="S1", networks=[IPv4Network("10.0.0.0/24")])
        res2 = ServiceResult(name="S2", networks=[IPv4Network("10.1.0.0/24")])
        stats = [ServiceStats(name="S1", raw_prefix_count=1), ServiceStats(name="S2", raw_prefix_count=1)]

        pipeline_result = PipelineResult(
            service_results=[res1, res2],
            stats=stats,
            asn_warnings=["AS123 (S1)"],
            dns_warnings=["fail.ru"],
        )

        assert pipeline_result.total_raw_prefixes == 2
        assert pipeline_result.has_networks is True
        assert len(pipeline_result.collect_all_networks()) == 2

    def test_pipeline_result_empty(self):
        empty_result = PipelineResult()
        assert empty_result.total_raw_prefixes == 0
        assert empty_result.has_networks is False
        assert empty_result.collect_all_networks() == []


class TestCoreConfig:
    """Tests configuration parsing and schema validation."""

    def test_parse_config_valid(self):
        raw = {
            "services": [
                {
                    "name": "ServiceA",
                    "asn": [12345],
                    "domains": ["a.ru"],
                    "ip_ranges": ["192.168.0.0/24"],
                }
            ],
            "dns": {
                "nameservers": ["1.1.1.1"],
                "timeout": 5,
                "max_workers": 10,
            },
        }
        validate_config(raw)
        cfg = parse_config(raw)

        assert isinstance(cfg, AppConfig)
        assert len(cfg.services) == 1
        assert cfg.services[0].name == "ServiceA"
        assert cfg.services[0].asn == [12345]
        assert cfg.services[0].domains == ["a.ru"]
        assert cfg.services[0].ip_ranges == ["192.168.0.0/24"]
        assert cfg.dns.nameservers == ["1.1.1.1"]
        assert cfg.dns.timeout == 5.0
        assert cfg.dns.max_workers == 10


class TestCorePipeline:
    """Tests the decoupled ListBuilderPipeline execution engine."""

    def test_pipeline_run_with_custom_resolvers(self):
        mock_asn_func = MagicMock(return_value=[IPv4Network("1.2.3.0/24")])
        mock_dns_func = MagicMock(return_value=([IPv4Network("4.5.6.7/32")], []))

        pipeline = ListBuilderPipeline(
            asn_resolver=mock_asn_func,
            dns_resolver_factory=lambda _cfg: mock_dns_func,
        )

        config = AppConfig(
            services=[
                ServiceConfig(
                    name="TestService",
                    asn=[12345],
                    domains=["test.example"],
                    ip_ranges=["10.0.0.0/24"],
                )
            ]
        )

        callback_calls = []

        def on_progress(name: str, index: int, total: int):
            callback_calls.append((name, index, total))

        result = pipeline.run(config, progress_callback=on_progress)

        assert len(callback_calls) == 1
        assert callback_calls[0] == ("TestService", 0, 1)

        assert len(result.service_results) == 1
        svc_res = result.service_results[0]
        assert svc_res.name == "TestService"
        assert len(svc_res.networks) == 3
        assert IPv4Network("1.2.3.0/24") in svc_res.networks
        assert IPv4Network("4.5.6.7/32") in svc_res.networks
        assert IPv4Network("10.0.0.0/24") in svc_res.networks

        assert len(result.stats) == 1
        assert result.stats[0].raw_prefix_count == 3
        assert result.asn_warnings == []
        assert result.dns_warnings == []

    def test_pipeline_collects_warnings_on_failures(self):
        def failing_asn(_asn):
            return []

        def failing_dns(_domains):
            return [], ["broken.domain"]

        pipeline = ListBuilderPipeline(
            asn_resolver=failing_asn,
            dns_resolver_factory=lambda _cfg: failing_dns,
        )

        config = AppConfig(
            services=[
                ServiceConfig(
                    name="FlakyService",
                    asn=[99999],
                    domains=["broken.domain"],
                    ip_ranges=["invalid-range"],
                )
            ]
        )

        result = pipeline.run(config)

        assert len(result.asn_warnings) == 1
        assert "AS99999 (FlakyService)" in result.asn_warnings[0]
        assert result.dns_warnings == ["broken.domain"]
        assert result.stats[0].raw_prefix_count == 0


class TestCoreReporter:
    """Tests the summary reporter formatting."""

    def test_format_statistics_report_output(self):
        result = PipelineResult(
            service_results=[ServiceResult(name="SvcA", networks=[IPv4Network("1.1.1.0/24")])],
            stats=[ServiceStats(name="SvcA", raw_prefix_count=1)],
            asn_warnings=["AS100 (SvcA)"],
            dns_warnings=["bad.domain"],
        )

        output = format_statistics_report(result)
        assert "Statistics:" in output
        assert "SvcA: 1 raw prefixes" in output
        assert "Services processed: 1" in output
        assert "Total raw prefixes: 1" in output
        assert "ASN warnings:       1" in output
        assert "AS100 (SvcA)" in output
        assert "DNS warnings:       1" in output
        assert "bad.domain" in output

    def test_print_statistics_report_stream(self):
        result = PipelineResult(
            service_results=[],
            stats=[],
            asn_warnings=[],
            dns_warnings=[],
        )
        stream = io.StringIO()
        print_statistics_report(result, file=stream)
        assert "Statistics:" in stream.getvalue()

    def test_print_aggregation_summary(self):
        stream = io.StringIO()
        print_aggregation_summary(42, "custom-output.json", file=stream)
        val = stream.getvalue()
        assert "After aggregation:  42" in val
        assert "Output: custom-output.json" in val


class TestResolverClasses:
    """Tests direct instantiation and methods of ASNResolver and DNSResolver classes."""

    def test_asn_resolver_custom_instance(self):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"prefixes": [{"prefix": "198.51.100.0/24"}]}}
        mock_session.get.return_value = mock_response

        resolver = ASNResolver(session=mock_session, rate_limit_interval=0.0)
        prefixes = resolver.resolve(64500)

        assert len(prefixes) == 1
        assert prefixes[0] == IPv4Network("198.51.100.0/24")

    def test_dns_resolver_custom_instance(self):
        resolver = DNSResolver(nameservers=["8.8.8.8"], timeout=5.0, max_workers=5)
        assert resolver.nameservers == ["8.8.8.8"]
        assert resolver.timeout == 5.0
        assert resolver.max_workers == 5

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"timeout": 0},
            {"max_workers": -1},
            {"nameservers": []},
        ],
    )
    def test_dns_resolver_invalid_init(self, kwargs):
        with pytest.raises(ValueError):
            DNSResolver(**kwargs)
