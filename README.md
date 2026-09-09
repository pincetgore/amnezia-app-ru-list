<img width="1584" height="672" alt="trikolor" src="https://github.com/user-attachments/assets/5afaee38-442a-499f-a49b-f8ebb6820d2d" />

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
[![Update](https://img.shields.io/github/actions/workflow/status/pincetgore/amnezia-app-ru-list/update.yml?style=for-the-badge&logo=github&label=UPDATE)](https://github.com/pincetgore/amnezia-app-ru-list/actions/workflows/update.yml)
![Tests](https://img.shields.io/badge/Unit_Tests-Passing-brightgreen?style=for-the-badge)
![Data Source](https://img.shields.io/badge/Data_Source-RIPE_NCC_API-ea580c?style=for-the-badge)
[![License](https://img.shields.io/badge/LICENSE-MIT-F6C25B?style=for-the-badge&logo=opensourceinitiative&logoColor=white&labelColor=555555)](LICENSE)
<p align="center">
  <a href="https://yoomoney.ru/to/4100119554027650">
    <img src="https://img.shields.io/badge/Поддержать-ЮMoney-8B3FFD?style=for-the-badge&logo=yoomoney&logoColor=white" alt="Поддержать" />
  </a>
</p>

## ⚠️ Юридическая информация

> **Этот проект создан исключительно в ознакомительных и исследовательских целях.**
>
> **Никакие материалы этого проекта не являются призывом к нарушению законов.**

# Оглавление
- [Описание проекта](#описание-проекта)
  - [Источники данных](#источники-данных)
  - [Включённые сервисы](#включённые-сервисы)
  - [Автообновление](#автообновление)
  - [Тесты](#тесты)
- [Инструкция по применению](#инструкция-по-применению)
  - [Получение актуального списка](#получение-актуального-списка)
  - [Настройка приложения AmneziaVPN](#настройка-приложения-amneziavpn)
- [FAQ (Частые вопросы)](#faq-частые-вопросы)
- [Как помочь проекту](#как-помочь-проекту)
- [Локальное развертывание](#локальное-развертывание)
  - [Добавление нового сервиса](#добавление-нового-сервиса)
  - [Ручной запуск тестов](#ручной-запуск-тестов)
  - [Структура проекта](#структура-проекта)
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
│  │  Раздельное тунелирование │   │
│  └─────┬───────────────┬─────┘   │
│        │               │         │
│     Совпало с     Не совпало c   │
│   ip-list.json    ip-list.json   │
│        │               │         │
│        ▼               ▼         │
│    Напрямую        Через VPN     │
│ (Сбербанк, РЖД,   (Telegram,     │
│    WB и др.)     Youtube и др.)  │
└──────────────────────────────────┘
```

---

## Источники данных

1. **RIPE NCC API** (основной) — все анонсированные IPv4-префиксы по ASN организации. Используется **автоматический retry** с экспоненциальным backoff: до 3 повторных запросов (до 4 суммарных попыток) для устойчивости к временным сетевым сбоям.
2. **DNS A-записи** (дополнительный) — многопоточный резолвинг доменов (в первую очередь через DNS-серверы Яндекса) для сервисов без выделенного ASN
3. **bgp.he.net** (fallback) — если RIPE API исчерпал все retry попытки или вернул пустой результат (извлекает CIDR с помощью BeautifulSoup)
4. **Статические подсети и IP-адреса (ip_ranges)** — явно заданные в конфигурации диапазоны

Скрипт собирает CIDR-диапазоны через ASN, дополняет их IP-адресами из DNS и статическими правилами, агрегирует (убирает дубли и вложенные подсети) и формирует в виде `ip-list.json` (в формате AmneziaVPN) и `cidrs.txt` (простой список префиксов).

Готовые файлы обновляются ежедневно и автоматически публикуются на странице **Releases**.

### Конфигурация DNS

DNS-резолвинг настраивается в блоке `dns:` файла `config.yaml`:

```yaml
dns:
  # DNS серверы для резолвинга доменов (порядок приоритета)
  nameservers:
    - 77.88.8.8        # Яндекс.DNS (основной)
    - 77.88.8.1        # Яндекс.DNS (резервный)
    - 8.8.8.8          # Google DNS (fallback)
    - 1.1.1.1          # Cloudflare DNS (fallback)
  
  # Таймаут для резолвинга (секунды)
  timeout: 10
  
  # Максимальное количество параллельных DNS запросов
  max_workers: 20
```

Это позволяет гибко менять DNS-сервера и параметры резолвинга без изменения кода скрипта. Если указаны, `nameservers` должен быть непустым списком IPv4-адресов, а `timeout` и `max_workers` — положительными числами.

### Ограничения

* **Только IPv4**: В данный момент скрипт собирает и агрегирует только IPv4-адреса. IPv6-префиксы игнорируются для совместимости.

## Включённые сервисы

### Локальные и служебные сети

| Сервис | IP-диапазоны | Домены |
| ------ | ------ | ------ |
| Локальные сети (LAN, CGNAT, Multicast) | `10.0.0.0/8`, `100.64.0.0/10`, `169.254.0.0/16` и др. | — |

### Push-уведомления и системные сервисы

| Сервис | IP-диапазоны | Домены |
| ------ | ------ | ------ |
| Apple (Push-уведомления APNs, iCloud и сервисы) | `17.249.0.0/16`, `17.252.0.0/16`, `17.57.144.0/22`, `17.188.128.0/18`, `17.188.20.0/23` | `push.apple.com`, `courier.push.apple.com`, `identity.apple.com`, `icloud.com` и др. |

### IP и GEO чеккеры

| Сервис | Домены |
| ------ | ------ |
| Проверка IP на признак включения VPN | `2ip.io`, `51degrees.com`, `abstractapi.com`, `apiip.net` и др. |

### Бигтех и супераппы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Яндекс | AS13238, AS44534 и др. | `afisha.yandex.ru`, `alice.yandex.ru`, `api.kinopoisk.ru`, `api.music.yandex.net` и др. |
| VK | AS28709, AS47541 и др. | `cloud.vk.com`, `mcs.mail.ru`, `mvk.com`, `userapi.com` и др. |
| Mail.ru + Одноклассники | AS47764, AS49797 и др. | `biz.mail.ru`, `cloud.mail.ru`, `e.mail.ru`, `games.mail.ru` и др. |

### Банки и Финтех

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Сбербанк | AS33844, AS35237 и др. | `online.sberbank.ru`, `sber-zvuk.com`, `sber.ru`, `sberbank.com` и др. |
| Т-Банк | AS205638, AS12686 и др. | `api.t-bank-app.ru`, `api.tinkoff.ru`, `as.t-bank-app.ru`, `cdn.t-bank-app.ru` и др. |
| ВТБ | AS24823, AS39154 и др. | `invest.vtb.ru`, `online.vtb.ru`, `vtb-group.ru`, `vtb.ru` и др. |
| Альфа-Банк | AS15632, AS34838 и др. | `alfa.me`, `alfabank.com`, `alfabank.ru`, `alfadirect.ru` и др. |
| Газпромбанк | AS35022, AS48033 и др. | `gazprombank.ru`, `gpb.ru` |
| Россельхозбанк | AS41615 | `online.rshb.ru`, `rshb.ru` |
| Промсвязьбанк | AS35090, AS41584 и др. | `ib.psbank.ru`, `psb.ru`, `psbank.ru` |
| Совкомбанк | AS51136, AS197258 и др. | `halvacard.ru`, `sovcombank.ru` |
| Райффайзен Банк | AS25253 | `online.raiffeisen.ru`, `raiffeisen.ru` |
| Московский Кредитный Банк | AS39267, AS50464 и др. | `mkb.ru`, `online.mkb.ru` |
| Открытие | AS5589 | `open.ru` |
| Росбанк | AS25501 | `rosbank.ru` |
| Банк Россия | AS50640, AS196796 и др. | `abr.ru` |
| ЮMoney | AS43247 | `yookassa.ru`, `yoomoney.ru` |
| СБП / НСПК | AS21292, AS41185 и др. | `nspk.ru`, `sbp.nspk.ru` |
| Wildberries Банк | — | `wb-bank.ru` |
| МТС Банк | AS42777 | `dbo-dengi.online`, `mtsbank.ru`, `mtsdengi.ru`, `tvoyodbo.online` |
| Ozon банк | — | `ozonbank.ru` |
| Мосбиржа | AS48009 | `moex.com` |
| Яндекс Банк / Яндекс Пэй | — | `bank.yandex.ru`, `pay.yandex.ru` |
| Точка Банк | — | `api.tochka.com`, `enter.tochka.com`, `tochka.com` |
| Модульбанк | — | `modulbank.ru` |
| Бланк Банк | — | `blank.ru` |
| Почта Банк | AS200424 | `pochtabank.ru` |
| Банк Санкт-Петербург | AS34978 | `bspb.ru` |
| Уралсиб | AS29076 | `uralsib.ru` |
| Ак Барс Банк | AS31200 | `akbars.ru` |
| Банк ДОМ.РФ | AS39169 | `domrfbank.ru` |
| Ренессанс Банк | AS41703 | `rencredit.ru` |
| ОТП Банк | AS42668 | `otpbank.ru` |
| Центр-инвест | AS34863 | `centrinvest.ru` |
| БКС Мир Инвестиций | AS44256 | `bcs.ru`, `bcsexpress.ru` |
| Финам | — | `finam.ru` |
| Банки.ру | — | `banki.ru` |
| Сравни.ру | — | `sravni.ru` |
| Финуслуги | — | `finuslugi.ru` |
| Золотая Корона (KoronaPay) | AS42691 | `korona.ru`, `koronapay.com`, `rnko.ru` |
| Цифра Банк (Freedom Finance) | AS207012 | `cifra-bank.ru`, `cifrabank.ru` |
| РНКБ (Группа ВТБ) | AS21235 | `rncb.ru` |
| Банк Синара / Делобанк | AS50141 | `delo.ru`, `sinara.ru` |

### Телеком и связь

| Сервис | Домены |
| ------ | ------ |
| МТС | `api.mts.ru`, `id.mts.ru`, `login.mts.ru`, `mts.me` и др. |
| МегаФон | `api.megafon.ru`, `id.megafon.ru`, `lk.megafon.ru`, `megafon.ru` и др. |
| Билайн | `api.beeline.ru`, `beeline.ru`, `id.beeline.ru`, `lk.beeline.ru` и др. |
| Теле2 | `b2c-digest.ru`, `my.tele2.ru`, `t2.com`, `t2.ru` и др. |
| Ростелеком | `lk.rt.ru`, `rostelecom.ru`, `rt.ru` |
| Дом.ру | `domru.ru`, `ertelecom.ru`, `lk.domru.ru` |

### E-commerce и маркетплейсы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Wildberries | AS49053, AS57073 и др. | `digital.wildberries.ru`, `seller.wildberries.ru`, `wb.ru`, `wbstatic.net` и др. |
| Ozon | AS207986, AS44386 | `ozon.app`, `ozon.com`, `ozon.dev`, `ozon.ru` и др. |
| Авито | AS201012 | `avito.com`, `avito.ru`, `avito.st`, `m.avito.ru` и др. |
| СберМегаМаркет | — | `megamarket.ru`, `sbermegamarket.ru` |
| Lamoda | AS57906 | `lamoda.co`, `lamoda.ru` |
| DNS Shop | AS43547 | `dns-shop.net`, `dns-shop.ru` |
| М.Видео / Эльдорадо | AS43977 | `eldorado.ru`, `mvideo.ru` |
| Ситилинк | AS42888 | `citilink.ru` |
| Леруа Мерлен | AS42358 | `lemanapro.ru` |
| Золотое Яблоко | AS208753 | `api.goldapple.ru`, `gacdn.ru`, `goldapple.ru`, `juicyscore.ru` и др. |
| Детский мир | AS44641 | `catalog-cdn.detmir.st`, `detmir.ru`, `go.detmir.st`, `img.detmir.st` |
| Hoff | — | `hoff.ru` |
| Aliexpress | — | `alicdn.com`, `aliexpress.ru`, `api.aliexpress.ru`, `static.alicdn.com` |
| ВсеИнструменты.ру | — | `vseinstrumenti.ru` |
| Петрович | AS50444 | `petrovich.ru` |
| Максидом | — | `maxidom.ru` |
| Спортмастер | AS41885 | `sportmaster.ru` |
| Л'Этуаль | AS42549 | `api.letu.ru`, `letu.ru` |
| Рив Гош | AS43486 | `rivegauche.ru` |
| Ostin | — | `ostin.com`, `ostin.ru` |
| Gloria Jeans | AS44040 | `gloria-jeans.ru` |
| Melon Fashion Group (Befree, Zarina, Love Republic, Sela) | AS43577 | `befree.ru`, `loverepublic.ru`, `melonfashion.ru`, `sela.ru` и др. |
| ОнлайнТрейд | — | `onlinetrade.ru` |
| Регард | — | `regard.ru` |
| Холодильник.ру | — | `holodilnik.ru` |
| Четыре Лапы | AS202359 | `4lapy.ru`, `api.4lapy.ru` |
| Читай-город / Буквоед | AS207604 | `bookvoed.ru`, `chitai-gorod.ru` |
| Лабиринт | — | `labirint.ru` |

### Доставка и логистика

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Купер (бывш. СберМаркет) | — | `api.kuper.ru`, `kuper.ru` |
| Самокат | — | `api.samokat.ru`, `cdn.samokat.ru`, `cm.samokat.ru`, `samokat.ru` |
| Delivery Club | — | `dclub.ru`, `delivery-club.ru` |
| СДЭК | AS50488 | `ad-cdek.ru`, `cdek.ru`, `cdek.shopping`, `lk.cdek.ru` |
| Boxberry | AS204646 | `boxberry.ru` |
| Деловые Линии | AS44633 | `dellin.ru` |
| ПЭК (Первая Экспедиционная Компания) | AS41893 | `pecom.ru` |

### Ритейл и продукты

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Пятёрочка / X5 Group | AS215810, AS44704 | `5ka.ru`, `chizhik.club`, `chizhik.ru`, `myapelsin.ru` и др. |
| Магнит | AS206126 | `dostavka.magnit.ru`, `magnit.app`, `magnit.com`, `magnit.ru` |
| Лента | AS41809 | `lenta.com`, `online.lenta.com` |
| Metro Cash and Carry | — | `api.metro-cc.ru`, `metro-cc.ru`, `online.metro-cc.ru` |
| FixPrice | — | `fix-price.com`, `fix-price.ru` |
| Дикси | AS202760 | `dixy.ru` |
| ВкусВилл | — | `api-sd.vkusvill.ru`, `api.vkusvill.ru`, `app.vkusvill.ru`, `cdn-mobile-backend.vkusvill.ru` и др. |
| SPAR | — | `api.myspar.ru`, `app.myspar.ru`, `myspar.ru` |
| Rendez-vous | — | `api.rendez-vous.ru`, `rendez-vous.ru` |
| One Price Coffee | — | `api.onepricecoffee.com`, `cloud.onepricecoffee.com`, `delivery.onepricecoffee.com`, `onepricecoffee.com` |
| Best Benefits | — | `app.bestbenefits.ru`, `bestbenefits.ru`, `mobile.bestbenefits.ru` |
| Зоозавр | — | `api.new1.zoozavr.ru`, `api.zoozavr.ru`, `blog.zoozavr.ru`, `feedback.zoozavr.ru` и др. |
| Ашан | AS39744 | `auchan.ru` |
| Азбука Вкуса | AS43292 | `av.ru`, `azbukavkusa.ru` |
| Глобус | — | `globus.ru`, `online.globus.ru` |
| О'КЕЙ | AS43431 | `okmarket.ru` |
| Красное & Белое | AS204670 | `k-b.ru`, `krasnoeibeloe.ru` |
| Винлаб | AS206089 | `winelab.ru` |

### Рестораны и доставка еды

| Сервис | Домены |
| ------ | ------ |
| Вкусно — и точка | `vkusnoitochka.ru` |
| Додо Пицца | `dodopizza.com`, `dodopizza.ru` |
| Ростикс | `kfc.ru`, `rostics.ru` |
| Бургер Кинг | `burgerking.ru`, `burgerkingrus.ru` |
| Тануки / Якитория | `tanuki.ru`, `yakitoriya.ru` |

### Стриминг, видео и музыка

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Rutube | AS207353 | `pic.rutube.ru`, `rutube.ru`, `static.rutube.ru` |
| IVI | — | `api.ivi.ru`, `images.ivi.ru`, `ivi.ru`, `ivi.tv` |
| Okko | — | `api.okko.tv`, `okko.tv` |
| KION | — | `kion.ru`, `kion.tv` |
| Wink | — | `wink.ru`, `wink.tv` |
| START | — | `start.ru`, `start.video` |
| Premier | — | `premier.one` |
| Звук (Сбер) | — | `zvuk.com`, `zvuk.ru` |
| Матч ТВ | — | `matchpremier.ru`, `matchtv.ru` |
| Смотрим / ВГТРК | — | `russia.tv`, `smotrim.ru`, `vgtrk.ru` |
| Триколор Кино и ТВ | AS44034 | `kino.tricolor.tv`, `tricolor.tv` |
| Амедиатека (Amediateka) | — | `amediateka.ru` |

### СМИ, пресса и медиа

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| РБК | AS29074 | `quote.ru`, `rbc.ru`, `rbcplus.ru` |
| ТАСС | — | `tass.ru` |
| РИА Новости | AS41829 | `1prime.ru`, `ria.ru`, `rossiyasegodnya.com` |
| Коммерсантъ | AS34818 | `kommersant.ru` |
| Ведомости | — | `vedomosti.ru` |
| Рамблер (Lenta, Gazeta, Чемпионат) | AS39561 | `championat.com`, `gazeta.ru`, `lenta.ru`, `rambler.ru` |
| Пикабу | — | `cs.pikabu.ru`, `pikabu.ru` |
| ИД Комитет (VC.ru, DTF) | — | `cmtt.ru`, `dtf.ru`, `vc.ru` |

### Билеты и афиша

| Сервис | Домены |
| ------ | ------ |
| Кассир.ру | `api.kassir.ru`, `kassir.ru` |
| Ticketland | `live.mts.ru`, `ticketland.ru` |
| Афиша | `afisha.ru` |
| Кинотеатры (Формула Кино, Синема Парк, КАРО) | `karofilm.ru`, `kinoteatr.ru` |

### Государственные сервисы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Госуслуги | AS196747, AS48287 и др. | `esia.gosuslugi.ru`, `gosuslugi.ru`, `gu-st.ru`, `lk.gosuslugi.ru` и др. |
| ФНС / Налоговая | AS25514, AS41892 и др. | `ebs.ru`, `goskey.ru`, `gov.ru`, `lkfl2.nalog.ru` и др. |
| СФР / Социальный фонд России | AS42360 | `pfr.gov.ru`, `sfr.gov.ru` |
| ЕИС Закупки | — | `zakupki.gov.ru` |
| Мос.ру | AS8901 | `mos.ru`, `mosreg.ru`, `my.mos.ru`, `uslugi.mos.ru` |
| ЦБ РФ | AS21272 | `cbr.ru`, `finmarket.ru` |
| Почта России | AS41457 | `mobileapp.russianpost.ru`, `pochta.ru`, `tracking.pochta.ru` |
| Честный знак | AS207867 | `xn--80ajghhoc2aj1c8b.xn--p1ai` |
| Суды и правосудие (ГАС Правосудие, Мой Арбитр, Мосгорсуд) | — | `arbitr.ru`, `ej.sudrf.ru`, `kad.arbitr.ru`, `mos-gorsud.ru` и др. |
| ФССП (Судебные приставы) | AS48721 | `fssp.gov.ru`, `fssprus.ru` |
| Росреестр | — | `pkk.rosreestr.ru`, `rosreestr.gov.ru`, `rosreestr.ru` |
| ГИБДД / Госавтоинспекция | — | `gibdd.ru`, `xn--90adear.xn--p1ai` |
| ФНП / Нотариат | — | `notariat.ru`, `reestr-dover.ru` |
| ГИС ЖКХ и коммунальные услуги | — | `dom.gosuslugi.ru`, `kvartplata.ru`, `lkk.mosoblgaz.ru`, `mosenergosbyt.ru` и др. |
| Региональные Госуслуги (СПб) | — | `gu.spb.ru` |
| ФТС (Таможенная служба) | — | `customs.gov.ru` |
| МВД РФ | — | `mvd.ru` |
| Федеральное казначейство | — | `roskazna.gov.ru` |
| Федресурс и Банкротства (ЕФРСБ) | — | `bankrot.fedresurs.ru`, `fedresurs.ru` |
| Электронные торговые площадки (Госзакупки) | — | `roseltorg.ru`, `rts-tender.ru`, `sberbank-ast.ru` |
| Правовые справочные системы (Консультант / Гарант) | — | `consultant.ru`, `garant.ru` |

### Транспорт, авто и каршеринг

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| РЖД | AS20702 | `cargo.rzd.ru`, `pass.rzd.ru`, `rzd-bonus.ru`, `rzd.ru` и др. |
| Аэрофлот | AS34571 | `aeroflot.ru`, `api.aeroflot.ru` |
| S7 Airlines | AS41801 | `s7.ru` |
| Победа | — | `pobeda.aero` |
| Уральские авиалинии | AS43455 | `uralairlines.ru` |
| Aviasales | — | `aviasales.com`, `aviasales.ru` |
| Tutu.ru | — | `tutu.ru` |
| Островок | — | `api.ostrovok.ru`, `ostrovok.ru` |
| Суточно.ру | — | `sutochno.ru` |
| Твил (Tvil.ru) | — | `tvil.ru` |
| OneTwoTrip | — | `onetwotrip.com`, `onetwotrip.ru` |
| Московский метрополитен | — | `mosmetro.ru`, `wi-fi.ru` |
| Тройка | — | `transport.mos.ru`, `troika.mos.ru` |
| Авто.ру | — | `auto.ru` |
| Drom.ru | — | `auto.drom.ru`, `drom.ru` |
| Автотека | — | `autoteka.ru` |
| Автодор | AS20698 | `avtodor-tr.ru` |
| Делимобиль | — | `api.delimobil.ru`, `delimobil.com`, `delimobil.ru` |
| Ситидрайв / Ситимобил | — | `city-mobil.ru`, `citydrive.ru` |
| Drivee | — | `drivee.ru` |
| Uber Russia | — | `uber.ru` |
| Парковки России | — | `parking.mos.ru` |
| ЦППК и Аэроэкспресс | — | `aeroexpress.ru`, `central-ppk.ru` |
| BelkaCar | — | `api.belkacar.ru`, `belkacar.ru` |
| Whoosh | — | `api.whoosh.bike`, `whoosh.bike`, `whoosh.ru` |
| Юрент | — | `api.urent.ru`, `urent.city`, `urent.ru` |
| Лукойл (АЗС / Ликард) | AS21245, AS44583 | `auto.lukoil.ru`, `licard.ru`, `lukoil.ru` |
| Газпромнефть (АЗС / ОПТИ 24) | AS41655 | `gazprom-neft.ru`, `opti-24.com`, `gpnbonus.ru` |
| Роснефть (Семейная команда) | AS35297, AS41618 | `komandacard.ru`, `rn-card.ru`, `rosneft.ru` |
| Татнефть | AS41793 | `club.tatneft.ru`, `tatneft.ru` |
| Utair | AS35316 | `utair.ru` |
| Smartavia | — | `flysmartavia.com`, `smartavia.ru` |
| Red Wings | — | `flyredwings.com` |
| Nordwind Airlines | — | `nordwindairlines.ru` |

### Автосигнализации и телематика

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| StarLine | AS44117 | `starline-online.ru`, `starline.ru` |
| Pandora | — | `p-on.ru`, `alarmtrade.ru`, `pandora.ru`, `pro.p-on.ru` |

### Недвижимость

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| ЦИАН | AS200449 | `api.cian.ru`, `cian.ru` |
| Домклик | — | `api.domclick.ru`, `domclick.ru` |
| ДомРФ | — | `domrf.ru` |
| ПИК (Группа ПИК и ПИК.Комфорт) | — | `pik.ru` |
| Девелопер Самолет | — | `samolet.ru` |

### Работа, HR и бизнес (ЭДО)

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| HeadHunter | AS47724, AS59601 | `api.hh.ru`, `headhunter.ru`, `hh.ru` |
| SuperJob | AS44046 | `superjob.ru` |
| Работа.ру | — | `rabota.ru` |
| Хабр | — | `career.habr.com`, `habr.com` |
| Профи.ру | AS60580 | `profi.ru` |
| ЭДО и Бизнес (Контур, СБИС, 1С) | AS41807, AS44280 и др. | `1c.ru`, `b2b-center.ru`, `cryptopro.ru`, `diadoc.ru` и др. |

### Карты и навигация

| Сервис | ASN | IP-диапазоны | Домены |
| ------ | ------ | ------ | ------ |
| 2ГИС | AS197482 | `91.236.48.0/22`, `91.221.198.0/23`, `91.236.49.0/24` и др. | `2gis.com`, `2gis.dev`, `2gis.ru`, `api.2gis.ru` и др. |

### Образование и школы

| Сервис | Домены |
| ------ | ------ |
| Яндекс Практикум | `practicum.yandex.ru` |
| Skillbox | `skillbox.ru` |
| GeekBrains | `gb.ru`, `geekbrains.ru` |
| Нетология | `netology.ru` |
| Skyeng | `skyeng.ru`, `student.skyeng.ru` |
| МЭШ (Московская электронная школа) | `dnevnik.mos.ru`, `school.mos.ru`, `uchebnik.mos.ru` |
| Дневник.ру | `dnevnik.me`, `dnevnik.ru` |
| Сферум | `sferum.ru` |
| Учи.ру | `uchi.ru` |
| Фоксфорд | `foxford.ru` |
| Научные библиотеки (eLibrary, КиберЛенинка) | `cyberleninka.ru`, `elibrary.ru` |

### Медицина и здоровье

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| СберЗдоровье | — | `doctoronline.ru`, `sberhealth.ru` |
| Аптека.ру | AS34812 | `apteka.ru` |
| Еаптека | AS208390 | `eapteka.ru` |
| Аптеки Столички | AS206967 | `api.stolichki.ru`, `stolichki.ru` |
| Аптека «Апрель» (Клуб Апрель) | — | `apteka-april.ru` |
| ЕМИАС | — | `emias.info`, `emias.ru`, `lk.emias.mos.ru`, `mgfoms.ru` и др. |
| Invitro | AS43846 | `invitro.ru`, `lk.invitro.ru` |
| Медси | — | `medsi-premium.ru`, `medsi.com`, `medsi.pro`, `medsi.ru` и др. |
| АГНИ | — | `beauty-forma.com`, `lk-dev.beauty-forma.com`, `lk.beauty-forma.com`, `shop.beauty-forma.com` |
| Аптека Вита | AS42996 | `autodiscover.vitaexpress.ru`, `cloud.vitaexpress.ru`, `mailimage.vitaexpress.ru`, `mobapp-api.vitaexpress.ru` и др. |
| ПроДокторов | — | `medtochka.ru`, `prodoctorov.ru` |
| Здравсити | — | `zdravcity.ru` |
| Аптека 36.6 / Горздрав | — | `366.ru`, `gorzdrav.org` |
| Ригла / Будь Здоров | — | `budzdorov.ru`, `rigla.ru` |
| Планета Здоровья | — | `planetazdorovo.ru` |
| Гемотест | AS200787 | `gemotest.ru` |
| Хеликс | AS57677 | `helix.ru` |

### Страхование

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Ингосстрах | AS42861 | `ingos.ru` |
| РЕСО | AS39266 | `agent.reso.ru`, `j7h6i8.reso.ru`, `lms.reso.ru`, `reso.ru` и др. |
| РСА (Российский союз автостраховщиков) | — | `autoins.ru`, `nsis.ru` |
| ВСК | AS43644 | `shop.vsk.ru`, `vsk.ru` |
| Росгосстрах | AS21396 | `my.rgs.ru`, `rgs.ru` |
| Согласие | — | `soglasie.ru` |
| АльфаСтрахование | AS42484 | `alfastrah.ru` |

### Мессенджеры и игры

| Сервис | Домены |
| ------ | ------ |
| TenChat | `tenchat.ru` |
| MAX | `apptracer.ru`, `max.ru`, `mycdn.me` |
| VK Play | `api.vkplay.ru`, `vkplay.ru` |
| MY.GAMES | `api.my.games`, `my.games` |

### Облака, хостинги и репозитории

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Selectel | — | `selectel.ru` |
| REG.RU | — | `reg.ru` |
| Timeweb | AS51115 | `timeweb.cloud` |
| Ngenix.net | AS34879, AS204878 и др. | `ngenix.net` |
| Gitverse | — | `gitverse.ru` |
| GitFlic | — | `gitflic.ru` |
| Beget | — | `beget.com`, `beget.ru` |
| FirstVDS / ISPsystem | — | `firstvds.ru`, `ispsystem.com`, `ispsystem.ru` |
| SpaceWeb | — | `sweb.ru` |
| RUVDS | — | `ruvds.com` |
| Cloud.ru | — | `cloud.ru`, `console.cloud.ru` |
| DDoS-Guard | — | `ddos-guard.net` |
| Qrator Labs | — | `qrator.net` |

### Прочее

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Литрес | — | `litres.ru` |
| Kaspersky | AS200187 | `kaspersky.com`, `kaspersky.ru` |
| Dreamehome | AS137280 | `dreametech.com`, `ru.dreametech.com`, `ru.iot.dreame.tech`, `smarthome.dreame.tech` |
| Мой умный дом (Уфанет) | — | `dom.ufanet.ru`, `secretapi.ufanet.ru`, `ufanet.ru`, `ufanetgroup.com` |
| kojima.ru | — | `kojima.ru` |
| yclients | — | `api.yclients.com`, `app.yclients.com`, `assets.yclients.com`, `b1.yclients.com` и др. |

## Автообновление

GitHub Actions workflow запускается **ежедневно в 04:00 UTC** и автоматически:
1. Прогоняет **42 теста** (`pytest`), включая проверки конфигурации, атомарной записи файлов, защиту от дефолтных маршрутов (`0.0.0.0/0`), unit-тесты ASN/DNS-резолверов с мокированием API и IDN-нормализацию.
2. Запрашивает актуальные данные из RIPE API (с автоматическим retry и exponential backoff) и многопоточно резолвит DNS.
3. Генерирует `ip-list.json` (для Amnezia) и `cidrs.txt` (простой список) с подробной статистикой.
4. Выводит список проблемных доменов, которые не удалось зарезолвить.
5. Создаёт/обновляет релиз и загружает в него сгенерированные файлы только при успешном сборе всех данных (бесшовно, без downtime).

## Тесты

В проекте настроено автоматическое тестирование с помощью фреймворка `pytest`. Тесты защищают проект от публикации сломанных списков маршрутизации из-за опечаток в конфиге или сбоев логики.

**Что проверяется:**
1. **Агрегация IP-сетей**:
   - Алгоритм схлопывания подсетей (например, поглощение мелкой `10.1.0.0/16` более крупной `10.0.0.0/8`).
   - Защита от дефолтного маршрута (`0.0.0.0/0`) и суперсетей (маска `< /8`), предотвращающая ошибочное схлопывание всего интернета в один префикс.
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
4. **Уникальность записей**: во всем `config.yaml` отсутствуют дубликаты:
   - Домены не повторяются в разных сервисах.
   - ASN уникальны (предотвращает лишние запросы к RIPE API).
   - Статически заданные `ip_ranges` не дублируются.

### Unit-тесты резолверов (26 тестов в `test_resolvers.py`)
Тесты используют мокирование API (`unittest.mock`) для быстрого и надежного выполнения без зависимости от внешних сервисов:

1. **Резолвер ASN** (`resolvers/asn.py`):
   - Успешный парсинг ответов RIPE NCC API (включая фильтрацию IPv6 и защиту от `0.0.0.0/0`).
   - Fallback на bgp.he.net при сбое или пустом ответе RIPE (включая проверку извлечения с помощью BeautifulSoup и фильтрацию `0.0.0.0/0`).
   - Обработка сетевых ошибок и пустых результатов.
   - Проверка retry логики с exponential backoff.
   - Нормализация входных форматов ASN (целые числа, строки вида "AS12345").
2. **Резолвер DNS** (`resolvers/dns.py`):
   - Успешный резолвинг доменов и создание `/32` сетей.
   - Поддержка множественных A-записей для одного домена.
   - Кастомные DNS-серверы и таймауты.
   - Параллельный резолвинг с ThreadPoolExecutor.
3. **Агрегация сетей**:
   - Создание и корректность IPv4Network объектов.
   - Правильность работы функции `collapse_addresses()` и фильтрация невалидных суперсетей.

# Инструкция по применению

## Получение актуального списка

1. Перейдите на страницу **Releases**.
2. Скачайте нужный файл из последнего релиза:
   * `ip-list.json` — для импорта в приложение AmneziaVPN.
   * `cidrs.txt` — простой текстовый список сетей в формате CIDR (по одному префиксу на строку). Подходит для настройки маршрутизации в других VPN-клиентах (v2ray, sing-box, Xray), сторонних утилитах, брандмауэрах (например, iptables) или на домашних роутерах (OpenWrt, Keenetic и др.).

## Настройка приложения AmneziaVPN

В приложении AmneziaVPN для iOS, MacOS и Linux раздельное тунелирование возможно только по IP-адресам.

В приложении AmneziaVPN для Android и Windows доступно два механизма раздельного туннелирования - как по IP-адресам, так и по приложениям. **Рекомендуется настроить оба метода одновременно:** исключение по IP-адресам — для браузеров, а исключение приложений — для мобильных и десктопных клиентов и приложений.

### Способ А: По IP-адресам (для iOS и macOS)

Этот метод направляет трафик к нужным IP-адресам в обход VPN. 

1. Откройте **AmneziaVPN** и перейдите в **Настройки** соединения.
2. Откройте **Раздельное туннелирование сайтов**.
3. Выберите режим: **«Адреса из списка НЕ должны открываться через VPN»**.
4. Нажмите на **«⋮»** (три точки в правом верхнем углу) ➔ **Импорт**.
5. Выберите скачанный файл `ip-list.json`.
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
>
> ⚠️ **Уязвимость в Android 16:** В операционной системе Android 16 присутствует критическая уязвимость раздельного тунелирования. Даже если приложение добавлено в исключения и его трафик по умолчанию идет напрямую, оно может принудительно направить свой запрос через сетевой интерфейс VPN (обычно он называется tun0). Вся актуальная информация и статус исправления проблемы обсуждаются в официальном трекере: [AmneziaVPN issue #2457](https://github.com/amnezia-vpn/amnezia-client/issues/2457).

---

# FAQ (Частые вопросы)

**Q: Сервис есть в списке, но он всё равно не работает при включенном VPN. Что делать?**  
**A:** Сервис мог добавить новые серверы, перейти на другой CDN или использовать неявные API-домены. Списки автообновляются ежедневно, попробуйте скачать свежую версию из релизов. Если проблема сохраняется, создайте Issue с описанием или Pull Request с недостающими данными.

**Q: Почему на Android появляется предупреждающий знак ⚠️ рядом с ключом VPN?**  
**A:** Это ограничение ОС Android — таблица маршрутизации переполняется из-за слишком большого количества IP-подсетей. Рекомендуется использовать встроенный механизм раздельного туннелирования «по приложениям» (Способ Б в инструкции) для клиентов банков и маркетплейсов, а маршрутизацию по IP оставить только для браузеров.

**Q: Возможны ли утечки данных о VPN с использованием конфига?**  
**A:** На Android 16 да. Читайте выше информацию о критической уязвимости в системе. 

**Q: Планируется ли поддержка IPv6?**  
**A:** В данный момент нет. Скрипт отфильтровывает IPv6-префиксы, так как многие VPN-клиенты и мобильные провайдеры работают с раздельной IPv6-маршрутизацией нестабильно. 

**Q: Можно ли использовать эти списки на домашних роутерах (Keenetic, OpenWrt и др.)?**  
**A:** Да! Специально для этого генерируется файл `cidrs.txt` (по одному префиксу на строку). Его легко интегрировать в скрипты статической маршрутизации, `ipset` или настройки брандмауэра вашего роутера.

---

# Как помочь проекту

Нашли неработающий российский сервис или знаете, какие IP-диапазоны/домены можно добавить? Буду рад вашим Pull Request-ам!

1. Сделайте форк репозитория.
2. Добавьте сервис или внесите исправления в файл `config.yaml`.
3. Убедитесь, что тесты проходят (см. ниже).
4. Откройте Pull Request с описанием добавленного ресурса.

> [!TIP]
> **Хотите поддержать проект?**
> Если вам помогает этот список и вы хотите поддержать его развитие (оплату серверов обновлений и чашечку кофе для автора), вы можете сделать донат по кнопке ниже:
> 
> [![Поддержать проект](https://img.shields.io/badge/Поддержать_проект-ЮMoney-8B3FFD?style=for-the-badge&logo=yoomoney&logoColor=white)](https://yoomoney.ru/to/4100119554027650)

# Локальное развертывание

**Требования:** Python 3.11+

Клонируйте репозиторий и выполните следующие команды: 

```bash
git clone https://github.com/pincetgore/amnezia-app-ru-list.git
cd amnezia-app-ru-list

# Установка зависимостей (версии зафиксированы для совместимости)
pip install -r requirements.txt

# Генерация списка IP-адресов
python main.py
```

Результат будет файл `ip-list.json`, который находится в текущей директории.

Все зависимости зафиксированы в `requirements.txt` для гарантии совместимости:
- `requests==2.34.2` — HTTP-клиент с поддержкой retry логики
- `dnspython==2.8.0` — DNS-резолвер
- `pyyaml==6.0.3` — парсер YAML-конфигов
- `tqdm==4.70.0` — прогресс-бар
- `pytest==9.1.1` — фреймворк для тестирования
- `beautifulsoup4==4.15.0` — HTML-парсер для извлечения данных с bgp.he.net

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

Выполните команду для запуска всех 42 тестов:

```bash
pytest -v
```

Для запуска проверок конфигурации и форматирования (16 тестов):

```bash
pytest test_logic.py -v
```

Для запуска только unit-тестов резолверов (26 тестов):

```bash
pytest test_resolvers.py -v
```

Для запуска конкретного теста (например, параметризованный тест проверки дубликатов):

```bash
pytest test_logic.py::test_no_duplicates_config -v
```

**Примечание:** Конфигурационные тесты используют `@pytest.mark.parametrize` для проверки дубликатов ASN и IP ranges, поэтому они расходятся на несколько вариантов в выводе.

## Структура проекта

```
.
├── main.py                 # Основной скрипт (загрузка, резолвинг, агрегация)
├── config.yaml             # Конфигурация сервисов и DNS параметры
├── requirements.txt        # Python зависимости (версии зафиксированы)
├── .gitignore              # Исключение артефактов (кэши, IDE, build)
├── test_logic.py           # 15 конфигурационных тестов
├── test_resolvers.py       # 22 unit-теста для резолверов (с мокированием)
├── resolvers/
│   ├── asn.py              # RIPE API → IPv4 префиксы (bs4 fallback на bgp.he.net)
│   └── dns.py              # DNS A-записи → /32 сети (параллельно)
└── output/
    └── formatter.py        # JSON/plain форматирование + агрегация CIDR
```

### Описание ключевых файлов

- **main.py** — оркестратор: загружает конфиг, вызывает резолверы, пишет результат. Обрабатывает SIGINT для graceful shutdown.
- **resolvers/asn.py** — получает IPv4-префиксы от RIPE (до 3 повторных запросов, exponential backoff). Fallback на bgp.he.net с парсингом HTML через BeautifulSoup.
- **resolvers/dns.py** — многопоточный резолвинг доменов (до 20 параллельных работников). Использует настраиваемые DNS серверы и возвращает предупреждение для любого неразрешённого домена, включая NXDOMAIN.
- **output/formatter.py** — агрегирует сети через `collapse_addresses()`, форматирует в JSON (AmneziaVPN) или plain (текст) и атомарно заменяет выходной файл.
- **config.yaml** — определения сервисов (ASN, домены, IP) и глобальные параметры DNS.

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

## Обработка ошибок и graceful shutdown

Скрипт имеет встроенную обработку ошибок и может быть безопасно остановлен:

- **Graceful shutdown (Ctrl+C)**: Нажатие Ctrl+C вызывает обработчик `SIGINT`, который завершает программу с кодом `130`.
- **DNS ошибки**: Любой неразрешённый домен, включая `NXDOMAIN`, логируется и выводится в итоговом списке предупреждений, не прерывая выпуск.
- **ASN предупреждения**: Если RIPE API или bgp.he.net не вернули префиксы для конкретного ASN, в лог и итоговую сводку выводится предупреждение ⚠️, а остальные сервисы продолжают собираться.
- **Проверка целостности**: Если не удалось собрать ни одного префикса или файл конфигурации некорректен, скрипт завершится с кодом `1` и **не создаст пустой выходной файл**.
- **Валидация конфига**: До сетевых запросов проверяются структура сервисов, типы данных ASN, IPv4-диапазоны и параметры DNS.

```bash
# При ошибке валидации конфигурации скрипт возвращает exit code для CI/CD
echo $?  # Код ошибки (0 = успех, 1 = ошибка)
```
