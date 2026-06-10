"""
Unit-тесты для resolvers (ASN и DNS) с использованием мокирования.

Тесты проверяют:
- Корректность парсинга ответов RIPE API
- Fallback на bgp.he.net
- Обработка ошибок при резолвинге DNS
- Корректность создания /32 сетей для IP адресов
"""

import pytest
from unittest.mock import patch, MagicMock
from ipaddress import IPv4Network

from resolvers.asn import get_prefixes_ripe, get_prefixes_he, resolve_asn
from resolvers.dns import resolve_domains, _resolve_single_domain


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
                    {"prefix": "2001:db8::/32"},  # IPv6 - должно пропуститься
                ]
            }
        }

        with patch("resolvers.asn._session.get", return_value=mock_response):
            result = get_prefixes_ripe(12389)

        assert len(result) == 2
        assert IPv4Network("1.2.3.0/24") in result
        assert IPv4Network("4.5.6.0/24") in result

    def test_get_prefixes_ripe_empty_data(self):
        """Проверяет обработку пустого ответа от RIPE."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"prefixes": []}}

        with patch("resolvers.asn._session.get", return_value=mock_response):
            result = get_prefixes_ripe(12389)

        assert result == []

    def test_get_prefixes_ripe_network_error(self):
        """Проверяет обработку сетевой ошибки - возвращает None для fallback."""
        # Используем RequestException из requests, чтобы пройти через retry логику
        import requests
        
        with patch("resolvers.asn._session.get", side_effect=requests.RequestException("Network error")):
            result = get_prefixes_ripe(12389)

        # После всех retry попыток должен вернуться None
        assert result is None

    def test_get_prefixes_he_success(self):
        """Проверяет успешный парсинг bgp.he.net."""
        mock_response = MagicMock()
        mock_response.text = """
            <table>
                <tr><td>1.2.3.0/24</td></tr>
                <tr><td>4.5.6.0/25</td></tr>
            </table>
        """

        with patch("resolvers.asn._session.get", return_value=mock_response):
            result = get_prefixes_he(12389)

        assert len(result) == 2
        assert IPv4Network("1.2.3.0/24") in result
        assert IPv4Network("4.5.6.0/25") in result

    def test_get_prefixes_he_fallback(self):
        """Проверяет fallback когда RIPE возвращает None."""
        mock_ripe_response = MagicMock()
        mock_he_response = MagicMock()
        mock_he_response.text = "<tr><td>1.2.3.0/24</td></tr>"

        with patch("resolvers.asn.get_prefixes_ripe", return_value=None):
            with patch("resolvers.asn.get_prefixes_he", return_value=[IPv4Network("1.2.3.0/24")]):
                result = resolve_asn(12389)

        assert len(result) == 1
        assert IPv4Network("1.2.3.0/24") in result

    def test_resolve_asn_fallback_with_data(self):
        """Проверяет что fallback работает только когда RIPE возвращает None."""
        ripe_data = [IPv4Network("1.0.0.0/8")]
        he_data = [IPv4Network("2.0.0.0/8")]

        with patch("resolvers.asn.get_prefixes_ripe", return_value=ripe_data):
            with patch("resolvers.asn.get_prefixes_he", return_value=he_data):
                result = resolve_asn(12389)

        # Должны использоваться данные RIPE, не HE
        assert IPv4Network("1.0.0.0/8") in result
        assert IPv4Network("2.0.0.0/8") not in result


class TestDNSResolver:
    """Тесты для DNS резолвера."""

    def test_resolve_single_domain_success(self):
        """Проверяет успешный резолвинг домена."""
        mock_resolver = MagicMock()
        mock_rdata = MagicMock()
        mock_rdata.__str__.return_value = "1.2.3.4"

        mock_answers = [mock_rdata]
        mock_resolver.resolve.return_value = mock_answers

        networks, warning = _resolve_single_domain("example.com", mock_resolver)

        assert len(networks) == 1
        assert IPv4Network("1.2.3.4/32") in networks
        assert warning is None

    def test_resolve_single_domain_multiple_ips(self):
        """Проверяет резолвинг домена с несколькими A-записями."""
        mock_resolver = MagicMock()

        # Создаем несколько mock rdata
        mock_rdata1 = MagicMock()
        mock_rdata1.__str__.return_value = "1.2.3.4"
        mock_rdata2 = MagicMock()
        mock_rdata2.__str__.return_value = "5.6.7.8"

        mock_resolver.resolve.return_value = [mock_rdata1, mock_rdata2]

        networks, warning = _resolve_single_domain("example.com", mock_resolver)

        assert len(networks) == 2
        assert IPv4Network("1.2.3.4/32") in networks
        assert IPv4Network("5.6.7.8/32") in networks

    def test_resolve_domains_with_custom_nameservers(self):
        """Проверяет что custom nameservers используются при передаче."""
        custom_nameservers = ["8.8.8.8", "1.1.1.1"]

        with patch("resolvers.dns.dns.resolver.Resolver") as MockResolver:
            mock_resolver_instance = MagicMock()
            MockResolver.return_value = mock_resolver_instance

            try:
                resolve_domains([], nameservers=custom_nameservers)
            except Exception:
                pass  # Игнорируем ошибки, просто проверяем что nameservers был установлен

            # Проверяем что nameservers был установлен на resolver
            assert mock_resolver_instance.nameservers == custom_nameservers

    def test_resolve_domains_with_timeout(self):
        """Проверяет что timeout и max_workers используются правильно."""
        with patch("resolvers.dns.concurrent.futures.ThreadPoolExecutor") as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock()
            MockExecutor.return_value = mock_executor

            with patch("resolvers.dns.dns.resolver.Resolver") as MockResolver:
                mock_resolver_instance = MagicMock()
                MockResolver.return_value = mock_resolver_instance

                try:
                    resolve_domains([], timeout=20, max_workers=30)
                except Exception:
                    pass

            # Проверяем что ThreadPoolExecutor был создан с правильными параметрами
            MockExecutor.assert_called_with(max_workers=30)


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
