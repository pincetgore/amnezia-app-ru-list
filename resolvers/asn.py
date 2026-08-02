"""
Резолвер ASN в префиксы.

Получает все анонсированные IPv4-префиксы для заданного номера автономной системы (ASN).
Основной источник: RIPE NCC RISstat API.
Резервный источник: парсинг HTML с bgp.he.net.

Для предотвращения блокировки со стороны API применяется глобальное ограничение скорости
(минимум 1 секунда между запросами).
"""

import logging
import re
import threading
from collections.abc import Mapping
import time
from ipaddress import IPv4Network
from typing import Any, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Эндпоинт RIPE NCC RISstat API для анонсированных префиксов
RIPE_API_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"

# Hurricane Electric BGP Toolkit — используется как резерв, если RIPE не возвращает данные
HE_BGP_URL = "https://bgp.he.net/AS{asn}#_prefixes4"

# Временная метка последнего запроса к API (используется для ограничения скорости)
_last_request_time = 0.0

# Мьютекс для потокобезопасного ограничения скорости запросов
_rate_limit_lock = threading.Lock()

def _create_session_with_retries() -> requests.Session:
    """Создает requests.Session с автоматическим retry для сетевых сбоев.
    
    Конфигурирует exponential backoff для повторных попыток при:
    - 429 (Too Many Requests)
    - 500, 502, 503, 504 (Server errors)
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (ru-bypass-list generator)"})
    
    # Настройка retry стратегии
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
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
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < 1.0:
            sleep_time = 1.0 - elapsed
            _last_request_time = now + sleep_time
        else:
            _last_request_time = now

    if sleep_time > 0.0:
        time.sleep(sleep_time)


def get_prefixes_ripe(asn: int, timeout: int = 30) -> Optional[List[IPv4Network]]:
    """Получает все анонсированные IPv4-префиксы для ASN из RIPE NCC API.

    Возвращает None при сбое сетевого запроса, чтобы вызывающая функция
    могла перейти к резервному варианту bgp.he.net.
    """
    _rate_limit()
    try:
        resp = _session.get(
            RIPE_API_URL,
            params={"resource": f"AS{asn}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except (ValueError, TypeError) as e:
            logger.warning("Invalid JSON from RIPE for AS%d: %s", asn, e)
            return None

        if not isinstance(data, Mapping):
            logger.warning("Unexpected RIPE response for AS%d: expected object", asn)
            return None
        payload = data.get("data")
        if not isinstance(payload, Mapping):
            logger.warning("Unexpected RIPE response for AS%d: missing data", asn)
            return None
        raw_prefixes = payload.get("prefixes", [])
        if not isinstance(raw_prefixes, list):
            logger.warning("Unexpected RIPE response for AS%d: invalid prefixes", asn)
            return None

        prefixes = []
        for entry in raw_prefixes:
            if not isinstance(entry, Mapping):
                logger.warning("Invalid prefix entry from RIPE for AS%d: %r", asn, entry)
                continue
            prefix = entry.get("prefix", "")
            if not isinstance(prefix, str):
                logger.warning("Invalid prefix from RIPE for AS%d: %r", asn, prefix)
                continue
            # Пропускаем IPv6-префиксы (содержат двоеточия)
            if ":" in prefix:
                continue
            try:
                prefixes.append(IPv4Network(prefix, strict=False))
            except ValueError:
                logger.warning("Invalid prefix from RIPE for AS%d: %s", asn, prefix)
        logger.info("AS%d: got %d prefixes from RIPE", asn, len(prefixes))
        return prefixes

    except (requests.RequestException, ValueError, TypeError, AttributeError) as e:
        logger.warning("RIPE API failed for AS%d: %s", asn, e)
        return None


def get_prefixes_he(asn: int, timeout: int = 30) -> List[IPv4Network]:
    """Парсит анонсированные IPv4-префиксы с bgp.he.net (резервный вариант).

    Извлекает CIDR-префиксы из элементов HTML-страницы с использованием BeautifulSoup.
    Менее надежен, чем RIPE, но полезен, когда RIPE возвращает пустой результат.
    """
    _rate_limit()
    try:
        resp = _session.get(
            HE_BGP_URL.format(asn=asn),
            timeout=timeout,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        prefixes = []
        cidr_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$'

        # Извлекаем префиксы из ссылок и ячеек таблиц
        elements = soup.find_all(["a", "td"])
        for elem in elements:
            text = elem.get_text().strip()
            if re.match(cidr_pattern, text):
                try:
                    prefixes.append(IPv4Network(text, strict=False))
                except ValueError:
                    pass

        # Если не нашли элементы через теги a/td, используем паттерн во всём тексте в качестве запасного сценария
        if not prefixes:
            raw = re.findall(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})', resp.text)
            for p in raw:
                try:
                    prefixes.append(IPv4Network(p, strict=False))
                except ValueError:
                    pass

        prefixes = sorted(set(prefixes), key=lambda network: (int(network.network_address), network.prefixlen))
        logger.info("AS%d: got %d prefixes from bgp.he.net (fallback)", asn, len(prefixes))
        return prefixes

    except (requests.RequestException, ValueError, TypeError) as e:
        logger.warning("bgp.he.net failed for AS%d: %s", asn, e)
        return []


def resolve_asn(asn: Any) -> List[IPv4Network]:
    """Получает все IPv4-префиксы для ASN.

    Сначала пытается использовать RIPE NCC; если RIPE не возвращает результаты (None или []), переключается на bgp.he.net.
    Принимает как целые числа, так и строки (например, "12345" или "AS12345"), нормализуя их.
    """
    original_asn = asn
    if isinstance(asn, bool):
        logger.error("ASN must not be boolean: %r", asn)
        return []
    if isinstance(asn, str):
        asn_clean = asn.strip()
        if not re.fullmatch(r"(?i:AS)?[0-9]+", asn_clean):
            logger.error("Invalid ASN format: '%s'", asn)
            return []
        asn = int(asn_clean[2:] if asn_clean[:2].upper() == "AS" else asn_clean)
    elif not isinstance(asn, int):
        logger.error("ASN must be an int or a string, got: %s", type(asn))
        return []

    if not 0 <= asn <= 4294967295:
        logger.error("ASN out of range: %r", original_asn)
        return []

    prefixes = get_prefixes_ripe(asn)
    if not prefixes:
        prefixes = get_prefixes_he(asn)
    return prefixes or []

