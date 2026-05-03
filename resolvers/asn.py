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
import time
from ipaddress import IPv4Network

import requests

logger = logging.getLogger(__name__)

# Эндпоинт RIPE NCC RISstat API для анонсированных префиксов
RIPE_API_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"

# Hurricane Electric BGP Toolkit — используется как резерв, если RIPE не возвращает данные
HE_BGP_URL = "https://bgp.he.net/AS{asn}#_prefixes4"

# Временная метка последнего запроса к API (используется для ограничения скорости)
_last_request_time = 0.0

# Переиспользование соединения для производительности
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (ru-bypass-list generator)"})

# Мьютекс для потокобезопасного ограничения скорости запросов
_rate_limit_lock = threading.Lock()

def _rate_limit():
    """Обеспечивает минимальный интервал в 1 секунду между последовательными запросами к API."""
    global _last_request_time
    with _rate_limit_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last_request_time = time.time()


def get_prefixes_ripe(asn: int, timeout: int = 30) -> list[IPv4Network] | None:
    """Получает все анонсированные IPv4-префиксы для ASN из RIPE NCC API.

    Возвращает пустой список при сбое (сетевая ошибка, неверный ответ и т.д.),
    чтобы вызывающая функция могла перейти к резервному варианту bgp.he.net.
    """
    _rate_limit()
    try:
        resp = _session.get(
            RIPE_API_URL,
            params={"resource": f"AS{asn}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        prefixes = []
        for entry in data.get("data", {}).get("prefixes", []):
            prefix = entry.get("prefix", "")
            # Пропускаем IPv6-префиксы (содержат двоеточия)
            if ":" in prefix:
                continue
            try:
                prefixes.append(IPv4Network(prefix, strict=False))
            except ValueError:
                logger.warning("Invalid prefix from RIPE for AS%d: %s", asn, prefix)
        logger.info("AS%d: got %d prefixes from RIPE", asn, len(prefixes))
        return prefixes

    except requests.RequestException as e:
        logger.warning("RIPE API failed for AS%d: %s", asn, e)
        return None


def get_prefixes_he(asn: int, timeout: int = 30) -> list[IPv4Network]:
    """Парсит анонсированные IPv4-префиксы с bgp.he.net (резервный вариант).

    Извлекает строки в формате CIDR из HTML-ответа с помощью регулярного выражения.
    Менее надежен, чем RIPE, но полезен, когда RIPE возвращает пустой результат.
    """
    _rate_limit()
    try:
        resp = _session.get(
            HE_BGP_URL.format(asn=asn),
            timeout=timeout,
        )
        resp.raise_for_status()

        # Извлекаем все IPv4 CIDR-строки из HTML-кода страницы
        pattern = r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})'
        raw = re.findall(pattern, resp.text)
        prefixes = []
        for p in raw:
            try:
                prefixes.append(IPv4Network(p, strict=False))
            except ValueError:
                pass
        logger.info("AS%d: got %d prefixes from bgp.he.net (fallback)", asn, len(prefixes))
        return prefixes

    except requests.RequestException as e:
        logger.warning("bgp.he.net failed for AS%d: %s", asn, e)
        return []


def resolve_asn(asn: int) -> list[IPv4Network]:
    """Получает все IPv4-префиксы для ASN.

    Сначала пытается использовать RIPE NCC; если RIPE не возвращает результаты, переключается на bgp.he.net.
    """
    prefixes = get_prefixes_ripe(asn)
    if prefixes is None:
        prefixes = get_prefixes_he(asn)
    return prefixes or []
