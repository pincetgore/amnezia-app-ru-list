from ipaddress import IPv4Network
from pathlib import Path

import pytest
import yaml

import main as app
from core.config import validate_config
from output.formatter import aggregate_networks, write_output
from resolvers.dns import DNSResolver

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def test_aggregate_cidrs_removes_subnets():
    """Проверяет, что мелкие подсети поглощаются более крупными."""
    ips = [
        IPv4Network("10.0.0.0/8"),
        IPv4Network("10.1.0.0/16"),  # Должно поглотиться первой строкой
        IPv4Network("192.168.1.1/32"),
    ]
    result = aggregate_networks(ips)
    result_strs = [str(net) for net in result]

    assert "10.0.0.0/8" in result_strs
    assert "10.1.0.0/16" not in result_strs, "Вложенная подсеть 10.1.0.0/16 не была удалена!"
    assert "192.168.1.1/32" in result_strs


def test_aggregate_cidrs_ignores_default_route():
    """Проверяет, что 0.0.0.0/0 отфильтровывается и не схлопывает все подсети в 1."""
    ips = [
        IPv4Network("0.0.0.0/0"),
        IPv4Network("10.0.0.0/8"),
        IPv4Network("77.88.0.0/18"),
    ]
    result = aggregate_networks(ips)
    result_strs = [str(net) for net in result]

    assert "0.0.0.0/0" not in result_strs
    assert "10.0.0.0/8" in result_strs
    assert "77.88.0.0/18" in result_strs
    assert len(result) == 2


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"services": [{"name": "Service", "domains": "example.com"}]},
        {"services": [{"name": "Service", "ip_ranges": ["not-a-network"]}]},
        {"services": [{"name": "Service", "domain": ["example.com"]}]},  # Опечатка в ключе: domain вместо domains
        {"services": [{"name": "Service", "extra_field": 123, "domains": ["example.com"]}]},  # Неизвестное поле
        {"services": [{"name": "Service", "domains": [" example.com "]}]},  # Пробелы по краям
        {"services": [{"name": "Service", "domains": ["exam ple.com"]}]},  # Пробел внутри
        {"services": [{"name": "Service", "domains": ["*.example.com"]}]},  # Wildcard домен
        {"services": [{"name": "Service", "domains": ["https://example.com"]}]},  # Схема URL
        {"services": [{"name": "Service", "domains": ["example.com/"]}]},  # Слеш на конце
        {"services": [], "dns": {"nameservers": []}},
        {"services": [], "dns": {"timeout": 0}},
        {"services": [], "dns": {"exclude_asn": 13335}},
        {"services": [], "dns": {"exclude_asn": ["13335"]}},
    ],
)
def test_validate_config_rejects_invalid_values(config):
    """Ошибочная конфигурация должна быть отклонена до сетевых запросов."""
    with pytest.raises(ValueError):
        validate_config(config)


CLI_CONFIG = (
    "services:\n"
    "  - name: TestService\n"
    "    asn: [12345, 23456]\n"
    "    domains: [good.example, bad.example]\n"
    "    ip_ranges: [192.0.2.1/32]\n"
)


def _run_cli(tmp_path: Path, monkeypatch, failing_asns: set[int], failing_domains: set[str]) -> Path:
    """Запускает main() с фейковыми ASN/DNS: указанные в failing_* не резолвятся."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CLI_CONFIG, encoding="utf-8")
    output_path = tmp_path / "ip-list.json"

    def fake_dns(_self, domains):
        return {d: ([], d) if d in failing_domains else ([IPv4Network("198.51.100.1/32")], None) for d in domains}

    monkeypatch.setattr(app.sys, "argv", ["main.py", "-c", str(config_path), "-o", str(output_path)])
    monkeypatch.setattr(app, "resolve_asn", lambda asn: [] if asn in failing_asns else [IPv4Network("203.0.113.0/24")])
    monkeypatch.setattr(DNSResolver, "resolve", fake_dns)
    app.main()
    return output_path


def test_dns_warning_writes_output_and_reports_domain(tmp_path: Path, monkeypatch, capsys):
    """Отдельный недоступный DNS-домен выводится как предупреждение и не останавливает выпуск."""
    output_path = _run_cli(tmp_path, monkeypatch, failing_asns=set(), failing_domains={"bad.example"})
    captured = capsys.readouterr()
    assert output_path.exists()
    assert "Domains that could not be resolved:" in captured.out
    assert "bad.example" in captured.out


def test_asn_warning_writes_output_and_reports_asn(tmp_path: Path, monkeypatch, capsys):
    """Отдельный недоступный или пустой ASN выводится как предупреждение и не останавливает выпуск."""
    output_path = _run_cli(tmp_path, monkeypatch, failing_asns={12345}, failing_domains=set())
    captured = capsys.readouterr()
    assert output_path.exists()
    assert "ASNs that could not be resolved or returned no prefixes:" in captured.out
    assert "AS12345 (TestService)" in captured.out


@pytest.mark.parametrize(
    ("failing_asns", "failing_domains"),
    [
        ({12345, 23456}, set()),
        (set(), {"good.example", "bad.example"}),
    ],
)
def test_mass_failure_keeps_previous_output(tmp_path: Path, monkeypatch, failing_asns, failing_domains):
    """Если легли RIPE или DNS, почти пустой список (только ip_ranges) не публикуется."""
    output_path = tmp_path / "ip-list.json"
    output_path.write_text("previous good list", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        _run_cli(tmp_path, monkeypatch, failing_asns, failing_domains)

    assert exc_info.value.code == 1
    assert output_path.read_text(encoding="utf-8") == "previous good list"


def test_write_output_replaces_existing_file_atomically(tmp_path: Path):
    """Успешная запись заменяет старое содержимое корректным полным JSON."""
    output_path = tmp_path / "ip-list.json"
    output_path.write_text("old and invalid content", encoding="utf-8")

    result = write_output(
        [IPv4Network("192.0.2.2/32"), IPv4Network("192.0.2.1/32")],
        str(output_path),
    )

    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == [
        {"hostname": "192.0.2.1/32", "ip": ""},
        {"hostname": "192.0.2.2/32", "ip": ""},
    ]
    assert not list(tmp_path.glob(".ip-list.json.*.tmp"))
    assert (output_path.stat().st_mode & 0o777) == 0o644
    assert result == [IPv4Network("192.0.2.1/32"), IPv4Network("192.0.2.2/32")]


def test_config_yaml_is_valid():
    """Рабочий config.yaml проходит ту же валидацию, что и при запуске."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        validate_config(yaml.safe_load(f))


@pytest.mark.parametrize("field_name", ["domains", "asn", "ip_ranges"])
def test_no_duplicates_config(field_name):
    """Проверяет отсутствие дубликатов доменов, ASN и IP-диапазонов во всем config.yaml."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    seen_items = {}
    duplicates = []

    for service in config.get("services", []):
        service_name = service.get("name", "Unknown")
        for item in service.get(field_name) or []:
            if item in seen_items:
                duplicates.append(f"{item} (в '{service_name}' и '{seen_items[item]}')")
            else:
                seen_items[item] = service_name

    assert not duplicates, f"Найдены дубликаты в '{field_name}':\n" + "\n".join(duplicates)


def test_loopback_covers_localhost():
    """Проверяет, что диапазон loopback в конфигурации покрывает 127.0.0.1 (localhost)."""
    from ipaddress import IPv4Address

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    local_service = next(s for s in config["services"] if "Локальные сети" in s["name"])
    networks = [IPv4Network(cidr) for cidr in local_service["ip_ranges"]]
    localhost = IPv4Address("127.0.0.1")
    assert any(localhost in net for net in networks), "Диапазон loopback должен покрывать 127.0.0.1"
