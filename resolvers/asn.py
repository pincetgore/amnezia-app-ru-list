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
from typing import List, Optional

import requests
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
        total=3,                                    # Максимум 3 попытки
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
    with _rate_limit_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last_request_time = time.time()


def get_prefixes_ripe(asn: int, timeout: int = 30) -> list[IPv4Network] | None:
    """Получает все анонсированные IPv4-префиксы для AOptional[List[IPv4Network]]

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


def get_prefixes_he(asn: int, timeout: int = 30) -> List[IPv4Network]:
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


def resolve_asn(asn: int) -> List[IPv4Network]:
    """Получает все IPv4-префиксы для ASN.

    Сначала пытается использовать RIPE NCC; если RIPE не возвращает результаты, переключается на bgp.he.net.
    """
    prefixes = get_prefixes_ripe(asn)
    if prefixes is None:
        prefixes = get_prefixes_he(asn)
    return prefixes or []
