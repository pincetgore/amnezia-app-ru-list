"""
Резолвер ASN (Autonomous System Number).

Получает анонсированные IPv4-префиксы для ASN через RIPE NCC Stat API.
В качестве резервного источника (fallback) используется парсинг bgp.he.net,
если RIPE API недоступен или возвращает ошибки.
"""

import logging
import re
import threading
import time
from ipaddress import IPv4Network
from typing import Any
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
CIDR_RAW_RE = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})")

# Временная метка последнего запроса к API (используется для ограничения скорости)
_last_request_time = 0.0

# Мьютекс для потокобезопасного ограничения скорости запросов
_rate_limit_lock = threading.Lock()


def _create_session_with_retries() -> requests.Session:
    """Создает requests.Session с автоматическим retry для сетевых сбоев.

    Выполняет до трёх повторных запросов (до четырёх суммарных попыток)
    с exponential backoff при:
    - 429 (Too Many Requests)
    - 500, 502, 503, 504 (Server errors)
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
    })

    # Настройка retry стратегии
    retry_strategy = Retry(
        total=3,                                    # До 3 повторов после первоначального запроса
        backoff_factor=0.5,                         # Экспоненциальный backoff: 0.5s, 1s, 2s
        status_forcelist=[429, 500, 502, 503, 504],  # Коды для повтора
        allowed_methods=["GET"],                    # Только GET запросы
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# Переиспользование соединения для производительности (с retry логикой)
_session = _create_session_with_retries()


def _rate_limit():
    """Обеспечивает минимальный интервал в 1 секунду между последовательными запросами к API."""
    global _last_request_time
    sleep_time = 0.0
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if _last_request_time > 0 and elapsed < 1.0:
            sleep_time = 1.0 - elapsed
            _last_request_time = now + sleep_time
        else:
            _last_request_time = now

    if sleep_time > 0.0:
        time.sleep(sleep_time)


def _is_valid_prefix(net: IPv4Network) -> bool:
    """Проверяет валидность полученного BGP IPv4-префикса.

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


def get_prefixes_ripe(asn: int, timeout: int = 30) -> list[IPv4Network] | None:
    """Получает все анонсированные IPv4-префиксы для ASN из RIPE NCC API.

    Возвращает None при сбое сетевого запроса или парсинга, чтобы вызывающая функция
    могла перейти к резервному варианту bgp.he.net.
    """
    _rate_limit()
    try:
        resp = _session.get(
            RIPE_API_URL.format(asn=quote(str(asn), safe="")),
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("RIPE API failed for AS%s: %s", asn, e)
        return None

    data_section = data.get("data") if isinstance(data, dict) else None
    entries = data_section.get("prefixes", []) if isinstance(data_section, dict) else []
    prefixes = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        prefix = entry.get("prefix")
        if not prefix or not isinstance(prefix, str) or not CIDR_RE.match(prefix):
            continue
        try:
            net = IPv4Network(prefix, strict=False)
            if _is_valid_prefix(net):
                prefixes.append(net)
        except ValueError:
            continue

    logger.debug("RIPE API AS%s: found %d IPv4 prefixes", asn, len(prefixes))
    return prefixes


def get_prefixes_he(asn: int, timeout: int = 30) -> list[IPv4Network]:
    """Парсит анонсированные IPv4-префиксы с bgp.he.net (резервный вариант).

    Вызывается только если RIPE NCC API недоступен или возвращает пустые данные.
    """
    _rate_limit()
    try:
        resp = _session.get(
            HE_BGP_URL.format(asn=quote(str(asn), safe="")),
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error("bgp.he.net request failed for AS%s: %s", asn, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    prefixes = []
    seen_prefixes = set()

    for elem in soup.find_all(["a", "td"]):
        text = elem.get_text().strip()
        if CIDR_RE.match(text) and text not in seen_prefixes:
            seen_prefixes.add(text)
            try:
                net = IPv4Network(text, strict=False)
                if _is_valid_prefix(net):
                    prefixes.append(net)
            except ValueError:
                continue

    if not prefixes:
        for p in CIDR_RAW_RE.findall(resp.text):
            if p not in seen_prefixes:
                seen_prefixes.add(p)
                try:
                    net = IPv4Network(p, strict=False)
                    if _is_valid_prefix(net):
                        prefixes.append(net)
                except ValueError:
                    continue

    logger.debug("bgp.he.net AS%s: found %d IPv4 prefixes", asn, len(prefixes))
    return prefixes


def resolve_asn(asn: Any) -> list[IPv4Network]:
    """Получает все IPv4-префиксы для ASN.

    Сначала опрашивает RIPE NCC Stat API; при сбое или пустом результате
    переключается на резервный источник bgp.he.net.
    Возвращает список объектов IPv4Network.
    """
    if isinstance(asn, bool):
        logger.error("Invalid ASN %r: booleans are not valid ASNs", asn)
        return []

    clean_asn = None
    if isinstance(asn, int):
        if asn > 0:
            clean_asn = asn
    elif isinstance(asn, str):
        normalized = asn.strip().upper()
        if normalized.startswith("AS"):
            normalized = normalized[2:]
        if normalized.isdigit():
            val = int(normalized)
            if val > 0:
                clean_asn = val

    if clean_asn is None:
        logger.error("Invalid ASN %r: must be a positive integer (e.g. 12389, 'AS12389')", asn)
        return []

    prefixes = get_prefixes_ripe(clean_asn)
    if prefixes is not None:
        return prefixes

    logger.info("Falling back to bgp.he.net for AS%s", clean_asn)
    return get_prefixes_he(clean_asn)
