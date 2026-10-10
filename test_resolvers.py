"""
Unit-тесты для resolvers (ASN и DNS) с использованием мокирования.

Тесты проверяют:
- Корректность парсинга ответов RIPE API
- Fallback на bgp.he.net
- Обработка ошибок при резолвинге DNS
- Корректность создания /32 сетей для IP адресов
"""

from ipaddress import IPv4Network
from unittest.mock import MagicMock, patch

import dns.resolver
import pytest

from core.models import DEFAULT_NAMESERVERS
from resolvers.asn import ASNResolver, is_valid_prefix, resolve_asn
from resolvers.dns import DNSResolver, _resolve_single_domain


class _DummyRdata:
    """Простой эмулятор DNS rdata объекта для тестирования."""

    def __init__(self, address: str) -> None:
        self.address = address

    def __str__(self) -> str:
        return self.address


@pytest.fixture(autouse=True)
def mock_rate_limit():
    """Предотвращает искусственные задержки (sleep) во время тестирования."""
    with patch("resolvers.asn._rate_limit", return_value=None):
        yield


def _resolver(response=None, error=None) -> ASNResolver:
    """ASNResolver с фейковой HTTP-сессией."""
    session = MagicMock()
    if error is not None:
        session.get.side_effect = error
    else:
        session.get.return_value = response
    return ASNResolver(session=session)


class TestASNResolver:
    """Тесты для ASN резолвера."""

    def test_get_prefixes_ripe_success(self):
        """Проверяет успешное получение префиксов из RIPE API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "prefixes": [
                    {"prefix": "1.2.3.0/24"},
                    {"prefix": "4.5.6.0/24"},
                    {"prefix": "0.0.0.0/0"},  # Default route - должно пропуститься
                    {"prefix": "0.0.0.0/8"},  # Unspecified / broad - должно пропуститься
                    {"prefix": "2001:db8::/32"},  # IPv6 - должно пропуститься
                ]
            }
        }

        result = _resolver(mock_response).get_prefixes_ripe(12389)

        assert result is not None
        assert len(result) == 2
        assert IPv4Network("1.2.3.0/24") in result
        assert IPv4Network("4.5.6.0/24") in result
        assert IPv4Network("0.0.0.0/0") not in result

    def test_get_prefixes_ripe_empty_data(self):
        """Проверяет обработку пустого ответа от RIPE."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"prefixes": []}}

        result = _resolver(mock_response).get_prefixes_ripe(12389)

        assert result == []

    def test_get_prefixes_ripe_network_error(self):
        """Проверяет обработку сетевой ошибки - возвращает None для fallback."""
        # Используем RequestException из requests, чтобы пройти через retry логику
        import requests

        result = _resolver(error=requests.RequestException("Network error")).get_prefixes_ripe(12389)

        # После всех retry попыток должен вернуться None
        assert result is None

    def test_get_prefixes_ripe_none_data(self):
        """Проверяет устойчивость к ответу RIPE с data: null."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": None}

        result = _resolver(mock_response).get_prefixes_ripe(12389)

        assert result == []

    def test_get_prefixes_ripe_json_decode_error_returns_none(self):
        """Проверяет обработку некорректного JSON от RIPE (возвращает None для fallback)."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        result = _resolver(mock_response).get_prefixes_ripe(12389)

        assert result is None

    def test_get_prefixes_he_success(self):
        """Проверяет успешный парсинг bgp.he.net с фильтрацией 0.0.0.0/0 и дедупликацией."""
        mock_response = MagicMock()
        mock_response.text = """
            <table>
                <tr><td>0.0.0.0/0</td></tr>
                <tr><td><a href="/net/1.2.3.0/24">1.2.3.0/24</a></td></tr>
                <tr><td><a href="/net/1.2.3.0/24">1.2.3.0/24</a></td></tr>
                <tr><td>2001:db8::/32</td></tr>
                <tr><td>4.5.6.0/24</td></tr>
            </table>
        """

        result = _resolver(mock_response).get_prefixes_he(12389)

        assert len(result) == 2
        assert IPv4Network("1.2.3.0/24") in result
        assert IPv4Network("4.5.6.0/24") in result
        assert IPv4Network("0.0.0.0/0") not in result

    def test_get_prefixes_he_ignores_unrelated_tables(self):
        """Проверяет, что префиксы из других таблиц (peers/IXP) игнорируются при наличии table_prefixes4."""
        mock_response = MagicMock()
        mock_response.text = """
            <table id="table_peers">
                <tr><td><a href="/net/8.8.8.0/24">8.8.8.0/24</a></td></tr>
            </table>
            <table id="table_prefixes4">
                <tr><td><a href="/net/1.2.3.0/24">1.2.3.0/24</a></td></tr>
            </table>
        """

        result = _resolver(mock_response).get_prefixes_he(12389)

        assert len(result) == 1
        assert IPv4Network("1.2.3.0/24") in result
        assert IPv4Network("8.8.8.0/24") not in result

    def test_get_prefixes_he_error(self):
        """Проверяет обработку ошибки при запросе к bgp.he.net."""
        import requests

        result = _resolver(error=requests.RequestException("Network error")).get_prefixes_he(12389)

        assert result == []

    def test_resolve_asn_uses_ripe_first(self):
        """Проверяет приоритет RIPE над bgp.he.net."""
        mock_ripe = [IPv4Network("1.2.3.0/24")]

        with (
            patch.object(ASNResolver, "get_prefixes_ripe", return_value=mock_ripe) as mock_ripe_func,
            patch.object(ASNResolver, "get_prefixes_he") as mock_he_func,
        ):
            result = resolve_asn(12389)

            assert result == mock_ripe
            mock_ripe_func.assert_called_once_with(12389, timeout=30)
            mock_he_func.assert_not_called()

    def test_resolve_asn_fallback_to_he(self):
        """Проверяет fallback на bgp.he.net при сбое RIPE (None)."""
        mock_he = [IPv4Network("4.5.6.0/24")]

        with (
            patch.object(ASNResolver, "get_prefixes_ripe", return_value=None),
            patch.object(ASNResolver, "get_prefixes_he", return_value=mock_he) as mock_he_func,
        ):
            result = resolve_asn(12389)

            assert result == mock_he
            mock_he_func.assert_called_once_with(12389, timeout=30)

    def test_resolve_asn_fallback_to_he_on_empty_ripe(self):
        """Проверяет fallback на bgp.he.net, когда RIPE возвращает пустой список префиксов []."""
        mock_he = [IPv4Network("4.5.6.0/24")]

        with (
            patch.object(ASNResolver, "get_prefixes_ripe", return_value=[]),
            patch.object(ASNResolver, "get_prefixes_he", return_value=mock_he) as mock_he_func,
        ):
            result = resolve_asn(33844)

            assert result == mock_he
            mock_he_func.assert_called_once_with(33844, timeout=30)

    def test_resolve_asn_with_string_format(self):
        """Проверяет корректность обработки строковых ASN (например, 'AS12389')."""
        mock_prefixes = [IPv4Network("1.2.3.0/24")]

        for raw in ("AS12389", "12389"):
            with patch.object(ASNResolver, "get_prefixes_ripe", return_value=mock_prefixes) as mock_ripe:
                result = resolve_asn(raw)
                assert result == mock_prefixes
                mock_ripe.assert_called_once_with(12389, timeout=30)

    def test_resolve_asn_with_invalid_string(self):
        """Проверяет обработку невалидной строки ASN."""
        result = resolve_asn("invalid_asn")
        assert result == []

    @pytest.mark.parametrize("invalid_asn", [True, False, 0, -1, None, [], {}])
    def test_resolve_asn_rejects_non_positive_and_non_int(self, invalid_asn):
        """Проверяет отклонение boolean, неположительных и некорректных типов ASN."""
        assert resolve_asn(invalid_asn) == []


class TestDNSResolver:
    """Тесты для DNS резолвера."""

    def test_dns_resolver_uses_default_nameservers(self):
        """Проверяет, что DNSResolver использует DEFAULT_NAMESERVERS по умолчанию."""
        resolver = DNSResolver()
        assert resolver.nameservers == DEFAULT_NAMESERVERS

    def test_resolve_single_domain_success(self):
        """Проверяет успешный резолвинг домена в /32 сеть."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [_DummyRdata("1.2.3.4")]

        networks, warning = _resolve_single_domain("example.com", mock_resolver)

        assert len(networks) == 1
        assert IPv4Network("1.2.3.4/32") in networks
        assert warning is None

    def test_resolve_single_domain_nxdomain_is_warning(self):
        """NXDOMAIN не должен молча исключаться из отчёта об ошибках."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = dns.resolver.NXDOMAIN()

        networks, warning = _resolve_single_domain("missing.example", mock_resolver)

        assert networks == []
        assert warning == "missing.example"

    def test_resolve_single_domain_multiple_ips(self):
        """Проверяет резолвинг домена с несколькими A-записями."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [_DummyRdata("1.2.3.4"), _DummyRdata("5.6.7.8")]

        networks, warning = _resolve_single_domain("example.com", mock_resolver)

        assert len(networks) == 2
        assert IPv4Network("1.2.3.4/32") in networks
        assert IPv4Network("5.6.7.8/32") in networks
        assert warning is None

    def test_resolve_single_domain_filters_sinkholed_and_loopback_ips(self):
        """Проверяет, что 0.0.0.0, 127.0.0.1 и multicast фильтруются при резолвинге."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [
            _DummyRdata("93.184.216.34"),
            _DummyRdata("0.0.0.0"),
            _DummyRdata("127.0.0.1"),
            _DummyRdata("224.0.0.1"),
        ]

        networks, warning = _resolve_single_domain("example.com", mock_resolver)

        assert len(networks) == 1
        assert IPv4Network("93.184.216.34/32") in networks
        assert warning is None

    def test_is_valid_prefix_for_dns_addresses(self):
        """Общий фильтр is_valid_prefix отсеивает sinkhole/loopback/multicast и для /32 из DNS."""
        assert is_valid_prefix(IPv4Network("93.184.216.34/32")) is True
        assert is_valid_prefix(IPv4Network("0.0.0.0/32")) is False
        assert is_valid_prefix(IPv4Network("127.0.0.1/32")) is False
        assert is_valid_prefix(IPv4Network("224.0.0.1/32")) is False
        assert is_valid_prefix(IPv4Network("0.1.2.3/32")) is False

    def test_resolver_uses_configured_nameservers_and_timeouts(self):
        """Каждый Resolver создаётся с настроенными серверами и таймаутом на сервер."""
        resolver = DNSResolver(nameservers=["8.8.8.8", "1.1.1.1"], timeout=4.0)._create_resolver()

        assert resolver.nameservers == ["8.8.8.8", "1.1.1.1"]
        assert resolver.timeout == 2.0
        assert resolver.lifetime == 4.0

    def test_resolve_deduplicates_and_maps_each_domain(self):
        """Повторяющиеся домены резолвятся один раз; результат — словарь по доменам."""
        calls = []

        def fake_single(domain, _resolver):
            calls.append(domain)
            return ([IPv4Network("1.2.3.4/32")], None) if domain == "ok.ru" else ([], domain)

        with patch("resolvers.dns._resolve_single_domain", side_effect=fake_single):
            result = DNSResolver().resolve(["ok.ru", "bad.ru", "ok.ru"])

        assert sorted(calls) == ["bad.ru", "ok.ru"]
        assert result == {"ok.ru": ([IPv4Network("1.2.3.4/32")], None), "bad.ru": ([], "bad.ru")}

    def test_resolve_empty_list(self):
        assert DNSResolver().resolve([]) == {}

    @pytest.mark.parametrize(
        "kwargs",
        [{"nameservers": []}, {"timeout": 0}, {"max_workers": 0}],
    )
    def test_resolver_rejects_invalid_settings(self, kwargs):
        """Пустые и нулевые параметры не подменяются значениями по умолчанию."""
        with pytest.raises(ValueError):
            DNSResolver(**kwargs)

    def test_resolve_single_domain_idn_punycode(self):
        """Проверяет преобразование кириллического домена в punycode при DNS-запросе."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [_DummyRdata("1.2.3.4")]

        networks, warning = _resolve_single_domain("тест.рф", mock_resolver)

        assert len(networks) == 1
        assert IPv4Network("1.2.3.4/32") in networks
        assert warning is None
        mock_resolver.resolve.assert_called_once_with("xn--e1aybc.xn--p1ai", "A")

    def test_resolve_limits_workers_to_domain_count(self):
        """Проверяет оптимизацию: число воркеров ограничивается числом доменов."""
        import concurrent.futures

        with (
            patch(
                "resolvers.dns.concurrent.futures.ThreadPoolExecutor", wraps=concurrent.futures.ThreadPoolExecutor
            ) as mock_executor_cls,
            patch("resolvers.dns._resolve_single_domain", return_value=([], None)),
        ):
            DNSResolver(timeout=20, max_workers=30).resolve(["a.com", "b.com"])
            mock_executor_cls.assert_called_with(max_workers=2)


class TestNetworkAggregation:
    """Тесты для проверки корректности работы с IPv4Network объектами."""

    def test_ipv4_network_creation_from_single_ip(self):
        """Проверяет создание /32 сети из одного IP."""
        net = IPv4Network("192.168.1.1/32")
        assert str(net) == "192.168.1.1/32"
        assert net.num_addresses == 1

    def test_ipv4_network_creation_from_cidr(self):
        """Проверяет создание сети из CIDR."""
        net = IPv4Network("10.0.0.0/8", strict=False)
        assert str(net) == "10.0.0.0/8"
        assert net.num_addresses == 16777216  # 2^24


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
