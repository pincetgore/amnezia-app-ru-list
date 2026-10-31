<img width="1584" height="672" alt="trikolor" src="https://github.com/user-attachments/assets/5afaee38-442a-499f-a49b-f8ebb6820d2d" />

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
[![Update](https://img.shields.io/github/actions/workflow/status/pincetgore/amnezia-app-ru-list/update.yml?style=for-the-badge&logo=github&label=UPDATE)](https://github.com/pincetgore/amnezia-app-ru-list/actions/workflows/update.yml)
![Tests](https://img.shields.io/badge/Unit_Tests-Passing-brightgreen?style=for-the-badge)
![Data Source](https://img.shields.io/badge/Data_Source-RIPE_NCC_API-ea580c?style=for-the-badge)
[![License](https://img.shields.io/badge/LICENSE-MIT-F6C25B?style=for-the-badge&logo=opensourceinitiative&logoColor=white&labelColor=555555)](LICENSE)
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
2. **DNS A-записи** (дополнительный) — многопоточный резолвинг доменов для сервисов без выделенного ASN. Запросы идут с подсетью клиента (ECS) из Москвы, поэтому CDN отдают те же адреса, что и пользователям в России. Адреса из сетей глобальных CDN (`dns.exclude_asn`) отбрасываются: они общие с посторонними сайтами
3. **bgp.he.net** (fallback) — если RIPE API исчерпал все retry попытки или вернул некорректный ответ; пустой список префиксов fallback не вызывает (извлекает CIDR с помощью BeautifulSoup)
4. **Статические подсети и IP-адреса (ip_ranges)** — явно заданные в конфигурации диапазоны

Скрипт собирает CIDR-диапазоны через ASN, дополняет их IP-адресами из DNS и статическими правилами, агрегирует (убирает дубли и вложенные подсети) и формирует в виде `ip-list.json` (в формате AmneziaVPN) и `cidrs.txt` (простой список префиксов).

Готовые файлы обновляются ежедневно и автоматически публикуются на странице **Releases**.

### Конфигурация DNS

DNS-резолвинг настраивается в блоке `dns:` файла `config.yaml`:

```yaml
dns:
  # DNS серверы для резолвинга доменов (порядок приоритета)
  nameservers:
    - 8.8.8.8          # Google DNS (основной: учитывает ECS)
    - 77.88.8.8        # Яндекс.DNS (резервный)
    - 77.88.8.1        # Яндекс.DNS (резервный)
    - 1.1.1.1          # Cloudflare DNS (fallback)
  
  # Таймаут для резолвинга (секунды)
  timeout: 10
  
  # Максимальное количество параллельных DNS запросов
  max_workers: 20

  # Сети глобальных CDN и облаков: адреса из DNS, попавшие в них, в список не добавляются
  exclude_asn:
    - 13335   # Cloudflare
    - 16509   # Amazon (AWS, CloudFront)
    - 20940   # Akamai
    # ...
```

Google DNS стоит первым, потому что учитывает подсеть клиента (ECS): скрипт передаёт московскую подсеть, и CDN отвечают как пользователю в России. Яндекс.DNS ECS игнорирует, и из CI (раннер GitHub в США) отдаёт зарубежные адреса CDN.

Это позволяет гибко менять DNS-сервера и параметры резолвинга без изменения кода скрипта. Если указаны, `nameservers` должен быть непустым списком IPv4-адресов, `timeout` и `max_workers` — положительными числами, а `exclude_asn` — списком номеров ASN. Фильтр `exclude_asn` действует только на адреса из DNS: ASN и `ip_ranges` сервисов он не затрагивает.

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
| Apple (Push-уведомления APNs, iCloud и системные сервисы) | `17.249.0.0/16`, `17.252.0.0/16`, `17.57.144.0/22`, `17.188.128.0/18`, `17.188.20.0/23` | `courier.push.apple.com`, `identity.apple.com`, `icloud.com` и др. |
| Google FCM и системные сервисы Android | — | `mtalk.google.com`, `fcm.googleapis.com`, `time.android.com` и др. |
| Push-уведомления вендоров Android (Xiaomi, Huawei) | — | `ru-api.xmpush.global.xiaomi.com`, `push.hicloud.com`, `connect.rom.miui.com` и др. |

### Бигтех и супераппы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Яндекс | AS13238, AS44534 и др. | `afisha.yandex.ru`, `alice.yandex.ru`, `api.kinopoisk.ru`, `api.music.yandex.net` и др. |
| VK | AS28709, AS47541 и др. | `cloud.vk.com`, `mcs.mail.ru`, `mvk.com`, `userapi.com` и др. |
| Mail.ru + Одноклассники | AS47764, AS49797 и др. | `biz.mail.ru`, `cloud.mail.ru`, `e.mail.ru`, `games.mail.ru` и др. |

### Нейросети, AI и погода

| Сервис | Домены |
| ------ | ------ |
| Нейросети и искусственный интеллект (GigaChat, Шедеврум) | `giga.chat`, `shedevrum.ai` |
| Погодные сервисы (Гисметео, Метеум) | `gismeteo.ru`, `meteum.ai` |

### Банки и Финтех

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Сбербанк | AS35237, AS42974 и др. | `online.sberbank.ru`, `sber-zvuk.com`, `sber.ru`, `sberbank.com` и др. |
| Т-Банк | AS205638, AS12686 и др. | `api.t-bank-app.ru`, `api.tinkoff.ru`, `as.t-bank-app.ru`, `cdn.t-bank-app.ru` и др. |
| ВТБ | AS24823, AS39154 и др. | `invest.vtb.ru`, `online.vtb.ru`, `vtb-group.ru`, `vtb.ru` и др. |
| Альфа-Банк | AS15632, AS34838 и др. | `alfa.me`, `alfabank.com`, `alfabank.ru`, `alfadirect.ru` и др. |
| Газпромбанк | AS35022, AS48033 и др. | `gazprombank.ru`, `gpb.ru` |
| Россельхозбанк | AS41615 | `online.rshb.ru`, `rshb.ru` |
| Промсвязьбанк | AS42231, AS42554 и др. | `ib.psbank.ru`, `psb.ru`, `psbank.ru` |
| Совкомбанк | AS51136, AS197258 и др. | `halvacard.ru`, `sovcombank.ru` |
| Райффайзен Банк | — | `online.raiffeisen.ru`, `raiffeisen.ru` |
| Московский Кредитный Банк | AS39267, AS50464 и др. | `mkb.ru`, `online.mkb.ru` |
| Открытие | AS5589 | `open.ru` |
| Росбанк | — | `rosbank.ru` |
| Банк Россия | AS50640, AS196796 и др. | `abr.ru` |
| ЮMoney | AS43247 | `yookassa.ru`, `yoomoney.ru` |
| СБП / НСПК | AS21292, AS41185 и др. | `nspk.ru`, `sbp.nspk.ru` |
| Wildberries Банк | — | `wb-bank.ru` |
| МТС Банк | AS51771 | `dbo-dengi.online`, `mtsbank.ru`, `mtsdengi.ru`, `tvoyodbo.online` |
| Ozon банк | — | `ozonbank.ru` |
| Мосбиржа | AS48009 | `moex.com` |
| Яндекс Банк / Яндекс Пэй | — | `bank.yandex.ru`, `pay.yandex.ru` |
| Точка Банк | — | `api.tochka.com`, `enter.tochka.com`, `tochka.com` |
| Модульбанк | AS49729 | `modulbank.ru` |
| Бланк Банк | — | `blank.ru` |
| Почта Банк | — | `pochtabank.ru` |
| Банк Санкт-Петербург | AS24913, AS39254 | `bspb.ru` |
| Уралсиб | AS20872, AS21252 | `uralsib.ru` |
| Ак Барс Банк | AS201757 | `akbars.ru` |
| Банк ДОМ.РФ | — | `domrfbank.ru` |
| Ренессанс Банк | AS34802 | `rencredit.ru` |
| ОТП Банк | AS39688 | `otpbank.ru` |
| Центр-инвест | AS208177 | `centrinvest.ru` |
| БКС Мир Инвестиций | — | `bcs.ru`, `bcsexpress.ru` |
| Финам | — | `finam.ru` |
| Банки.ру | — | `banki.ru` |
| Сравни.ру | — | `sravni.ru` |
| Финуслуги | — | `finuslugi.ru` |
| Золотая Корона (KoronaPay) | AS212264, AS8848 и др. | `korona.ru`, `koronapay.com`, `rnko.ru` |
| Цифра Банк (Freedom Finance) | AS58341 | `cifra-bank.ru`, `cifrabank.ru` |
| РНКБ (Группа ВТБ) | — | `rncb.ru` |
| Банк Синара / Делобанк | AS50141 | `delo.ru`, `sinara.ru` |

### Телеком и связь

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| МТС | — | `api.mts.ru`, `id.mts.ru`, `login.mts.ru`, `mts.me` и др. |
| МегаФон | — | `api.megafon.ru`, `id.megafon.ru`, `lk.megafon.ru`, `megafon.ru` и др. |
| Билайн | — | `api.beeline.ru`, `beeline.ru`, `id.beeline.ru`, `lk.beeline.ru` и др. |
| Теле2 | — | `b2c-digest.ru`, `my.tele2.ru`, `t2.ru`, `tele2.ru` |
| Ростелеком | — | `lk.rt.ru`, `rostelecom.ru`, `rt.ru` |
| Дом.ру | — | `domru.ru`, `ertelecom.ru`, `lk.domru.ru` |
| Виртуальные мобильные операторы (Т-Мобайл, СберМобайл, ВТБ Мобайл, ГПБ Мобайл) | AS202498 | `gpbmobile.ru`, `sbermobile.ru`, `vtbmobile.ru` |

### E-commerce и маркетплейсы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Wildberries | AS49053, AS57073 и др. | `digital.wildberries.ru`, `seller.wildberries.ru`, `wb.ru`, `wbstatic.net` и др. |
| Ozon | AS207986, AS44386 | `ozon.com`, `ozon.dev`, `ozon.ru`, `ozone.ru` и др. |
| Авито | AS201012 | `avito.com`, `avito.ru`, `avito.st`, `m.avito.ru` и др. |
| СберМегаМаркет | — | `megamarket.ru`, `sbermegamarket.ru` |
| Lamoda | AS57906 | `lamoda.ru` |
| DNS Shop | AS57898 | `dns-shop.net`, `dns-shop.ru` |
| М.Видео / Эльдорадо | — | `eldorado.ru`, `mvideo.ru` |
| Ситилинк | AS206904 | `citilink.ru` |
| Леруа Мерлен | — | `lemanapro.ru` |
| Золотое Яблоко | AS208629, AS210443 | `api.goldapple.ru`, `gacdn.ru`, `goldapple.ru`, `juicyscore.ru` и др. |
| Детский мир | AS42661 | `catalog-cdn.detmir.st`, `detmir.ru`, `go.detmir.st`, `img.detmir.st` |
| Hoff | — | `hoff.ru` |
| Aliexpress | — | `aliexpress.ru`, `api.aliexpress.ru` |
| ВсеИнструменты.ру | — | `vseinstrumenti.ru` |
| Петрович | — | `petrovich.ru` |
| Максидом | — | `maxidom.ru` |
| Спортмастер | AS57512 | `sportmaster.ru` |
| Л'Этуаль | AS198821 | `api.letu.ru`, `letu.ru` |
| Рив Гош | — | `rivegauche.ru` |
| Ostin | — | `ostin.com`, `ostin.ru` |
| Melon Fashion Group (Befree, Zarina, Love Republic, Sela) | — | `befree.ru`, `loverepublic.ru`, `melonfashion.ru`, `sela.ru` и др. |
| ОнлайнТрейд | — | `onlinetrade.ru` |
| Регард | — | `regard.ru` |
| Холодильник.ру | — | `holodilnik.ru` |
| Четыре Лапы | — | `4lapy.ru`, `api.4lapy.ru` |
| Читай-город / Буквоед | — | `bookvoed.ru`, `chitai-gorod.ru` |
| Лабиринт | AS60598 | `labirint.ru` |

### Доставка и логистика

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Купер (бывш. СберМаркет) | — | `api.kuper.ru`, `kuper.ru` |
| Самокат | — | `api.samokat.ru`, `cdn.samokat.ru`, `cm.samokat.ru`, `samokat.ru` |
| Delivery Club | — | `dclub.ru`, `delivery-club.ru` |
| СДЭК | AS42524, AS202250 и др. | `ad-cdek.ru`, `cdek.ru`, `cdek.shopping`, `lk.cdek.ru` |
| Boxberry | — | `boxberry.ru` |
| Деловые Линии | AS201800 | `dellin.ru` |
| ПЭК (Первая Экспедиционная Компания) | AS197756 | `pecom.ru` |
| Транспортные компании и курьерская доставка (DPD, Достависта, Байкал Сервис, ЖДЭ, Возовоз) | — | `baikalsr.ru`, `dostavista.ru`, `dpd.ru`, `jde.ru`, `vozovoz.ru` |

### Ритейл и продукты

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Пятёрочка / X5 Group | AS215810, AS44704 | `5ka.ru`, `chizhik.club`, `chizhik.ru`, `myapelsin.ru` и др. |
| Магнит | AS57319, AS60691 | `dostavka.magnit.ru`, `magnit.app`, `magnit.com`, `magnit.ru` |
| Лента | AS201394, AS49012 | `lenta.com`, `online.lenta.com` |
| Metro Cash and Carry | AS34381, AS204474 | `api.metro-cc.ru`, `metro-cc.ru`, `online.metro-cc.ru` |
| FixPrice | — | `fix-price.com`, `fix-price.ru` |
| Дикси | AS202760 | `dixy.ru` |
| ВкусВилл | AS213506 | `api-sd.vkusvill.ru`, `api.vkusvill.ru`, `cdn-mobile-backend.vkusvill.ru` и др. |
| SPAR | — | `api.myspar.ru`, `myspar.ru` |
| Rendez-vous | — | `api.rendez-vous.ru`, `rendez-vous.ru` |
| One Price Coffee | — | `api.onepricecoffee.com`, `cloud.onepricecoffee.com`, `delivery.onepricecoffee.com`, `onepricecoffee.com` |
| Best Benefits | — | `app.bestbenefits.ru`, `bestbenefits.ru`, `mobile.bestbenefits.ru` |
| Зоозавр | — | `api.new1.zoozavr.ru`, `api.zoozavr.ru`, `blog.zoozavr.ru`, `feedback.zoozavr.ru` и др. |
| Ашан | AS204696 | `auchan.ru` |
| Азбука Вкуса | — | `av.ru`, `azbukavkusa.ru` |
| Глобус | — | `globus.ru`, `online.globus.ru` |
| О'КЕЙ | AS60832 | `okmarket.ru` |
| Красное & Белое | — | `k-b.ru`, `krasnoeibeloe.ru` |
| Винлаб | — | `winelab.ru` |

### Рестораны и доставка еды

| Сервис | Домены |
| ------ | ------ |
| Вкусно — и точка | `vkusnoitochka.ru` |
| Додо Пицца | `dodopizza.ru`, `api.dodopizza.ru`, `mapi.dodopizza.ru`, `auth.dodois.io` и др. |
| Дринкит | `drinkit.ru`, `drinkit.io`, `app.drinkit.io` |
| Ароматный мир | `amwine.ru` |
| Ростикс | `kfc.ru`, `rostics.ru` |
| Бургер Кинг | `burgerking.ru`, `burgerkingrus.ru` |
| Тануки / Якитория | `tanuki.ru`, `yakitoriya.ru` |

### Стриминг, видео и музыка

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Rutube | AS207353 | `pic.rutube.ru`, `rutube.ru`, `static.rutube.ru` |
| IVI | AS57629 | `api.ivi.ru`, `images.ivi.ru`, `ivi.ru`, `ivi.tv` |
| Okko | AS211609 | `api.okko.tv`, `okko.tv` |
| KION | — | `kion.ru` |
| Wink | — | `wink.ru` |
| START | AS60283, AS213075 | `start.ru`, `start.video` |
| Premier | — | `premier.one` |
| Звук (Сбер) | — | `zvuk.com`, `zvuk.ru` |
| Матч ТВ | — | `matchpremier.ru`, `matchtv.ru` |
| Смотрим / ВГТРК | AS25292 | `russia.tv`, `smotrim.ru`, `vgtrk.ru` |
| Триколор Кино и ТВ | — | `kino.tricolor.tv`, `tricolor.tv` |
| Амедиатека (Amediateka) | — | `api.amediateka.tech`, `www.amediateka.ru` |

### СМИ, пресса и медиа

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| РБК | AS20848 | `quote.ru`, `rbc.ru`, `rbcplus.ru` |
| ТАСС | — | `tass.ru` |
| РИА Новости | AS44479, AS57352 | `1prime.ru`, `ria.ru`, `rossiyasegodnya.com` |
| Коммерсантъ | AS41619 | `kommersant.ru` |
| Ведомости | — | `vedomosti.ru` |
| Рамблер (Lenta, Gazeta, Чемпионат) | AS24638 | `championat.com`, `gazeta.ru`, `lenta.ru`, `rambler.ru` |
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
| Правительство и Президент РФ (RSNet) | AS8291 | `council.gov.ru`, `duma.gov.ru`, `government.ru`, `kremlin.ru` |
| Федеральные ведомства (РКН, Роспотребнадзор, ФАС, Минобороны) | AS61280 | `edu.gov.ru`, `www.edu.ru`, `fas.gov.ru`, `mil.ru`, `rkn.gov.ru`, `rospotrebnadzor.ru` |
| ЦИК РФ (Выборы) | — | `cikrf.ru`, `izbirkom.ru` |
| Госуслуги | AS196747, AS48287 и др. | `esia.gosuslugi.ru`, `gosuslugi.ru`, `gu-st.ru`, `lk.gosuslugi.ru` и др. |
| ФНС / Налоговая | — | `ebs.ru`, `goskey.ru`, `gov.ru`, `lkfl2.nalog.ru` и др. |
| СФР / Социальный фонд России | AS199922 | `pfr.gov.ru`, `sfr.gov.ru` |
| Мос.ру | AS8901 | `mos.ru`, `mosreg.ru`, `my.mos.ru`, `uslugi.mos.ru` |
| ЦБ РФ | AS8904 | `cbr.ru`, `finmarket.ru` |
| Почта России | — | `mobileapp.russianpost.ru`, `pochta.ru`, `tracking.pochta.ru` |
| Честный знак | AS56565 | `xn--80ajghhoc2aj1c8b.xn--p1ai` |
| Суды и правосудие (ГАС Правосудие, Мой Арбитр, Мосгорсуд) | — | `arbitr.ru`, `ej.sudrf.ru`, `kad.arbitr.ru`, `mos-gorsud.ru` и др. |
| ФССП (Судебные приставы) | — | `fssp.gov.ru`, `fssprus.ru` |
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
| Аэрофлот | AS21231 | `aeroflot.ru`, `api.aeroflot.ru` |
| S7 Airlines | AS198716, AS198817 и др. | `s7.ru` |
| Победа | AS203627 | `pobeda.aero` |
| Уральские авиалинии | — | `uralairlines.ru` |
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
| Делимобиль | — | `api.delimobil.ru`, `delimobil.ru` |
| Ситидрайв / Ситимобил | — | `city-mobil.ru`, `citydrive.ru` |
| Drivee | — | `drivee.ru` |
| Uber Russia | — | `uber.ru` |
| Парковки России | — | `parking.mos.ru` |
| ЦППК и Аэроэкспресс | — | `aeroexpress.ru`, `central-ppk.ru` |
| BelkaCar | — | `api.belkacar.ru`, `belkacar.ru` |
| Whoosh | — | `api.whoosh.bike`, `whoosh.bike`, `whoosh.ru` |
| Юрент | — | `api.urent.ru`, `urent.city`, `urent.ru` |
| Лукойл (АЗС / Ликард) | AS57645, AS60065 | `auto.lukoil.ru`, `licard.ru`, `lukoil.ru` |
| Газпромнефть (АЗС / ОПТИ 24) | — | `gazprom-neft.ru`, `opti-24.com`, `gpnbonus.ru` |
| Роснефть (Семейная команда) | AS41706, AS39911 | `komandacard.ru`, `rn-card.ru`, `rosneft.ru` |
| Татнефть | AS50164 | `club.tatneft.ru`, `tatneft.ru` |
| Utair | AS198877 | `utair.ru` |
| Smartavia | AS64461 | `flysmartavia.com`, `smartavia.ru` |
| Red Wings | — | `flyredwings.com` |
| Nordwind Airlines | — | `nordwindairlines.ru` |
| Автозапчасти и автотовары (Exist, Автодок, Emex, ЕвроАвто, Колеса Даром) | AS204159 | `autodoc.ru`, `emex.ru`, `euroauto.ru`, `exist.ru`, `kolesa-darom.ru` |
| Сети АЗС (Teboil, Нефтьмагистраль) | — | `neftm.ru`, `teboil.ru` |
| Отели, бронирование и туры (Купибилет, Слетать.ру, Броневик) | — | `bronevik.com`, `kupibilet.ru`, `sletat.ru` |

### Автосигнализации и телематика

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| StarLine | AS201511 | `starline-online.ru`, `starline.ru` |
| Pandora | — | `p-on.ru`, `alarmtrade.ru`, `pandora.ru`, `pro.p-on.ru` |

### Недвижимость

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| ЦИАН | — | `api.cian.ru`, `cian.ru` |
| Домклик | — | `api.domclick.ru`, `domclick.ru` |
| ДомРФ | — | `domrf.ru` |
| ПИК (Группа ПИК и ПИК.Комфорт) | AS201851 | `pik.ru` |
| Девелопер Самолет | AS34639 | `samolet.ru` |

### Работа, HR и бизнес (ЭДО)

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| HeadHunter | AS47724, AS59601 | `api.hh.ru`, `headhunter.ru`, `hh.ru` |
| SuperJob | AS47652 | `superjob.ru` |
| Работа.ру | — | `rabota.ru` |
| Хабр | AS204671 | `career.habr.com`, `habr.com` |
| Профи.ру | AS60580 | `profi.ru` |
| ЭДО и Бизнес (Контур, СБИС, 1С) | AS49675, AS39864 | `1c.ru`, `b2b-center.ru`, `cryptopro.ru`, `diadoc.ru` и др. |

### Карты и навигация

| Сервис | ASN | IP-диапазоны | Домены |
| ------ | ------ | ------ | ------ |
| 2ГИС | AS197482 | `91.236.48.0/22`, `91.221.198.0/23`, `91.236.49.0/24` и др. | `2gis.com`, `2gis.dev`, `2gis.ru`, `api.2gis.ru` и др. |

### Образование и школы

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Яндекс Практикум | — | `practicum.yandex.ru` |
| Skillbox | — | `skillbox.ru` |
| GeekBrains | — | `gb.ru`, `geekbrains.ru` |
| Нетология | — | `netology.ru` |
| Skyeng | — | `skyeng.ru`, `student.skyeng.ru` |
| МЭШ (Московская электронная школа) | — | `dnevnik.mos.ru`, `school.mos.ru`, `uchebnik.mos.ru` |
| Дневник.ру | AS199866 | `dnevnik.ru` |
| Сферум | — | `sferum.ru` |
| Учи.ру | — | `uchi.ru` |
| Фоксфорд | — | `foxford.ru` |
| Научные библиотеки (eLibrary) | — | `elibrary.ru` |

### Медицина и здоровье

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| СберЗдоровье | — | `sberhealth.ru` |
| Аптека.ру | — | `apteka.ru` |
| Еаптека | — | `eapteka.ru` |
| Аптеки Столички | — | `api.stolichki.ru`, `stolichki.ru` |
| Аптека Апрель (Клуб Апрель) | — | `apteka-april.ru` |
| ЕМИАС | — | `emias.info`, `emias.ru`, `lk.emias.mos.ru`, `mgfoms.ru` и др. |
| Invitro | AS197379 | `invitro.ru`, `lk.invitro.ru` |
| Медси | AS206295 | `medsi-premium.ru`, `medsi.com`, `app.medsi.pro`, `medsi.ru` и др. |
| АГНИ | — | `beauty-forma.com`, `lk-dev.beauty-forma.com`, `lk.beauty-forma.com`, `shop.beauty-forma.com` |
| Аптека Вита | AS42996 | `autodiscover.vitaexpress.ru`, `cloud.vitaexpress.ru`, `mailimage.vitaexpress.ru`, `mobapp-api.vitaexpress.ru` и др. |
| ПроДокторов | — | `medtochka.ru`, `prodoctorov.ru` |
| Здравсити | — | `zdravcity.ru` |
| Аптека 36.6 / Горздрав | — | `366.ru`, `gorzdrav.org` |
| Ригла / Будь Здоров | AS50218, AS60553 | `budzdorov.ru`, `rigla.ru` |
| Планета Здоровья | — | `planetazdorovo.ru` |
| Гемотест | AS205567 | `gemotest.ru` |
| Хеликс | AS212748 | `helix.ru` |
| Медицинские лаборатории (KDL, Ситилаб) | — | `citilab.ru`, `kdl.ru` |
| Мониторинг диабета и уровня глюкозы (FreeStyle Libre, Medtrum, Sinocare iCan) | — | `freestylediabetes.ru`, `ican-sinocare.ru`, `medtrum.ru` |

### Страхование

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Ингосстрах | AS15707 | `ingos.ru` |
| РЕСО | AS39266 | `agent.reso.ru`, `j7h6i8.reso.ru`, `lms.reso.ru`, `reso.ru` и др. |
| РСА (Российский союз автостраховщиков) | — | `autoins.ru`, `nsis.ru` |
| ВСК | AS51641 | `shop.vsk.ru`, `vsk.ru` |
| Росгосстрах | AS49886 | `my.rgs.ru`, `rgs.ru` |
| Согласие | AS198873 | `soglasie.ru` |
| АльфаСтрахование | — | `alfastrah.ru` |

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
| Timeweb | AS51789 | `timeweb.cloud` |
| Ngenix.net | AS34879, AS204878 | `ngenix.net` |
| ServicePipe (Додо Пицца, Дринкит и др.) | AS201706 | — |
| HLL (Ароматный мир и др.) | AS51115 | — |
| Gitverse | — | `gitverse.ru` |
| GitFlic | — | `gitflic.ru` |
| Beget | — | `beget.com`, `beget.ru` |
| FirstVDS / ISPsystem | — | `firstvds.ru`, `ispsystem.ru` |
| SpaceWeb | — | `sweb.ru` |
| RUVDS | — | `ruvds.com` |
| Cloud.ru | — | `cloud.ru`, `console.cloud.ru` |
| DDoS-Guard | — | `ddos-guard.net` |
| Qrator Labs | — | `qrator.net` |

### Прочее

| Сервис | ASN | Домены |
| ------ | ------ | ------ |
| Литрес | AS61306 | `litres.ru` |
| Kaspersky | — | `kaspersky.com`, `kaspersky.ru` |
| Dreamehome | — | `ru.dreametech.com`, `ru.iot.dreame.tech`, `smarthome.dreame.tech` |
| Мой умный дом (Уфанет) | — | `dom.ufanet.ru`, `secretapi.ufanet.ru`, `ufanet.ru`, `ufanetgroup.com` |
| kojima.ru | — | `kojima.ru` |
| yclients | — | `api.yclients.com`, `assets.yclients.com`, `b1.yclients.com` и др. |

## Автообновление

GitHub Actions workflow запускается **ежедневно в 04:00 UTC** и автоматически:
1. Прогоняет **78 тестов** (`pytest`), включая проверки конфигурации, атомарной записи файлов, защиту от дефолтных маршрутов (`0.0.0.0/0`), unit-тесты ASN/DNS-резолверов с мокированием API и IDN-нормализацию.
2. Запрашивает актуальные данные из RIPE API (с автоматическим retry и exponential backoff) и многопоточно резолвит DNS.
3. Генерирует `ip-list.json` (для Amnezia) и `cidrs.txt` (простой список) с подробной статистикой.
4. Выводит список проблемных доменов, которые не удалось зарезолвить.
5. Создаёт/обновляет релиз и загружает в него сгенерированные файлы (бесшовно, без downtime). Если не ответило больше половины ASN или доменов (например, лёг RIPE API или DNS), список не публикуется и в релизе остаётся предыдущая рабочая версия.

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
5. **Фильтр CDN**: адреса из DNS в сетях `dns.exclude_asn` отбрасываются, а ASN и `ip_ranges` сервисов остаются.

### Unit-тесты резолверов (27 тестов в `test_resolvers.py`)
Тесты используют мокирование API (`unittest.mock`) для быстрого и надежного выполнения без зависимости от внешних сервисов:

1. **Резолвер ASN** (`resolvers/asn.py`):
   - Успешный парсинг ответов RIPE NCC API (включая фильтрацию IPv6 и защиту от `0.0.0.0/0`).
   - Fallback на bgp.he.net только при сбое RIPE, не при пустом списке префиксов (включая проверку извлечения с помощью BeautifulSoup и фильтрацию `0.0.0.0/0`).
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

# Локальное развертывание

**Требования:** Python 3.15+

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

Выполните команду для запуска всех 84 тестов:

```bash
pytest -v
```

Для запуска тестов архитектурных компонентов (модели, валидация конфигурации, пайплайн, репортер — 23 теста):

```bash
pytest test_core.py -v
```

Для запуска проверок конфигурации, форматирования и CLI (25 тестов):

```bash
pytest test_logic.py -v
```

Для запуска только unit-тестов резолверов (36 тестов):

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
├── main.py                 # Тонкая точка входа CLI
├── config.yaml             # Конфигурация сервисов и DNS параметры
├── requirements.txt        # Python зависимости (версии зафиксированы)
├── .gitignore              # Исключение артефактов (кэши, IDE, build)
├── pyrightconfig.json      # Конфигурация статического анализатора типов
├── ruff.toml               # Конфигурация линтера и форматтера Ruff
├── test_core.py            # 23 теста архитектурных компонентов и моделей
├── test_logic.py           # 25 тестов конфигурации, форматирования и CLI
├── test_resolvers.py       # 36 unit-тестов для резолверов (с мокированием)
├── core/
│   ├── config.py           # Загрузка, валидация и парсинг YAML в AppConfig
│   ├── models.py           # Строго типизированные доменные датаклассы (AppConfig, ServiceConfig, PipelineResult)
│   ├── pipeline.py         # ListBuilderPipeline: движок резолвинга и сбора сетей
│   └── reporter.py         # Форматирование и вывод консольной статистики и предупреждений
├── resolvers/
│   ├── asn.py              # ASNResolver: RIPE API → IPv4 префиксы (bs4 fallback на bgp.he.net)
│   └── dns.py              # DNSResolver: DNS A-записи → /32 сети (параллельно)
└── output/
    └── formatter.py        # JSON/plain форматирование + агрегация CIDR
```

### Описание ключевых файлов

- **main.py** — тонкая точка входа CLI: парсинг аргументов командной строки, настройка логирования, запуск `ListBuilderPipeline`, проверка доли неудачных запросов и вывод результатов.
- **core/models.py** — доменные датаклассы (`AppConfig`, `DnsConfig`, `ServiceConfig`, `ServiceResult`, `PipelineResult`) со слотами и строгой типизацией.
- **core/config.py** — изолированная валидация структуры `config.yaml` и безопасный парсинг в типизированные объекты.
- **core/pipeline.py** — `ListBuilderPipeline`: независимый от CLI оркестратор получения сетей по ASN, DNS и статическим диапазонам. Все домены всех сервисов резолвятся одним общим пулом потоков (каждый уникальный домен — один раз).
- **core/reporter.py** — модуль формирования и вывода итоговых сводок и отчётов о предупреждениях.
- **resolvers/asn.py** — получает IPv4-префиксы от RIPE (до 3 повторных запросов, exponential backoff). Fallback на bgp.he.net с парсингом HTML через BeautifulSoup.
- **resolvers/dns.py** — многопоточный резолвинг доменов (до 20 параллельных работников). Использует настраиваемые DNS серверы и возвращает предупреждение для любого неразрешённого домена, включая NXDOMAIN.
- **output/formatter.py** — агрегирует сети через `collapse_addresses()`, форматирует в JSON (AmneziaVPN) или plain (текст) и атомарно заменяет выходной файл.
- **config.yaml** — определения сервисов (ASN, домены, IP) и глобальные параметры DNS.
- **pyrightconfig.json** — привязка виртуального окружения Python 3.15 и правила проверки типов.
- **ruff.toml** — правила линтинга (PEP 8, Pyflakes, isort, modern syntax py315).

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

- **Прерывание (Ctrl+C)**: Выходной файл записывается атомарно, поэтому прерывание не оставляет частично записанный список.
- **DNS ошибки**: Любой неразрешённый домен, включая `NXDOMAIN`, логируется и выводится в итоговом списке предупреждений, не прерывая выпуск.
- **ASN предупреждения**: Если RIPE API или bgp.he.net не вернули префиксы для конкретного ASN, в лог и итоговую сводку выводится предупреждение ⚠️, а остальные сервисы продолжают собираться.
- **Проверка целостности**: Если не ответило больше 50% ASN или больше 50% доменов, после агрегации не осталось ни одного префикса или файл конфигурации некорректен, скрипт завершится с кодом `1` и **не перезапишет выходной файл**. Отдельные сбои дают только предупреждения ⚠️.
- **Валидация конфига**: До сетевых запросов проверяются структура сервисов, типы данных ASN, IPv4-диапазоны и параметры DNS.

```bash
# При ошибке валидации конфигурации скрипт возвращает exit code для CI/CD
echo $?  # Код ошибки (0 = успех, 1 = ошибка)
```
