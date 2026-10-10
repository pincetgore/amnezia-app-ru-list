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


def _dns_stub(results: dict[str, list[IPv4Network]]):
    """DNS-заглушка: домен из results резолвится, остальные дают предупреждение."""

    def resolve(domains: list[str]) -> dict[str, tuple[list[IPv4Network], str | None]]:
        return {d: (results[d], None) if d in results else ([], d) for d in domains}

    return resolve


class TestCoreModels:
    """Tests domain models and their backwards-compatibility behaviors."""

    def test_dns_config_defaults(self):
        dns_cfg = DnsConfig()
        assert len(dns_cfg.nameservers) == 4
        assert "77.88.8.8" in dns_cfg.nameservers
        assert dns_cfg.timeout == 10.0
        assert dns_cfg.max_workers == 20

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
        assert len(pipeline_result.collect_all_networks()) == 2

    def test_pipeline_result_empty(self):
        empty_result = PipelineResult()
        assert empty_result.total_raw_prefixes == 0
        assert empty_result.failure_reason() is None
        assert empty_result.collect_all_networks() == []

    @pytest.mark.parametrize(
        ("asn_failed", "asn_total", "dns_failed", "domain_total", "blocked"),
        [
            (0, 10, 0, 10, False),
            (5, 10, 5, 10, False),  # ровно половина — ещё допустимо
            (6, 10, 0, 10, True),
            (0, 10, 6, 10, True),
            (0, 0, 0, 0, False),  # только статические ip_ranges
        ],
    )
    def test_failure_reason_blocks_mass_failures(self, asn_failed, asn_total, dns_failed, domain_total, blocked):
        result = PipelineResult(
            asn_warnings=["x"] * asn_failed,
            dns_warnings=["y"] * dns_failed,
            asn_total=asn_total,
            domain_total=domain_total,
        )
        assert (result.failure_reason() is not None) is blocked


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

        pipeline = ListBuilderPipeline(
            asn_resolve=mock_asn_func,
            dns_resolve=_dns_stub({"test.example": [IPv4Network("4.5.6.7/32")]}),
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
        assert result.asn_total == 1
        assert result.domain_total == 1

    def test_pipeline_collects_warnings_on_failures(self):
        pipeline = ListBuilderPipeline(asn_resolve=lambda _asn: [], dns_resolve=_dns_stub({}))

        config = AppConfig(
            services=[
                ServiceConfig(name="FlakyService", asn=[99999], domains=["broken.domain"]),
            ]
        )

        result = pipeline.run(config)

        assert len(result.asn_warnings) == 1
        assert "AS99999 (FlakyService)" in result.asn_warnings[0]
        assert result.dns_warnings == ["broken.domain"]
        assert result.stats[0].raw_prefix_count == 0
        assert result.failure_reason() is not None

    def test_pipeline_resolves_shared_domain_once_for_all_services(self):
        """Домен из нескольких сервисов резолвится один раз, но попадает в каждый сервис."""
        dns_resolve = MagicMock(side_effect=_dns_stub({"shared.ru": [IPv4Network("4.5.6.7/32")]}))
        pipeline = ListBuilderPipeline(asn_resolve=lambda _asn: [], dns_resolve=dns_resolve)
        config = AppConfig(
            services=[
                ServiceConfig(name="A", domains=["shared.ru"]),
                ServiceConfig(name="B", domains=["shared.ru", "bad.ru"]),
            ]
        )

        result = pipeline.run(config)

        dns_resolve.assert_called_once_with(["shared.ru", "shared.ru", "bad.ru"])
        assert [r.networks for r in result.service_results] == [[IPv4Network("4.5.6.7/32")]] * 2
        assert result.dns_warnings == ["bad.ru"]
        assert result.domain_total == 2

    def test_pipeline_marks_all_domains_failed_when_dns_crashes(self):
        def crashing_dns(_domains):
            raise RuntimeError("boom")

        pipeline = ListBuilderPipeline(asn_resolve=lambda _asn: [], dns_resolve=crashing_dns)
        config = AppConfig(services=[ServiceConfig(name="A", domains=["a.ru", "b.ru"])])

        result = pipeline.run(config)

        assert sorted(result.dns_warnings) == ["a.ru", "b.ru"]
        assert result.failure_reason() is not None

    def test_pipeline_default_dns_uses_float_timeout_from_config(self, monkeypatch):
        """Дробный timeout из конфига не обрезается до целого (0.5 -> 0 отключало DNS)."""
        seen = {}

        def fake_resolve(self, domains):
            seen["timeout"] = self.timeout
            return {d: ([IPv4Network("4.5.6.7/32")], None) for d in domains}

        monkeypatch.setattr(DNSResolver, "resolve", fake_resolve)
        config = AppConfig(
            services=[ServiceConfig(name="A", domains=["a.ru"])],
            dns=DnsConfig(timeout=0.5),
        )

        result = ListBuilderPipeline(asn_resolve=lambda _asn: []).run(config)

        assert seen["timeout"] == 0.5
        assert result.dns_warnings == []


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

    def test_asn_resolver_falls_back_to_he_when_ripe_empty(self):
        ripe = MagicMock()
        ripe.json.return_value = {"data": {"prefixes": []}}
        he = MagicMock(text='<table id="table_prefixes4"><tr><td>203.0.113.0/24</td></tr></table>')
        session = MagicMock()
        session.get.side_effect = [ripe, he]

        prefixes = ASNResolver(session=session, rate_limit_interval=0.0).resolve("AS64500")

        assert prefixes == [IPv4Network("203.0.113.0/24")]
        assert "bgp.he.net" in session.get.call_args_list[1].args[0]

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
