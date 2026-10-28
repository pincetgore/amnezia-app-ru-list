"""
Резолвер ASN (Autonomous System Number).

Получает анонсированные IPv4-префиксы для ASN через RIPE NCC Stat API.
В качестве резервного источника (fallback) используется парсинг bgp.he.net,
если RIPE API недоступен или возвращает ошибки.
"""

import logging
import re
import time
from ipaddress import IPv4Network
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# URL API для получения префиксов ASN
RIPE_API_URL = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}"
HE_BGP_URL = "https://bgp.he.net/AS{asn}#_prefixes4"

# Предварительно скомпилированное регулярное выражение для поиска CIDR
CIDR_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$")

# Временная метка последнего запроса к API (используется для ограничения скорости)
_last_request_time = 0.0


def _create_session_with_retries() -> requests.Session:
    """Создает requests.Session с автоматическим retry для сетевых сбоев.

    Выполняет до трёх повторных запросов (до четырёх суммарных попыток)
    с exponential backoff при:
    - 429 (Too Many Requests)
    - 500, 502, 503, 504 (Server errors)
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
        }
    )

    # Настройка retry стратегии
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# Переиспользование соединения для производительности (с retry логикой)
_session = _create_session_with_retries()


def _rate_limit(min_interval: float = 1.0) -> None:
    """Обеспечивает минимальный интервал между последовательными запросами к API."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if _last_request_time > 0 and elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_request_time = time.monotonic()


def is_valid_prefix(net: IPv4Network) -> bool:
    """Проверяет валидность IPv4-префикса из BGP или DNS (/32).

    Исключает:
    - Default route (0.0.0.0/0) и чрезмерно широкие суперсети (маска < 8)
    - Неопределенные адреса (0.0.0.0/8)
    - Loopback адреса (127.0.0.0/8)
    - Multicast / Class E (>= 224.0.0.0/4)
    """
    if net.prefixlen < 8 or net.prefixlen > 32:
        return False
    if net.is_unspecified or net.is_loopback or net.is_multicast:
        return False
    return not str(net.network_address).startswith("0.")


class ASNResolver:
    """Резолвер ASN с поддержкой RIPE NCC Stat API и fallback на bgp.he.net."""

    def __init__(
        self,
        session: requests.Session | None = None,
        default_timeout: int = 30,
        rate_limit_interval: float = 1.0,
    ) -> None:
        self.session = session if session is not None else _session
        self.default_timeout = default_timeout
        self.rate_limit_interval = rate_limit_interval

    def _apply_rate_limit(self) -> None:
        _rate_limit(self.rate_limit_interval)

    def get_prefixes_ripe(self, asn: int, timeout: int | None = None) -> list[IPv4Network] | None:
        """Получает анонсированные IPv4-префиксы из RIPE NCC Stat API."""
        self._apply_rate_limit()
        req_timeout = timeout if timeout is not None else self.default_timeout
        try:
            resp = self.session.get(
                RIPE_API_URL.format(asn=quote(str(asn), safe="")),
                timeout=req_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("RIPE API failed for AS%s: %s", asn, e)
            return None

        data_section = data.get("data") if isinstance(data, dict) else None
        if not isinstance(data_section, dict):
            logger.warning("RIPE API returned malformed data for AS%s", asn)
            return None
        entries = data_section.get("prefixes", [])
        prefixes: list[IPv4Network] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            prefix = entry.get("prefix")
            if not prefix or not isinstance(prefix, str) or not CIDR_RE.match(prefix):
                continue
            try:
                net = IPv4Network(prefix, strict=False)
                if is_valid_prefix(net):
                    prefixes.append(net)
            except ValueError:
                continue

        logger.debug("RIPE API AS%s: found %d IPv4 prefixes", asn, len(prefixes))
        return prefixes

    def get_prefixes_he(self, asn: int, timeout: int | None = None) -> list[IPv4Network]:
        """Парсит анонсированные IPv4-префиксы с bgp.he.net (резервный источник)."""
        self._apply_rate_limit()
        req_timeout = timeout if timeout is not None else self.default_timeout
        try:
            resp = self.session.get(
                HE_BGP_URL.format(asn=quote(str(asn), safe="")),
                timeout=req_timeout,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("bgp.he.net request failed for AS%s: %s", asn, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        prefixes: list[IPv4Network] = []
        seen_prefixes: set[str] = set()

        table = soup.find("table", id="table_prefixes4") or soup.find("table")
        search_root = table if table is not None else soup
        for elem in search_root.find_all(["a", "td"]):
            text = elem.get_text().strip()
            if CIDR_RE.match(text) and text not in seen_prefixes:
                seen_prefixes.add(text)
                try:
                    net = IPv4Network(text, strict=False)
                    if is_valid_prefix(net):
                        prefixes.append(net)
                except ValueError:
                    continue

        logger.debug("bgp.he.net AS%s: found %d IPv4 prefixes", asn, len(prefixes))
        return prefixes

    def resolve(self, asn: int, timeout: int | None = None) -> list[IPv4Network]:
        """Получает все IPv4-префиксы для ASN (сначала RIPE, при его сбое — bgp.he.net)."""
        req_timeout = timeout or self.default_timeout
        prefixes = self.get_prefixes_ripe(asn, timeout=req_timeout)
        # Пустой ответ RIPE — ASN ничего не анонсирует; bgp.he.net тогда отдаёт устаревшие префиксы
        if prefixes is not None:
            return prefixes

        logger.info("Falling back to bgp.he.net for AS%s", asn)
        return self.get_prefixes_he(asn, timeout=req_timeout)


_default_asn_resolver = ASNResolver()


def resolve_asn(asn: int) -> list[IPv4Network]:
    """Резолвит ASN общим экземпляром ASNResolver (общая сессия и rate limit)."""
    return _default_asn_resolver.resolve(asn)
