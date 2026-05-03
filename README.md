<img width="1584" height="672" alt="trikolor" src="https://github.com/user-attachments/assets/5afaee38-442a-499f-a49b-f8ebb6820d2d" />

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
[![Update](https://img.shields.io/github/actions/workflow/status/pincetgore/amnezia-app-ru-list/update.yml?style=for-the-badge&logo=github&label=UPDATE)](https://github.com/pincetgore/amnezia-app-ru-list/actions/workflows/update.yml)
![Tests](https://img.shields.io/badge/Unit_Tests-Passing-brightgreen?style=for-the-badge)
![Data Source](https://img.shields.io/badge/Data_Source-RIPE_NCC_API-ea580c?style=for-the-badge)
[![License](https://img.shields.io/badge/LICENSE-MIT-F6C25B?style=for-the-badge&logo=opensourceinitiative&logoColor=white&labelColor=555555)](#)

## ⚠️ Юридическая информация

> **Этот проект создан исключительно в ознакомительных и исследовательских целях.**
>
> **Никакие материалы этого проекта не являются призывом к нарушению законов.**

# Оглавление
- [Описание проекта](#описание-проекта)
  - [Источники данных](#источники-данных)
  - [Автообновление](#автообновление)
  - [Тесты](#тесты)
  - [Включённые сервисы](#включённые-сервисы-117-записей)
- [Инструкция по применению](#инструкция-по-применению)
  - [Получение актуального списка](#получение-актуального-списка)
  - [Настройка приложения AmneziaVPN](#настройте-приложение-amneziavpn)
- [Локальное развертывание](#локальное-развертывание)
  - [Добавление нового сервиса](#как-добавить-свой-сервис)
  - [Ручной запуск тестов](#как-запустить-тесты-самостоятельно)
  - [Параметры CLI](#параметры-cli)

# Описание проекта

Автоматически генерируемый список IP-адресов и доменов российских сервисов для **split tunneling** для Amnezia.

Трафик к сервисам из списка идёт **напрямую**, минуя VPN. Всё остальное (включая заблокированные ресурсы) продолжает идти через VPN.

```
           Ваше устройство
┌──────────────────────────────────┐
│        Браузер / Приложение      │
│                │                 │
│                ▼                 │
│  ┌───────────────────────────┐   │
│  │         AmneziaVPN        │   │
│  │       Split Tunneling     │   │
│  └─────┬───────────────┬─────┘   │
│        │               │         │
│     Совпало с     Не совпало c   │
│   ip-list.json    ip-list.json   │
│        │               │         │
│        ▼               ▼         │
│     Напрямую     Через Amnezia   │
│ (Сбербанк, РЖД,   (Telegram,     │
│    WB и др.)     Youtube и др.)  │
└──────────────────────────────────┘
```

---

## Источники данных

1. **RIPE NCC API** (основной) — все анонсированные IPv4-префиксы по ASN организации
2. **DNS A-записи** (дополнительный) — многопоточный резолвинг доменов (через публичные DNS) для сервисов без выделенного ASN
3. **bgp.he.net** (fallback) — если RIPE API не отвечает
4. **Статические подсети и IP-адреса (ip_ranges / ip-tables)** — явно заданные в конфигурации диапазоны

Скрипт собирает CIDR-диапазоны через ASN, дополняет их IP-адресами из DNS и статическими правилами, агрегирует (убирает дубли и вложенные подсети) и формирует в виде `ip-list-<дата_время>.json` в формате AmneziaVPN. 
Готовые файлы обновляются еженедельно и доступны на странице **Releases**.

## Автообновление

GitHub Actions workflow запускается **каждый понедельник в 04:00 UTC** и автоматически:
1. Прогоняет тесты (`pytest`), проверяя структуру `config.yaml`, валидность доменов и алгоритм склейки сетей.
2. Запрашивает актуальные данные из RIPE и многопоточно резолвит DNS.
3. Генерирует `ip-list.json` (для Amnezia) и `cidrs.txt` (простой список) с подробной статистикой и списком проблемных доменов (warnings) в логах.
4. Создаёт/обновляет релиз и загружает в него сгенерированные файлы.

## Тесты

В проекте настроено автоматическое тестирование с помощью фреймворка `pytest`. Тесты защищают проект от публикации сломанных списков маршрутизации из-за опечаток в конфиге или сбоев логики.

**Что проверяется:**
1. **Агрегация IP-сетей**: алгоритм схлопывания подсетей (например, поглощение мелкой `10.1.0.0/16` более крупной `10.0.0.0/8`).
2. **Структура `config.yaml`**:
   - Конфиг является валидным словарем и содержит базовый ключ `services`.
   - У каждого добавленного сервиса есть обязательное поле `name`.
   - У сервиса обязательно присутствует хотя бы одно из полей `asn`, `domains` или `ip_ranges`.
   - В полях `asn` содержатся строго числовые значения.
3. **Валидность доменов**: в списке доменов нет частых опечаток:
   - Отсутствует префикс протокола (например, `http://` или `https://`).
   - Отсутствует закрывающий слеш (`/`) на конце.
   - Нет случайных пробелов внутри строки.
   - Не используются неподдерживаемые wildcard-записи (`*.domain.com`).
4. **Уникальность записей**: во всем `config.yaml` отсутствуют дубликаты (защита от ошибок при добавлении):
   - Домены не повторяются в разных сервисах.
   - ASN уникальны (предотвращает лишние запросы к RIPE API).
   - Статически заданные `ip_ranges` не дублируются.

## Включённые сервисы (117 записей)

### Локальные и служебные сети
В список по умолчанию включены диапазоны частных сетей (LAN), CGNAT и Multicast. Это гарантирует, что при включенном VPN у вас не пропадет доступ к домашнему роутеру, локальным ресурсам и устройствам умного дома.

| Сервис | IP-диапазоны |
|--------|--------------|
| Локальные сети (LAN, CGNAT, Multicast) | `10.0.0.0/8`, `100.64.0.0/10`, `169.254.0.0/16`, `172.16.0.0/12`, `192.168.0.0/16`, `224.0.0.0/4` |

### Бигтех / Супераппы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Яндекс | AS13238, AS44534 и др. | `yandex.ru`, `ya.ru`, `kinopoisk.ru`, `dzen.ru` и др. |
| ВКонтакте | AS28709, AS47541 и др. | `vk.com`, `mvk.com`, `vkvideo.ru`, `cloud.vk.com` и др. |
| Mail.ru + Одноклассники | AS47764, AS49797 и др. | `mail.ru`, `ok.ru`, `cloud.mail.ru` и др. |

### Банки
| Сервис | ASN | Домены |
|--------|-----|--------|
| Сбербанк | AS33844, AS35237 и др. | `sberbank.ru`, `sber.ru`, `sberinvestor.ru` и др. |
| Т-Банк | AS12686, AS205638 и др. | `tbank.ru`, `tinkoff.ru`, `invest-gw.tinkoff.ru` и др. |
| ВТБ | AS24823, AS39154 и др. | `vtb.ru`, `online.vtb.ru`, `invest.vtb.ru` |
| Альфа-Банк | AS15632, AS34838 и др. | `alfabank.ru`, `alfadirect.ru`, `alfa.me` |
| Газпромбанк | AS35022, AS48033 и др. | `gazprombank.ru`, `gpb.ru` |
| Россельхозбанк | AS41615 | `rshb.ru`, `online.rshb.ru` |
| Промсвязьбанк | -- | `psbank.ru` |
| Совкомбанк | AS51136, AS197258 и др. | `sovcombank.ru`, `halvacard.ru` |
| Райффайзен Банк | -- | `raiffeisen.ru`, `online.raiffeisen.ru` |
| Московский Кредитный Банк | AS39267, AS50464, AS202273 | `mkb.ru`, `online.mkb.ru` |
| Открытие | AS5589 | `open.ru` |
| Росбанк | -- | `rosbank.ru` |
| Банк Россия | AS50640, AS196796 и др. | `abr.ru` |
| ЮMoney | AS43247 | `yoomoney.ru`, `yookassa.ru` |
| СБП / НСПК | AS21292, AS41185 и др. | `nspk.ru`, `sbp.nspk.ru` |
| Wildberries Банк | -- | `wb-bank.ru` |
| Ozon Банк | -- | `ozonbank.ru` |

### Телеком
МТС (AS8359), МегаФон (AS31133), Билайн (AS3216), Ростелеком (AS12389) — это интернет-провайдеры с сотнями/тысячами IP-префиксов. Включение их полных ASN-диапазонов перегружает маршрутную таблицу Android (появляется восклицательный знак на иконке VPN) и может вызвать сбои. Для работы личных кабинетов операторов достаточно DNS-резолвинга их доменов.

| Сервис | Домены |
|--------|--------|
| МТС | `mts.ru`, `payment.mts.ru`, `login.mts.ru` |
| МегаФон | `megafon.ru`, `lk.megafon.ru` |
| Билайн | `beeline.ru`, `my.beeline.ru` |
| Теле2 | `tele2.ru`, `my.tele2.ru` |
| Ростелеком | `rt.ru`, `rostelecom.ru`, `lk.rt.ru` |
| Дом.ру | `domru.ru`, `lk.domru.ru` |

### E-commerce / Маркетплейсы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Wildberries | AS49053, AS57073 и др. | `wildberries.ru`, `wb.ru` и др. |
| Ozon | AS207986, AS44386 | `ozon.ru`, `ozon.app`, `ozone.ru` и др. |
| Авито | AS201012 | `avito.ru`, `avito.st` |
| KazanExpress / Магнит Маркет | AS57319, AS60691 | `kazanexpress.ru`, `magnit.market`, `magnit.ru` и др. |
| СберМегаМаркет | -- | `sbermegamarket.ru`, `megamarket.ru` |
| Lamoda | AS57906 | `lamoda.ru`, `lamoda.co` |
| DNS Shop | -- | `dns-shop.ru`, `dns-shop.net` |
| М.Видео / Эльдорадо | -- | `mvideo.ru`, `eldorado.ru` |
| Ситилинк | -- | `citilink.ru` |
| Леруа Мерлен | -- | `leroymerlin.ru`, `lemanapro.ru` |
| Золотое Яблоко | -- | `goldapple.ru` |
| Детский мир | -- | `detmir.ru` |
| Hoff | -- | `hoff.ru` |
| Aliexpress | AS45102 | `aliexpress.ru` |

### Доставка / Логистика
| Сервис | Домены |
|--------|--------|
| Самокат | `samokat.ru` |
| Delivery Club | `delivery-club.ru` |
| СДЭК | `cdek.ru`, `lk.cdek.ru` и др. |
| Boxberry | `boxberry.ru` |

### Ритейл / Продукты
| Сервис | ASN | Домены |
|--------|-----|--------|
| Пятёрочка / X5 Group | AS44704, AS215810 и др. | `5ka.ru`, `perekrestok.ru`, `vprok.ru`, `x5.ru` и др. |
| Лента | -- | `lenta.com`, `online.lenta.com` |
| Metro Cash and Carry | AS210756 | `metro-cc.ru`, `online.metro-cc.ru` |
| FixPrice | -- | `fix-price.com`, `fix-price.ru` |
| Дикси | AS202760, AS51115 | `dixy.ru` |
| ВкусВилл | -- | `vkusvill.ru`, `online.vkusvill.ru` |
| SPAR | -- | `myspar.ru`, `api.myspar.ru` и др. |
| Rendez-vous | -- | `rendez-vous.ru`, `api.rendez-vous.ru` и др. |
| One Price Coffee | -- | `onepricecoffee.com`, `premiumbonus.ru` и др. |
| Best Benefits | -- | `bestbenefits.ru`, `app.bestbenefits.ru` и др. |

### Стриминг / Видео / Музыка
| Сервис | ASN | Домены |
|--------|-----|--------|
| Rutube | AS207353 | `rutube.ru`, `static.rutube.ru` |
| IVI | -- | `ivi.ru`, `ivi.tv`, `api.ivi.ru` |
| Okko | -- | `okko.tv`, `api.okko.tv` |
| KION | -- | `kion.ru`, `api.kion.ru` |
| Wink | -- | `wink.ru`, `api.wink.ru` |
| START | -- | `start.ru`, `start.video` |
| Premier | -- | `premier.one`, `api.premier.one` |
| Звук (Сбер) | -- | `zvuk.com`, `sberaudio.ru` |

### Государственные сервисы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Госуслуги | AS12389 | `gosuslugi.ru`, `esia.gosuslugi.ru` и др. |
| ФНС / Налоговая | -- | `nalog.gov.ru`, `lkfl2.nalog.ru`, `lkip2.nalog.ru` |
| Мос.ру | AS8901 | `mos.ru`, `my.mos.ru`, `uslugi.mos.ru` |
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
| Суточно.ру | -- | `sutochno.ru` |
| Московский метрополитен | -- | `mosmetro.ru`, `wi-fi.ru` |
| Тройка | -- | `transport.mos.ru`, `troika.mos.ru` |

### Недвижимость
| Сервис | Домены |
|--------|--------|
| ЦИАН | `cian.ru`, `api.cian.ru` |
| Домклик | `domclick.ru`, `api.domclick.ru` |
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
| Авто.ру | `auto.ru`, `api.auto.ru` |
| Drom.ru | `drom.ru`, `auto.drom.ru` |
| Автотека | `autoteka.ru` |

### Карты / Навигация / Гео
| Сервис | ASN | Домены |
|--------|-----|--------|
| 2ГИС | AS197482 | `2gis.com`, `2gis.ru`, `api.2gis.ru` и др. |

### Образование
| Сервис | Домены |
|--------|--------|
| Яндекс Практикум | `practicum.yandex.ru` |
| Skillbox | `skillbox.ru` |
| GeekBrains | `geekbrains.ru`, `gb.ru` |
| Нетология | `netology.ru` |
| Skyeng | `skyeng.ru`, `student.skyeng.ru` |

### Медицина / Здоровье
| Сервис | ASN | Домены |
|--------|-----|--------|
| ДокторНаРаботе / СберЗдоровье | -- | `sberhealth.ru`, `doctoronline.ru` |
| Аптека.ру | -- | `apteka.ru` |
| Еаптека | -- | `eapteka.ru` |
| Аптеки Столички | AS201706 | `stolichki.ru` |
| ЕМИАС | AS209030 | `emias.info`, `emias.ru` |
| Invitro | -- | `invitro.ru`, `api.invitro.ru` и др. |
| Медси | -- | `api.medsi.ru`, `app.medsi.ru` и др. |

### Мессенджеры / Соцсети
| Сервис | Домены |
|--------|--------|
| TenChat | `tenchat.ru` |
| MAX | `max.ru`, `apptracer.ru`, `mycdn.me` |

### Игры
| Сервис | Домены |
|--------|--------|
| VK Play | `vkplay.ru`, `api.vkplay.ru` |
| MY.GAMES | `my.games`, `api.my.games` |

### Облака / Хостинги
| Сервис | Домены |
|--------|--------|
| Selectel | `selectel.ru` |
| REG.RU | `reg.ru` |

### Финтех
| Сервис | Домены |
|--------|--------|
| Мосбиржа | `moex.com` |

### Другое
| Сервис | ASN | Домены |
|--------|-----|--------|
| Литрес | -- | `litres.ru` |
| 1С | -- | `1c.ru`, `1c-bitrix.ru` |
| Битрикс24 | -- | `bitrix24.ru`, `b24.io` |
| AmoCRM | -- | `amocrm.ru`, `amocrm.com` |
| Контур | -- | `kontur.ru`, `extern.kontur.ru`, `elba.kontur.ru` |
| Kaspersky | AS200187 | `kaspersky.ru`, `kaspersky.com` |
| Dr.Web | -- | `drweb.ru`, `drweb.com` |
| Профи.ру | AS60580 | `profi.ru` |

---

# Инструкция по применению

## Получение актуального списка

1. Перейдите на страницу **Releases**.
2. Скачайте файл `ip-list-<дата_время>.json` из последнего релиза.

## Настройка приложения AmneziaVPN

В приложении AmneziaVPN для iOS, MacOS и Linux раздельное тунелирование возможно только по IP-адресам.

В приложении AmneziaVPN для Android и Windows доступно два механизма раздельного туннелирования - как по IP-адресам, так и по приложениям. **Рекомендуется настроить оба метода одновременно:** исключение по IP-адресам — для браузеров, а исключение приложений — для мобильных и десктопных клиентов и приложений.

### Способ А: По IP-адресам (для iOS и macOS)

Этот метод направляет трафик к нужным IP-адресам в обход VPN. 

1. Откройте **AmneziaVPN** и перейдите в **Настройки** соединения.
2. Откройте **Раздельное туннелирование сайтов**.
3. Выберите режим: **«Адреса из списка НЕ должны открываться через VPN»**.
4. Нажмите на **«⋮»** (три точки в правом верхнем углу) ➔ **Импорт**.
5. Выберите скачанный файл `ip-list-<дата_время>.json`.
6. Готово! Маршруты загружены в список исключений.

### Способ Б: По приложениям (для Android и Windows)

Этот метод направляет трафик приложений в обход VPN.
1. В **Настройках** перейдите в **Раздельное туннелирование приложений**.
2. Выберите режим: **«Выбранные приложения НЕ должны открываться через VPN»**.
3. Добавьте в список программы, которые конфликтуют с VPN:
   * **Банки:** Сбербанк, ВТБ, Т-Банк, Альфа-Банк и т.д.
   * **Маркетплейсы:** Wildberries, Ozon, Авито.
   * **Транспорт:** РЖД, Аэрофлот, Яндекс Go, 2ГИС.
   * **Прочее:** Госуслуги, Налоги ФНС.

> ⚠️ **Важно:** Многие российские приложения на Android (банки, маркетплейсы, Госуслуги) определяют VPN через системные API, просто проверяя наличие виртуального сетевого интерфейса. Маршрутизация по IP здесь не поможет — приложение увидит включенный VPN и заблокирует доступ. Для таких случаев нужно исключать приложение целиком. 



# Локальное развертывание

Выполните команду: 

```bash
git clone https://github.com/pincetgore/amnezia-app-ru-list.git
cd amnezia-app-ru-list
pip install -r requirements.txt
python main.py
```

Результат будет файл `ip-list.json`, который находится в текущей директории.

## Добавление нового сервиса

Добавьте запись в файл `config.yaml`:

```yaml
  - name: "Название сервиса"
    asn:
      - 12345          # ASN можно найти на https://bgp.he.net
    domains:
      - example.ru     # Домены для DNS-резолвинга
      - api.example.ru
    ip_ranges:         # (Опционально) Статические подсети или IP-адреса
      - 192.0.2.0/24
```

Если ASN неизвестен или сервис использует облачный хостинг, оставьте `asn: []` — будут использованы только DNS A-записи.

Затем выполните команду:

```bash
python main.py
```

## Ручной запуск тестов

Выполните команду:

```bash
pip install pytest pyyaml
pytest
```

## Параметры CLI

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
