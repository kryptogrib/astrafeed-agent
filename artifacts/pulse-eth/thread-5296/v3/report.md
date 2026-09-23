# Релевантность и пересказ: тред https://t.me/don_invest/5296

Контракт `v3-relevance-summary` (sha промпта 9afc8371a8335d39), вход sha d3b4ed3d94fd5e35.
Модель `deepseek/deepseek-v4-flash`, провайдер DeepInfra (закреплён: DeepInfra), finish_reason stop, один вызов, повтор без вызова; исходный вызов 88.6 с.
Токены: вход 5165, выход 4313. Стоимость $0.001204326 (82 реплик, $0.000015 за реплику; $0.127 за 1M токенов).

Упоминания темы от детектора: пост — нет; комментариев с упоминанием 5.

relevance: {'unrelated': 58, 'unclear': 3, 'relevant': 21}. У relevant aspect: {'market': 8, 'usage': 11, 'other': 2}, kind: {'experience': 13, 'other': 1, 'question': 3, 'opinion': 4}.

## Структурные проверки (флаги, не исключения)

- context_not_in_chain: ['379891:379890']
- relevant_without_mention_or_context: ['379908', '379912', '379937']
- relevant_not_grounded: ['379899', '379908', '379911', '379912', '379913', '379914', '379927', '379928', '379929', '379931', '379937', '379938', '379939', '379940']

## Кандидаты в названия темы от модели (не подтверждены)

- нет

## Сравнение с разметкой `docs/research/pulse_thread_prelim_5296_v3.tsv`

relevance совпала: 61/82. aspect совпал на 4/7 репликах, которые обе стороны считают relevant. Офтоп в выборке модели (relevant у модели, unrelated в разметке): 12 ['379908', '379911', '379913', '379914', '379927', '379928', '379929', '379931', '379937', '379938', '379939', '379940'].

| разметка \ модель | relevant | unrelated | unclear |
|---|---:|---:|---:|
| relevant | 7 | 0 | 0 |
| unrelated | 12 | 51 | 0 |
| unclear | 2 | 7 | 3 |

### Расхождения

- [379796](https://t.me/don_invest/5296?comment=379796) разметка relevant/usage — модель relevant/market, context []
  > 0.148 eth
  модель: Сообщает, что цена минта составляет 0.148 eth. · разметка: v3: mint price in ETH -> usage (payment currency)
- [379802](https://t.me/don_invest/5296?comment=379802) разметка unclear/- — модель unrelated/-, context []
  > ну так и надо было в идеале
  модель: — · разметка: —
- [379817](https://t.me/don_invest/5296?comment=379817) разметка unclear/- — модель unrelated/-, context []
  > ?
  модель: — · разметка: —
- [379820](https://t.me/don_invest/5296?comment=379820) разметка unclear/- — модель unrelated/-, context []
  > копейки
  модель: — · разметка: —
- [379823](https://t.me/don_invest/5296?comment=379823) разметка unclear/- — модель unrelated/-, context []
  > зайди и все поймешь
  модель: — · разметка: —
- [379824](https://t.me/don_invest/5296?comment=379824) разметка unclear/- — модель unrelated/-, context []
  > да
  модель: — · разметка: —
- [379847](https://t.me/don_invest/5296?comment=379847) разметка unclear/- — модель unrelated/-, context []
  > как решить вопрос? [media]
  модель: — · разметка: —
- [379848](https://t.me/don_invest/5296?comment=379848) разметка unclear/- — модель unrelated/-, context []
  > Другой браузер
  модель: — · разметка: —
- [379897](https://t.me/don_invest/5296?comment=379897) разметка relevant/usage — модель relevant/market, context []
  > Дак там же написано цена минта 0,16 eth примерно, 55$ маловато будет.
  модель: Объясняет, что цена минта 0.16 eth, поэтому 55 долларов мало. · разметка: v3: mint price 0.16 eth
- [379899](https://t.me/don_invest/5296?comment=379899) разметка unclear/- — модель relevant/usage, context ['379898']
  > Да уже закинул 500 все равно не получается заминтить, ошибка при переводе…
  модель: Сообщает, что закинул 500 долларов, но всё равно не получается заминтить — ошибка при переводе. · разметка: v3: sent 500, cannot mint; ETH only implied by siblings
- [379908](https://t.me/don_invest/5296?comment=379908) разметка unrelated/- — модель relevant/usage, context []
  > Короче заминтил, это метамаск мозг делал, осталось продать в профит…
  модель: Сообщает, что заминтил — проблема была в MetaMask, осталось продать. · разметка: —
- [379909](https://t.me/don_invest/5296?comment=379909) разметка relevant/usage — модель relevant/market, context ['379908']
  > Да это наверное будет самое сложное, этих нфт там уже 5732 штуки, цена самой дёшевой была около 0.16 eth, сейчас опустилась к 0.14 уже
  модель: Сообщает, что NFT уже 5732 штуки, самая дешёвая стоила около 0.16 eth, сейчас опустилась к 0.14. · разметка: v3: NFT floor price named in ETH -> usage, not ETH market
- [379911](https://t.me/don_invest/5296?comment=379911) разметка unrelated/- — модель relevant/usage, context ['379908']
  > Сколько за минт отдал? На какой карте замайнил?
  модель: Спрашивает, сколько отдал за минт и на какой карте замайнил. · разметка: question
- [379912](https://t.me/don_invest/5296?comment=379912) разметка unclear/- — модель relevant/market, context []
  > Да они сейчас любой картой майнится быстро. Цена за минт от 0.16+ начинается уже. Всё не выгодно уже. Обманули как обычно😂
  модель: Считает, что майнится любой картой, но цена минта от 0.16+ — уже невыгодно, обманули. · разметка: v3: mint price 0.16+ without a unit; ETH only implied by a sibling (379897), not the chain
- [379913](https://t.me/don_invest/5296?comment=379913) разметка unrelated/- — модель relevant/usage, context ['379911']
  > 3070 да я из уже штук 10 замайнил не мог просто метамаск отработать
  модель: Отвечает, что на 3070 замайнил уже штук 10, проблема была в MetaMask. · разметка: —
- [379914](https://t.me/don_invest/5296?comment=379914) разметка unrelated/- — модель relevant/usage, context ['379912']
  > Да, так и есть походу. Но вроде можно сжечь за 1000 их крипты бля пздц
  модель: Соглашается, что так и есть, но упоминает возможность сжечь за 1000 их крипты. · разметка: —
- [379927](https://t.me/don_invest/5296?comment=379927) разметка unrelated/- — модель relevant/market, context ['379914']
  > кто тебе мешал посмотреть стоимость флора и стоимость минта ?)
  модель: Риторически спрашивает, кто мешал посмотреть стоимость флора и минта. · разметка: —
- [379928](https://t.me/don_invest/5296?comment=379928) разметка unrelated/- — модель relevant/other, context ['379927']
  > Вроде никто, хотелось победить сам процесс
  модель: Отвечает, что хотелось победить сам процесс. · разметка: —
- [379929](https://t.me/don_invest/5296?comment=379929) разметка unrelated/- — модель relevant/other, context ['379914']
  > Печально конечно
  модель: Выражает сожаление: печально. · разметка: —
- [379931](https://t.me/don_invest/5296?comment=379931) разметка unrelated/- — модель relevant/usage, context ['379914']
  > Это скок вышло
  модель: Спрашивает, сколько вышло. · разметка: question
- [379937](https://t.me/don_invest/5296?comment=379937) разметка unrelated/- — модель relevant/usage, context []
  > Запустил на 1070 Ti, почти сразу дало сминтить, но у меня бабок нет)
  модель: Сообщает, что на 1070 Ti почти сразу дало сминтить, но нет денег. · разметка: —
- [379938](https://t.me/don_invest/5296?comment=379938) разметка unrelated/- — модель relevant/market, context ['379937']
  > потому что 0 конкуренции в сети
  модель: Объясняет, что потому что 0 конкуренции в сети. · разметка: —
- [379939](https://t.me/don_invest/5296?comment=379939) разметка unrelated/- — модель relevant/market, context ['379938']
  > Там уже и цена на минт такая же как флор на опенси
  модель: Сообщает, что цена на минт уже такая же, как флор на OpenSea. · разметка: v3: mint price vs floor on OpenSea, no ETH in text or chain
- [379940](https://t.me/don_invest/5296?comment=379940) разметка unrelated/- — модель relevant/market, context ['379939']
  > выше
  модель: Поправляет, что выше. · разметка: —

## Все метки модели

| id | relevance | aspect | kind | упоминания | summary | quote | context | текст |
|---|---|---|---|---|---|---|---|---|
| [379741](https://t.me/don_invest/5296?comment=379741) | unrelated |  | experience |  |  |  |  | я походу мимо с своей тоже |
| [379744](https://t.me/don_invest/5296?comment=379744) | unrelated |  | experience |  |  |  |  | Я со своей 1660 super... |
| [379745](https://t.me/don_invest/5296?comment=379745) | unrelated |  | experience |  |  |  |  | а реально нагрузка идет какая то? я включил, вроде ниче) |
| [379746](https://t.me/don_invest/5296?comment=379746) | unrelated |  | other |  |  |  |  | чертолет) щас на пропеллерах нахуй из дома улетит |
| [379747](https://t.me/don_invest/5296?comment=379747) | unrelated |  | experience |  |  |  |  | да, у меня грузит нормально так компьютер но и 8 часов показывает до минта |
| [379748](https://t.me/don_invest/5296?comment=379748) | unrelated |  | experience |  |  |  |  | rx 7800xt 100% 67 градусов |
| [379750](https://t.me/don_invest/5296?comment=379750) | unrelated |  | other |  |  |  |  | Без мата пожалуйста) |
| [379752](https://t.me/don_invest/5296?comment=379752) | unclear |  | other |  |  |  |  |  [media] |
| [379753](https://t.me/don_invest/5296?comment=379753) | unrelated |  | experience |  |  |  |  | Там тип фермой все забирает |
| [379754](https://t.me/don_invest/5296?comment=379754) | unrelated |  | question |  |  |  |  | мне лучше выключить, да? |
| [379755](https://t.me/don_invest/5296?comment=379755) | unrelated |  | experience |  |  |  |  | сейчас попробую купить сервер быстро |
| [379758](https://t.me/don_invest/5296?comment=379758) | unrelated |  | other |  |  |  |  | О, интересно, расскажешь, если стоит того |
| [379759](https://t.me/don_invest/5296?comment=379759) | unrelated |  | experience |  |  |  |  | я сам только 10 мин как включил но 88 градусов многовато если там 10+ часов висит минт у меня 14 пишет |
| [379760](https://t.me/don_invest/5296?comment=379760) | unrelated |  | opinion |  |  |  |  | как будто стоит выключить в таком случае |
| [379761](https://t.me/don_invest/5296?comment=379761) | unrelated |  | opinion |  |  |  |  | поздновато мы конечно |
| [379762](https://t.me/don_invest/5296?comment=379762) | unrelated |  | opinion |  |  |  |  | хорошо ему, ферма дорогая должна быть |
| [379763](https://t.me/don_invest/5296?comment=379763) | unrelated |  | opinion |  |  |  |  | Не очень. Думаю на ферме из 8 видях, которые майнят что-то забирать этих котов на раз два. Но скорей всего он знал запус |
| [379764](https://t.me/don_invest/5296?comment=379764) | unrelated |  | opinion |  |  |  |  | идея кстати интересная |
| [379766](https://t.me/don_invest/5296?comment=379766) | unclear |  | other |  |  |  |  |  [media] |
| [379767](https://t.me/don_invest/5296?comment=379767) | unrelated |  | experience |  |  |  |  | типа таких майнят |
| [379768](https://t.me/don_invest/5296?comment=379768) | unrelated |  | experience |  |  |  |  | оно жрет только визуал даже память не жрет [media] |
| [379769](https://t.me/don_invest/5296?comment=379769) | unrelated |  | opinion |  |  |  |  | с таким шансом пусть идут нахуй) [media] |
| [379770](https://t.me/don_invest/5296?comment=379770) | unrelated |  | question |  |  |  |  | что за карта? |
| [379774](https://t.me/don_invest/5296?comment=379774) | unrelated |  | other |  |  |  |  | Без мата пожалуйста |
| [379775](https://t.me/don_invest/5296?comment=379775) | unrelated |  | experience |  |  |  |  | надо на будущее себе подготовить тоже такие сервера, чтоб в пару кликов поднимать.. нужно найти недорогие варианты |
| [379776](https://t.me/don_invest/5296?comment=379776) | unrelated |  | opinion |  |  |  |  | а как в крипте без мата лол) ты бы еще такое на заводе производстве заявил ) со смеху все бы упали |
| [379777](https://t.me/don_invest/5296?comment=379777) | unrelated |  | other |  |  |  |  | Ну мы не на заводе вроде |
| [379778](https://t.me/don_invest/5296?comment=379778) | unclear |  | other |  |  |  |  |  [media] |
| [379779](https://t.me/don_invest/5296?comment=379779) | unrelated |  | opinion |  |  |  |  | крипта=завод, это мне кажется тебе любой мем об крипте докажет |
| [379782](https://t.me/don_invest/5296?comment=379782) | unrelated |  | opinion |  |  |  |  | 5090 не дешево будет, главное почасовку брать а не фиксу за месяц, тогда нормально и выгодно может получиться |
| [379792](https://t.me/don_invest/5296?comment=379792) | unrelated |  | other |  |  |  |  | пробуй, смотри нагрузку |
| [379794](https://t.me/don_invest/5296?comment=379794) | unrelated |  | opinion |  |  |  |  | типа если 80-90 градусов висит, то себе дороже |
| [379796](https://t.me/don_invest/5296?comment=379796) | relevant | market | experience | eth (confirmed) | Сообщает, что цена минта составляет 0.148 eth. | 0.148 eth |  | 0.148 eth |
| [379797](https://t.me/don_invest/5296?comment=379797) | unrelated |  | other |  |  |  |  | https://opensea.io/collection/hash-cats [media] |
| [379798](https://t.me/don_invest/5296?comment=379798) | unrelated |  | opinion |  |  |  |  | ну если 10+ часов на минт будет держать то пасту бы точно поменять |
| [379800](https://t.me/don_invest/5296?comment=379800) | unrelated |  | experience |  |  |  |  | Нужен контакт сервисного инженера из какого-нибудь дата центра, договориться несколько серваков запустить на это дело ти |
| [379802](https://t.me/don_invest/5296?comment=379802) | unrelated |  | opinion |  |  |  |  | ну так и надо было в идеале |
| [379804](https://t.me/don_invest/5296?comment=379804) | unrelated |  | opinion |  |  |  |  | конкуренция всё больше |
| [379807](https://t.me/don_invest/5296?comment=379807) | unrelated |  | opinion |  |  |  |  | ну да, рандом |
| [379817](https://t.me/don_invest/5296?comment=379817) | unrelated |  | other |  |  |  |  | ? |
| [379820](https://t.me/don_invest/5296?comment=379820) | unrelated |  | experience |  |  |  |  | копейки |
| [379823](https://t.me/don_invest/5296?comment=379823) | unrelated |  | other |  |  |  |  | зайди и все поймешь |
| [379824](https://t.me/don_invest/5296?comment=379824) | unrelated |  | other |  |  |  |  | да |
| [379846](https://t.me/don_invest/5296?comment=379846) | unrelated |  | opinion |  |  |  |  | ❗❗❗Scam ,машенники |
| [379847](https://t.me/don_invest/5296?comment=379847) | unrelated |  | question |  |  |  |  | как решить вопрос? [media] |
| [379848](https://t.me/don_invest/5296?comment=379848) | unrelated |  | experience |  |  |  |  | Другой браузер |
| [379849](https://t.me/don_invest/5296?comment=379849) | unrelated |  | experience |  |  |  |  | Спасибо. Удалил. Дон вот как раз по тому что мы говорили днем. Тип поменял своё сообщение на скам. Также он мог поменять |
| [379851](https://t.me/don_invest/5296?comment=379851) | unrelated |  | opinion |  |  |  |  | Ну тут наверно гейт нужен, чтобы ловил такое, а то ночью или под утро никто не увидит |
| [379852](https://t.me/don_invest/5296?comment=379852) | unrelated |  | other |  |  |  |  | Ага. |
| [379878](https://t.me/don_invest/5296?comment=379878) | unrelated |  | experience |  |  |  |  | Я спомнил что когда то писал что мое сообщение било удалено из етого чата и писал 18+ как помню и ешо один человек писал |
| [379879](https://t.me/don_invest/5296?comment=379879) | unrelated |  | question |  |  |  |  | Всем салам 👋🏻 У кого-нибудь получилось сминтить? Я так понимаю сложность растет в такой прогрессии что rtx 5070 в лучшем |
| [379880](https://t.me/don_invest/5296?comment=379880) | unrelated |  | experience |  |  |  |  | привет, вон выше инфа.. по 5-30 видях уже ставят, и там рандом же, может выпасть и за 1 час как я понял но нужны мощност |
| [379890](https://t.me/don_invest/5296?comment=379890) | relevant | usage | experience | ether (confirmed) | Сообщает, что намайнил, но не может отправить из-за нехватки ether для цены и газа. | Not sent Not enough ether for the price and the gas |  | Чет не врубаюсь. Вроде бы намайнил, пишет: Not sent Not enough ether for the price and the gas |
| [379891](https://t.me/don_invest/5296?comment=379891) | relevant | usage | experience | эфире (ambiguous) | Уточняет, что на кошельке 7 долларов в эфире сети Robinhood. | на кошеле 7 баксов в эфире сети robinhood | 379890 | на кошеле 7 баксов в эфире сети robinhood |
| [379892](https://t.me/don_invest/5296?comment=379892) | relevant | usage | other |  | Советует посмотреть цену минта. | Так ты глянь цену минта | 379891 | Так ты глянь цену минта |
| [379893](https://t.me/don_invest/5296?comment=379893) | unrelated |  | question |  |  |  |  | где глянуть? |
| [379895](https://t.me/don_invest/5296?comment=379895) | relevant | usage | experience |  | Сообщает, что у него та же проблема: 55 долларов в сети не хватило. | Такой же вопрос, 55$ в сети тоже не хватило | 379890 | Такой же вопрос, 55$ в сети тоже не хватило |
| [379896](https://t.me/don_invest/5296?comment=379896) | unrelated |  | experience |  |  |  |  | Ошибка таже |
| [379897](https://t.me/don_invest/5296?comment=379897) | relevant | market | experience | eth (confirmed) | Объясняет, что цена минта 0.16 eth, поэтому 55 долларов мало. | Дак там же написано цена минта 0,16 eth примерно, 55$ маловато будет. |  | Дак там же написано цена минта 0,16 eth примерно, 55$ маловато будет. |
| [379898](https://t.me/don_invest/5296?comment=379898) | unrelated |  | opinion |  |  |  |  | Что только не придумают, чтоб развести народ на бабки😂 |
| [379899](https://t.me/don_invest/5296?comment=379899) | relevant | usage | experience |  | Сообщает, что закинул 500 долларов, но всё равно не получается заминтить — ошибка при переводе. | Да уже закинул 500 все равно не получается заминтить, ошибка при переводе… | 379898 | Да уже закинул 500 все равно не получается заминтить, ошибка при переводе… |
| [379904](https://t.me/don_invest/5296?comment=379904) | unrelated |  | experience |  |  |  |  | Кошелёк законектил с сайтом и если на сам кошелёк нажать когда сконектил, там есть профиль. Можно посмотреть сколько ото |
| [379905](https://t.me/don_invest/5296?comment=379905) | unrelated |  | opinion |  |  |  |  | Но лучше не связываться, всё равно обманут😁 |
| [379908](https://t.me/don_invest/5296?comment=379908) | relevant | usage | experience |  | Сообщает, что заминтил — проблема была в MetaMask, осталось продать. | Короче заминтил, это метамаск мозг делал, осталось продать в профит… |  | Короче заминтил, это метамаск мозг делал, осталось продать в профит… |
| [379909](https://t.me/don_invest/5296?comment=379909) | relevant | market | experience | eth (confirmed) | Сообщает, что NFT уже 5732 штуки, самая дешёвая стоила около 0.16 eth, сейчас опустилась к 0.14. | цена самой дёшевой была около 0.16 eth, сейчас опустилась к 0.14 уже | 379908 | Да это наверное будет самое сложное, этих нфт там уже 5732 штуки, цена самой дёшевой была около 0.16 eth, сейчас опустил |
| [379911](https://t.me/don_invest/5296?comment=379911) | relevant | usage | question |  | Спрашивает, сколько отдал за минт и на какой карте замайнил. | Сколько за минт отдал? На какой карте замайнил? | 379908 | Сколько за минт отдал? На какой карте замайнил? |
| [379912](https://t.me/don_invest/5296?comment=379912) | relevant | market | opinion |  | Считает, что майнится любой картой, но цена минта от 0.16+ — уже невыгодно, обманули. | Цена за минт от 0.16+ начинается уже. Всё не выгодно уже. Обманули как обычно😂 |  | Да они сейчас любой картой майнится быстро. Цена за минт от 0.16+ начинается уже. Всё не выгодно уже. Обманули как обычн |
| [379913](https://t.me/don_invest/5296?comment=379913) | relevant | usage | experience |  | Отвечает, что на 3070 замайнил уже штук 10, проблема была в MetaMask. | 3070 да я из уже штук 10 замайнил не мог просто метамаск отработать | 379911 | 3070 да я из уже штук 10 замайнил не мог просто метамаск отработать |
| [379914](https://t.me/don_invest/5296?comment=379914) | relevant | usage | experience |  | Соглашается, что так и есть, но упоминает возможность сжечь за 1000 их крипты. | Да, так и есть походу. Но вроде можно сжечь за 1000 их крипты бля пздц | 379912 | Да, так и есть походу. Но вроде можно сжечь за 1000 их крипты бля пздц |
| [379918](https://t.me/don_invest/5296?comment=379918) | unrelated |  | question |  |  |  |  | Капец как так? У меня 5070 ни одного минта до сих пор. Или ты с самого начала прям майнишь? |
| [379919](https://t.me/don_invest/5296?comment=379919) | unrelated |  | opinion |  |  |  |  | Уже не надо, в первые сутки норм профит был |
| [379920](https://t.me/don_invest/5296?comment=379920) | unrelated |  | experience |  |  |  |  | Да утром запустил |
| [379927](https://t.me/don_invest/5296?comment=379927) | relevant | market | question |  | Риторически спрашивает, кто мешал посмотреть стоимость флора и минта. | кто тебе мешал посмотреть стоимость флора и стоимость минта ?) | 379914 | кто тебе мешал посмотреть стоимость флора и стоимость минта ?) |
| [379928](https://t.me/don_invest/5296?comment=379928) | relevant | other | experience |  | Отвечает, что хотелось победить сам процесс. | Вроде никто, хотелось победить сам процесс | 379927 | Вроде никто, хотелось победить сам процесс |
| [379929](https://t.me/don_invest/5296?comment=379929) | relevant | other | opinion |  | Выражает сожаление: печально. | Печально конечно | 379914 | Печально конечно |
| [379931](https://t.me/don_invest/5296?comment=379931) | relevant | usage | question |  | Спрашивает, сколько вышло. | Это скок вышло | 379914 | Это скок вышло |
| [379933](https://t.me/don_invest/5296?comment=379933) | unrelated |  | experience |  |  |  |  | У меня на 3050 показало 6 дней, закрыл нафиг)) |
| [379937](https://t.me/don_invest/5296?comment=379937) | relevant | usage | experience |  | Сообщает, что на 1070 Ti почти сразу дало сминтить, но нет денег. | Запустил на 1070 Ti, почти сразу дало сминтить, но у меня бабок нет) |  | Запустил на 1070 Ti, почти сразу дало сминтить, но у меня бабок нет) |
| [379938](https://t.me/don_invest/5296?comment=379938) | relevant | market | opinion |  | Объясняет, что потому что 0 конкуренции в сети. | потому что 0 конкуренции в сети | 379937 | потому что 0 конкуренции в сети |
| [379939](https://t.me/don_invest/5296?comment=379939) | relevant | market | experience |  | Сообщает, что цена на минт уже такая же, как флор на OpenSea. | Там уже и цена на минт такая же как флор на опенси | 379938 | Там уже и цена на минт такая же как флор на опенси |
| [379940](https://t.me/don_invest/5296?comment=379940) | relevant | market | opinion |  | Поправляет, что выше. | выше | 379939 | выше |
| [379999](https://t.me/don_invest/5296?comment=379999) | unrelated |  | other |  |  |  |  | Гайс, кто трафик лить умеет? В лс |
