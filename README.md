# amnezia-app-ru-list

[![Deploy](https://img.shields.io/github/actions/workflow/status/pincetgore/amnezia-app-ru-list/deploy.yml?style=for-the-badge&logo=github&label=Deploy)](https://github.com/pincetgore/amnezia-app-ru-list/actions)
[![License](https://img.shields.io/badge/LICENSE-MIT-F6C25B?style=for-the-badge&logo=opensourceinitiative&logoColor=white&labelColor=555555)](#)

## ⚠️ Юридическая информация

> **Этот проект создан исключительно в ознакомительных и исследовательских целях.**
>
> **Никакие материалы этого проекта не являются призывом к нарушению законов.**

## Описание проекта

Автоматически генерируемый список IP-адресов и доменов российских сервисов для **split tunneling** для Amnezia.

Трафик к сервисам из списка идёт **напрямую**, минуя VPN. Всё остальное (включая заблокированные ресурсы) продолжает идти через VPN.

> Готовые файлы обновляются еженедельно и доступны на странице **Releases**.

---

## Как это работает

```
          Ваше устройство
┌──────────────────────────────────┐
│        Браузер / Приложение      │
│                │                 │
│                ▼                 │
│  ┌───────────────────────────┐   │
│  │         AmneziaVPN        │   │
│  │       Split Tunneling     │   │
│  └──────┬─────────────┬──────┘   │
│         │             │          │
│   Совпало с      Не совпало      │
│   ip-list.json   с ip-list.json  │
│         │             │          │
│         ▼             ▼          │
│    Напрямую      Через Amnezia   │
│   (sberbank,    (telegram,       │
│    rzd, wb)     youtube и др.)   │
└──────────────────────────────────┘
```

### Источники данных

1. **RIPE NCC API** (основной) — все анонсированные IPv4-префиксы по ASN организации
2. **DNS A-записи** (дополнительный) — многопоточный резолвинг доменов (через публичные DNS) для сервисов без выделенного ASN
3. **bgp.he.net** (fallback) — если RIPE API не отвечает

Скрипт собирает CIDR-диапазоны через ASN, дополняет их IP-адресами из DNS, агрегирует (убирает дубли и вложенные подсети), и формирует `ip-list.json` в формате AmneziaVPN.

---

## Быстрый старт

### Вариант 1: Скачать готовый файл

1. Перейдите на страницу **Releases**.
2. Скачайте файл `ip-list-<дата_время>.json` из последнего релиза.
3. Импортируйте в AmneziaVPN (см. инструкцию ниже).

### Вариант 2: Сгенерировать самостоятельно

```bash
git clone https://github.com/pincetgore/amnezia-app-ru-list.git
cd amnezia-app-ru-list
pip install -r requirements.txt
python main.py
```

Результат — файл `ip-list.json` в текущей директории.

### Параметры CLI

| Флаг | Описание | По умолчанию |
|------|----------|--------------|
| `-o`, `--output` | Путь к выходному файлу | `ip-list.json` |
| `-f`, `--format` | Формат: `amnezia` или `plain` | `amnezia` |
| `-c`, `--config` | Путь к `config.yaml` | `config.yaml` |
| `-v`, `--verbose` | Подробный лог (debug) | выключен |

```bash
# Сгенерировать в другой файл
python main.py -o my-list.json

# Простой текстовый формат (по одному CIDR на строку)
python main.py -f plain -o cidrs.txt

# Подробный лог для отладки
python main.py -v
```

---

## Импорт в AmneziaVPN

### IP-маршрутизация (для браузера и веб-сервисов)

1. Откройте **AmneziaVPN**
2. Перейдите в **Настройки** соединения
3. Откройте **Раздельное туннелирование сайтов**
4. Выберите режим: **"Адреса из списка НЕ должны открываться через VPN"**
5. Нажмите **":"** (три точки) -> **Импорт** -> выберите скачанный файл `ip-list-<дата_время>.json`
6. Домены и IP-диапазоны загрузятся в список исключений

### Исключение приложений (только для Android и Windows)

> **Важно:** Многие российские приложения (банки, маркетплейсы, РЖД) определяют наличие VPN через Android API (`ConnectivityManager`), проверяя активный VPN-интерфейс. IP-маршрутизация здесь не поможет — приложение видит VPN-туннель вне зависимости от маршрутов.

**Решение:** используйте раздельное туннелирование **по приложениям**:

1. Откройте **AmneziaVPN**
2. Перейдите в **Настройки** -> **Раздельное туннелирование приложений**
3. Выберите режим: **"Выбранные приложения НЕ должны открываться через VPN"**
4. Добавьте приложения, которые ругаются на VPN:
   - ВТБ, Сбербанк, Тинькофф, Альфа-Банк и др. банки
   - Wildberries, Ozon, Авито
   - РЖД, Аэрофлот
   - 2ГИС, Яндекс.Карты, Яндекс Go
   - Госуслуги
   - и другие

Эти приложения перестанут видеть VPN-интерфейс и будут работать как обычно.

> **Рекомендуется использовать оба метода одновременно:** исключение приложений + IP-список. Приложения — для мобильных приложений, IP-список — для браузера.

---

## Включённые сервисы (124 записи)

### Технологии / Поисковики / Суперапы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Яндекс | AS13238, AS44534 и др. | `yandex.ru`, `yandex.net`, `ya.ru` и др. |
| ВКонтакте | AS28709, AS47541 и др. | `vk.com`, `vk.ru`, `userapi.com` и др. |
| Mail.ru + Одноклассники | AS47764 | `mail.ru`, `ok.ru`, `cloud.mail.ru` и др. |
| Max | -- | `max.ru`, `apptracer.ru`, `mycdn.me` и др. |
| Aliexpress | AS45102 | `aliexpress.ru` |

### Банки
| Сервис | ASN | Домены |
|--------|-----|--------|
| Сбербанк | AS33844, AS35237 и др. | `sberbank.ru`, `online.sberbank.ru`, `sber.ru` и др. |
| Тинькофф / Т-Банк | AS205638, AS12686 и др. | `tbank.ru`, `tinkoff.ru` и др. |
| ВТБ | AS24823, AS34662 и др. | `vtb.ru`, `online.vtb.ru` |
| Альфа-Банк | AS15632, AS34838 и др. | `alfabank.ru`, `alfadirect.ru`, `alfa.me` |
| Газпромбанк | AS35022, AS48033 и др. | `gazprombank.ru`, `gpb.ru` |
| Россельхозбанк | AS41615 | `rshb.ru`, `online.rshb.ru` |
| Промсвязьбанк | -- | `psbank.ru` |
| Совкомбанк | AS34155, AS34336 и др. | `sovcombank.ru`, `halvacard.ru` |
| Райффайзен Банк | -- | `raiffeisen.ru`, `online.raiffeisen.ru` |
| Московский Кредитный Банк | AS39267, AS50464, AS202273 | `mkb.ru`, `online.mkb.ru` |
| Открытие | AS5589, AS25296 и др. | `open.ru` |
| Росбанк | -- | `rosbank.ru` |
| Банк Россия | AS50640, AS196796 и др. | `abr.ru` |
| ЮMoney | -- | `yoomoney.ru`, `yookassa.ru` |
| СБП / НСПК | AS21292, AS41185 и др. | `nspk.ru`, `sbp.nspk.ru` |

### Телеком
| Сервис | Домены |
|--------|--------|
| МТС | `mts.ru`, `payment.mts.ru`, `kion.ru` и др. |
| МегаФон | `megafon.ru`, `lk.megafon.ru` |
| Билайн / Вымпелком | `beeline.ru`, `my.beeline.ru` |
| Теле2 | `tele2.ru`, `my.tele2.ru` |
| Ростелеком | `rt.ru`, `rostelecom.ru`, `wink.ru` и др. |
| Дом.ру / ЭР-Телеком | `domru.ru`, `lk.domru.ru` |

### E-commerce / Маркетплейсы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Wildberries | AS49053, AS57073 и др. | `wildberries.ru`, `wb.ru` и др. |
| Ozon | AS207986 | `ozon.ru`, `ozon.app`, `ozone.ru` и др. |
| Авито | AS201012 | `avito.ru`, `avito.st` |
| Яндекс.Маркет | -- | `market.yandex.ru`, `pokupki.market.yandex.ru` и др. |
| KazanExpress / Магнит Маркет | AS57319, AS60691 | `kazanexpress.ru`, `magnit.market` и др. |
| СберМегаМаркет | -- | `sbermegamarket.ru`, `megamarket.ru` |
| Lamoda | AS57906 | `lamoda.ru`, `lamoda.co` |
| DNS Shop | -- | `dns-shop.ru`, `dns-shop.net` |
| М.Видео / Эльдорадо | -- | `mvideo.ru`, `eldorado.ru` |
| Ситилинк | -- | `citilink.ru` |
| Леруа Мерлен | -- | `leroymerlin.ru`, `lemanapro.ru` |
| Золотое Яблоко | -- | `goldapple.ru` |
| Детский мир | -- | `detmir.ru` |
| Hoff | -- | `hoff.ru` |

### Еда / Доставка / Такси
| Сервис | Домены |
|--------|--------|
| Яндекс Еда / Лавка / Такси | `eda.yandex.ru`, `lavka.yandex.ru`, `taxi.yandex.ru`, `go.yandex.ru` |
| Самокат | `samokat.ru` |
| Delivery Club | `delivery-club.ru` |
| ВкусВилл | `vkusvill.ru`, `online.vkusvill.ru` |
| СДЭК | `cdek.ru`, `lk.cdek.ru` и др. |
| Boxberry | `boxberry.ru` |

### Ритейл / Продукты
| Сервис | ASN | Домены |
|--------|-----|--------|
| Пятёрочка / X5 Group | AS198027, AS215810 и др. | `5ka.ru`, `perekrestok.ru`, `vprok.ru`, `x5.ru` и др. |
| Магнит | AS57319, AS60691 | `magnit.ru`, `dostavka.magnit.ru` |
| Лента | -- | `lenta.com`, `online.lenta.com` |
| Metro Cash and Carry | AS210756 | `metro-cc.ru`, `online.metro-cc.ru` |
| FixPrice | -- | `fix-price.com`, `fix-price.ru` |
| Светофор | -- | `svetofor.info` |
| Дикси | AS202760, AS51115 | `dixy.ru` |

### Стриминг / Видео / Музыка
| Сервис | ASN | Домены |
|--------|-----|--------|
| Кинопоиск | -- | `kinopoisk.ru`, `hd.kinopoisk.ru`, `api.kinopoisk.ru` |
| Rutube | AS207353 | `rutube.ru`, `static.rutube.ru` |
| IVI | -- | `ivi.ru`, `ivi.tv`, `api.ivi.ru` |
| Okko | -- | `okko.tv`, `api.okko.tv` |
| KION (МТС) | -- | `kion.ru`, `api.kion.ru` |
| Wink (Ростелеком) | -- | `wink.ru`, `api.wink.ru` |
| START | -- | `start.ru`, `start.video` |
| Premier | -- | `premier.one`, `api.premier.one` |
| Яндекс Музыка | -- | `music.yandex.ru`, `api.music.yandex.net` |
| Звук (Сбер) | -- | `zvuk.com`, `sberaudio.ru` |
| VK Видео | -- | `vkvideo.ru`, `video.vk.com` |

### Государственные сервисы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Госуслуги | -- | `gosuslugi.ru`, `esia.gosuslugi.ru` и др. |
| ФНС / Налоговая | -- | `nalog.gov.ru`, `lkfl2.nalog.ru`, `lkip2.nalog.ru` |
| Мос.ру | -- | `mos.ru`, `my.mos.ru`, `uslugi.mos.ru` |
| ЦБ РФ | -- | `cbr.ru`, `finmarket.ru` |
| Почта России | -- | `pochta.ru`, `tracking.pochta.ru` |

### Транспорт / Путешествия
| Сервис | ASN | Домены |
|--------|-----|--------|
| РЖД | AS20702, AS28991 | `rzd.ru`, `ticket.rzd.ru`, `pass.rzd.ru` |
| Аэрофлот | -- | `aeroflot.ru`, `api.aeroflot.ru`, `booking.aeroflot.ru` |
| S7 Airlines | -- | `s7.ru`, `s7airlines.com` |
| Победа | -- | `pobeda.aero`, `booking.pobeda.aero` |
| Уральские авиалинии | -- | `uralairlines.ru` |
| Aviasales | -- | `aviasales.ru`, `aviasales.com` |
| Tutu.ru | -- | `tutu.ru`, `api.tutu.ru` |
| Островок | -- | `ostrovok.ru`, `api.ostrovok.ru` |
| Яндекс.Путешествия | -- | `travel.yandex.ru` |
| Суточно.ру | -- | `sutochno.ru` |
| Московский метрополитен | -- | `mosmetro.ru`, `wi-fi.ru` |
| Тройка | -- | `transport.mos.ru`, `troika.mos.ru` |

### Недвижимость
| Сервис | Домены |
|--------|--------|
| ЦИАН | `cian.ru`, `api.cian.ru` |
| Домклик (Сбер) | `domclick.ru`, `api.domclick.ru` |
| ДомРФ | `domrf.ru` |

### Работа / HR
| Сервис | ASN | Домены |
|--------|-----|--------|
| HeadHunter | AS47724, AS59601 | `hh.ru`, `api.hh.ru`, `headhunter.ru` |
| SuperJob | -- | `superjob.ru` |
| Работа.ру | -- | `rabota.ru` |
| Хабр | -- | `habr.com`, `career.habr.com` |

### Авто
| Сервис | Домены |
|--------|--------|
| Авто.ру (Яндекс) | `auto.ru`, `api.auto.ru` |
| Drom.ru | `drom.ru`, `auto.drom.ru` |
| Автотека | `autoteka.ru` |

### Карты / Навигация / Гео
| Сервис | ASN | Домены |
|--------|-----|--------|
| 2ГИС | AS197482 | `2gis.ru`, `api.2gis.ru`, `tile.2gis.com` и др. |
| Яндекс.Карты | -- | `maps.yandex.ru`, `core-renderer-tiles.maps.yandex.net` |

### Образование
| Сервис | Домены |
|--------|--------|
| Яндекс Практикум | `practicum.yandex.ru` |
| Skillbox | `skillbox.ru` |
| GeekBrains | `geekbrains.ru`, `gb.ru` |
| Нетология | `netology.ru` |
| Skyeng | `skyeng.ru`, `student.skyeng.ru` |

### Медицина / Здоровье
| Сервис | Домены |
|--------|--------|
| ДокторНаРаботе / СберЗдоровье | `sberhealth.ru`, `doctoronline.ru` |
| Аптека.ру | `apteka.ru` |
| Еаптека | `eapteka.ru` |

### Мессенджеры / Соцсети
| Сервис | Домены |
|--------|--------|
| Дзен | `dzen.ru`, `zen.yandex.ru` |
| TenChat | `tenchat.ru` |

### Игры
| Сервис | Домены |
|--------|--------|
| VK Play | `vkplay.ru`, `api.vkplay.ru` |
| MY.GAMES | `my.games`, `api.my.games` |

### Облака / Хостинг
| Сервис | Домены |
|--------|--------|
| Яндекс.Облако | `cloud.yandex.ru`, `yandex.cloud`, `storage.yandexcloud.net` |
| VK Cloud | `cloud.vk.com`, `mcs.mail.ru` |
| Selectel | `selectel.ru` |
| REG.RU | `reg.ru` |

### Финтех / Инвестиции
| Сервис | Домены |
|--------|--------|
| Тинькофф Инвестиции | `invest-gw.tinkoff.ru` |
| СберИнвестиции | `sberinvestor.ru` |
| ВТБ Мои Инвестиции | `broker.vtb.ru` |
| Мосбиржа | `moex.com` |

### Другое
| Сервис | ASN | Домены |
|--------|-----|--------|
| Wildberries Банк | -- | `wb-bank.ru` |
| Литрес | -- | `litres.ru` |
| 1С | -- | `1c.ru`, `1c-bitrix.ru` |
| Битрикс24 | -- | `bitrix24.ru`, `b24.io` |
| AmoCRM | -- | `amocrm.ru`, `amocrm.com` |
| Контур | -- | `kontur.ru`, `extern.kontur.ru`, `elba.kontur.ru` |
| Kaspersky | AS200187 | `kaspersky.ru`, `kaspersky.com` |
| Dr.Web | -- | `drweb.ru`, `drweb.com` |
| Ozon Банк | -- | `ozonbank.ru` |
| Юла | -- | `youla.ru` |
| Яндекс.Доставка | -- | `dostavka.yandex.ru` |

---

## Как добавить свой сервис

Добавьте запись в `config.yaml`:

```yaml
  - name: "Название сервиса"
    asn:
      - 12345          # ASN можно найти на https://bgp.he.net
    domains:
      - example.ru     # Домены для DNS-резолвинга
      - api.example.ru
```

Если ASN неизвестен или сервис использует облачный хостинг, оставьте `asn: []` — будут использованы только DNS A-записи.

Затем перегенерируйте список:

```bash
python main.py
```

---

## Тестирование

В проекте настроено автоматическое тестирование с помощью фреймворка `pytest`. Тесты защищают проект от публикации сломанных списков маршрутизации из-за опечаток в конфиге или сбоев логики.

**Что проверяется:**
1. **Агрегация IP-сетей**: алгоритм схлопывания подсетей (например, поглощение мелкой `10.1.0.0/16` более крупной `10.0.0.0/8`).
2. **Структура `config.yaml`**:
   - Конфиг является валидным словарем и содержит базовый ключ `services`.
   - У каждого добавленного сервиса есть обязательное поле `name`.
   - У сервиса обязательно присутствует хотя бы одно из полей `asn` или `domains`.
   - В полях `asn` содержатся строго числовые значения.
3. **Валидность доменов**: в списке доменов нет частых опечаток:
   - Отсутствует префикс протокола (например, `http://` или `https://`).
   - Отсутствует закрывающий слеш (`/`) на конце.
   - Нет случайных пробелов внутри строки.
   - Не используются неподдерживаемые wildcard-записи (`*.domain.com`).

**Как запустить тесты локально:**
```bash
pip install pytest pyyaml
pytest
```

---

## Автообновление

GitHub Actions workflow запускается **каждый понедельник в 04:00 UTC** и автоматически:
1. Прогоняет тесты (`pytest`), проверяя структуру `config.yaml`, валидность доменов и алгоритм склейки сетей.
2. Запрашивает актуальные данные из RIPE и многопоточно резолвит DNS.
3. Генерирует `ip-list.json` (для Amnezia) и `cidrs.txt` (простой список) с подробной статистикой и списком проблемных доменов (warnings) в логах.
4. Создаёт/обновляет релиз `latest` и загружает в него сгенерированные файлы.

---

## Почему без ASN для телекомов?

МТС (AS8359), МегаФон (AS31133), Билайн (AS3216), Ростелеком (AS12389) — это интернет-провайдеры с сотнями/тысячами IP-префиксов. Включение их полных ASN-диапазонов перегружает маршрутную таблицу Android (появляется восклицательный знак на иконке VPN) и может вызвать сбои. Для работы личных кабинетов операторов достаточно DNS-резолвинга их доменов.

---

## Лицензия

MIT
