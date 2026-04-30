# amnezia-app-ru-list

Автоматически генерируемый список IP-адресов и доменов российских сервисов для **split tunneling** для Amnezia.

Трафик к сервисам из списка идёт **напрямую**, минуя VPN. Всё остальное (включая заблокированные ресурсы) продолжает идти через VPN.

> Готовые файлы обновляются еженедельно и доступны на странице **Releases**.

---

## Как это работает

```
┌─────────────────────────────────────────────────────────────┐
│                      Ваше устройство                        │
│                                                             │
│  Браузер / Приложение                                       │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────────────┐                                   │
│  │   AmneziaVPN         │                                   │
│  │   Split Tunneling    │                                   │
│  └──────┬───────┬───────┘                                   │
│         │       │                                           │
│    Совпало с    Не совпало                                  │
│    ip-list.json с ip-list.json                              │
│         │       │                                           │
│         ▼       ▼                                           │
│    Напрямую   Через Amnezia                                 │
│   (sberbank,  (telegram,                                    │
│    rzd, wb)   youtube и др.)                                │
└─────────────────────────────────────────────────────────────┘
```

### Источники данных

1. **RIPE NCC API** (основной) — все анонсированные IPv4-префиксы по ASN организации
2. **DNS A-записи** (дополнительный) — резолвинг доменов для сервисов без выделенного ASN
3. **bgp.he.net** (fallback) — если RIPE API не отвечает

Скрипт собирает CIDR-диапазоны через ASN, дополняет их IP-адресами из DNS, агрегирует (убирает дубли и вложенные подсети), и формирует `ip-list.json` в формате AmneziaVPN.

---

## Быстрый старт

### Вариант 1: Скачать готовый файл

1. Перейдите на страницу **Releases**.
2. Скачайте `ip-list.json` из последнего релиза.
3. Импортируйте в AmneziaVPN (см. инструкцию ниже).

### Вариант 2: Сгенерировать самостоятельно

```bash
git clone [https://github.com/pincetgore/amnezia-app-ru-list.git]
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
5. Нажмите **":"** (три точки) -> **Импорт** -> выберите `ip-list.json`
6. Домены и IP-диапазоны загрузятся в список исключений

### Исключение приложений (для пользователей Android)

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

## Включённые сервисы (123 записи)

### Технологии / Поисковики / Суперапы
| Сервис | ASN | Домены |
|--------|-----|--------|
| Яндекс | AS13238, AS202611, AS208722 | `yandex.ru`, `ya.ru`, `dzen.ru` и др. |
| ВКонтакте | AS47541, AS44715 | `vk.com`, `vk.ru`, `userapi.com` и др. |
| Mail.ru + Одноклассники | AS47764 | `mail.ru`, `ok.ru`, `cloud.mail.ru` и др. |
| Max | -- | `max.ru`, `apptracer.ru`, `mycdn.me` и др. |

### Банки
| Сервис | ASN | Домены |
|--------|-----|--------|
| Сбербанк | AS44693 | `sberbank.ru`, `online.sberbank.ru`, `sber.ru` и др. |
| Тинькофф / Т-Банк | AS205638 | `tbank.ru`, `tinkoff.ru` и др. |
| ВТБ | AS12722 | `vtb.ru`, `online.vtb.ru` |
| Альфа-Банк | AS28884 | `alfabank.ru`, `alfadirect.ru`, `alfa.me` |
| Газпромбанк | AS56375 | `gazprombank.ru`, `gpb.ru` |
| Россельхозбанк | -- | `rshb.ru`, `online.rshb.ru` |
| Промсвязьбанк | AS198504 | `psbank.ru` |
| Совкомбанк | -- | `sovcombank.ru`, `halvacard.ru` |
| Райффайзен Банк | -- | `raiffeisen.ru`, `online.raiffeisen.ru` |
| Московский Кредитный Банк | -- | `mkb.ru`, `online.mkb.ru` |
| Открытие | -- | `open.ru` |
| Росбанк | -- | `rosbank.ru` |
| Банк Россия | -- | `abr.ru` |
| ЮMoney | -- | `yoomoney.ru`, `yookassa.ru` |
| СБП / НСПК | AS207009 | `nspk.ru`, `sbp.nspk.ru` |

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
| Wildberries | AS210639 | `wildberries.ru`, `wb.ru` и др. |
| Ozon | -- | `ozon.ru`, `ozonbank.ru` и др. |
| Авито | AS200467 | `avito.ru`, `avito.st` |
| Яндекс.Маркет | -- | `market.yandex.ru`, `pokupki.market.yandex.ru` и др. |
| KazanExpress / Магнит Маркет | -- | `kazanexpress.ru`, `magnit.market` и др. |
| СберМегаМаркет | -- | `sbermegamarket.ru`, `megamarket.ru` |
| Lamoda | -- | `lamoda.ru`, `lamoda.co` |
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
| Сервис | Домены |
|--------|--------|
| Пятёрочка / X5 Group | `5ka.ru`, `perekrestok.ru`, `vprok.ru`, `x5.ru` и др. |
| Магнит | `magnit.ru`, `dostavka.magnit.ru` |
| Лента | `lenta.com`, `online.lenta.com` |
| Метро | `metro-cc.ru`, `online.metro-cc.ru` |
| FixPrice | `fix-price.com`, `fix-price.ru` |
| Светофор | `svetofor.info` |
| Дикси | `dixy.ru` |

### Стриминг / Видео / Музыка
| Сервис | ASN | Домены |
|--------|-----|--------|
| Кинопоиск | -- | `kinopoisk.ru`, `hd.kinopoisk.ru`, `api.kinopoisk.ru` |
| Rutube | AS49676 | `rutube.ru`, `static.rutube.ru` |
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
| Госуслуги | AS48498 | `gosuslugi.ru`, `esia.gosuslugi.ru` и др. |
| ФНС / Налоговая | -- | `nalog.gov.ru`, `lkfl2.nalog.ru`, `lkip2.nalog.ru` |
| Мос.ру | -- | `mos.ru`, `my.mos.ru`, `uslugi.mos.ru` |
| ЦБ РФ | -- | `cbr.ru`, `finmarket.ru` |
| Почта России | AS29124 | `pochta.ru`, `tracking.pochta.ru` |

### Транспорт / Путешествия
| Сервис | ASN | Домены |
|--------|-----|--------|
| РЖД | AS34485 | `rzd.ru`, `ticket.rzd.ru`, `pass.rzd.ru` |
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
| HeadHunter | AS211398 | `hh.ru`, `api.hh.ru`, `headhunter.ru` |
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
| 2ГИС | AS196695 | `2gis.ru`, `api.2gis.ru`, `tile.2gis.com` и др. |
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
| Тинькофф Инвестиции | `tinkoff.ru`, `invest-gw.tinkoff.ru` |
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

## Автообновление

GitHub Actions workflow запускается **каждый понедельник в 04:00 UTC** и автоматически:
1. Запрашивает актуальные данные из RIPE и DNS
2. Генерирует `ip-list.json` (для Amnezia) и `cidrs.txt` (простой список)
3. Создаёт/обновляет релиз `latest` и загружает в него сгенерированные файлы

---

## Почему без ASN для телекомов?

МТС (AS8359), МегаФон (AS31133), Билайн (AS3216), Ростелеком (AS12389) — это интернет-провайдеры с сотнями/тысячами IP-префиксов. Включение их полных ASN-диапазонов перегружает маршрутную таблицу Android (появляется восклицательный знак на иконке VPN) и может вызвать сбои. Для работы личных кабинетов операторов достаточно DNS-резолвинга их доменов.

---

## Лицензия

MIT
