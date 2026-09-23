# Контекстная классификация треда https://t.me/don_invest/5296

Промпт `v2-mention-subject-claim` (sha c3860da60d6120d0), вход sha a3ec6f8e090eff88.
Модель `deepseek/deepseek-v4-flash`, один вызов, повтор без вызова; исходный вызов 112.6 с. Токены: вход 5106, выход 4753. Стоимость: $0.00131508 (82 реплик, $0.000016 за реплику).

Сущности треда, из которых выбирала модель: eth, ether, ethereum, opensea, robinhood + other/unknown.

## Структурные проверки

- bad_aspect: ['379797']
- mention_not_in_text: ['379895:eth', '379912:eth']

## Сравнение с разметкой `docs/research/pulse_thread_prelim_5296.tsv`

related = unrelated, продолжающий тему поста или предка (evidence_ids не пусто).

Отношение к теме совпало: 19/82. aspect совпал на 4/6 репликах, которые обе стороны считают относящимися к теме.

| разметка \ модель | direct | contextual | related | unrelated | unclear |
|---|---:|---:|---:|---:|---:|
| direct | 4 | 1 | 0 | 0 | 0 |
| contextual | 1 | 0 | 0 | 1 | 0 |
| related | 1 | 2 | 0 | 51 | 0 |
| unrelated | 0 | 0 | 0 | 11 | 0 |
| unclear | 0 | 0 | 0 | 6 | 4 |

### Расхождения

- [379741](https://t.me/don_invest/5296?comment=379741) разметка related/- — модель unrelated/None, evidence []
  > я походу мимо с своей тоже
  модель: mining hardware · None · разметка: GPU too weak · 
- [379744](https://t.me/don_invest/5296?comment=379744) разметка related/- — модель unrelated/None, evidence []
  > Я со своей 1660 super...
  модель: mining hardware · None · разметка: GPU too weak · 
- [379745](https://t.me/don_invest/5296?comment=379745) разметка related/- — модель unrelated/None, evidence []
  > а реально нагрузка идет какая то? я включил, вроде ниче)
  модель: mining load · None · разметка: GPU load while mining · question
- [379746](https://t.me/don_invest/5296?comment=379746) разметка related/- — модель unrelated/None, evidence []
  > чертолет) щас на пропеллерах нахуй из дома улетит
  модель: fan noise · None · разметка: GPU joke · 
- [379747](https://t.me/don_invest/5296?comment=379747) разметка related/- — модель unrelated/None, evidence []
  > да, у меня грузит нормально так компьютер но и 8 часов показывает до минта
  модель: mining time estimate · None · разметка: GPU load and time to mint · 
- [379748](https://t.me/don_invest/5296?comment=379748) разметка related/- — модель unrelated/None, evidence []
  > rx 7800xt 100% 67 градусов
  модель: GPU temperature · None · разметка: GPU temperature · 
- [379753](https://t.me/don_invest/5296?comment=379753) разметка related/- — модель unrelated/None, evidence []
  > Там тип фермой все забирает
  модель: farms mining · None · разметка: farms take all mints · 
- [379754](https://t.me/don_invest/5296?comment=379754) разметка related/- — модель unrelated/None, evidence []
  > мне лучше выключить, да?
  модель: mining advice · None · разметка: GPU temperature · question
- [379755](https://t.me/don_invest/5296?comment=379755) разметка related/- — модель unrelated/None, evidence []
  > сейчас попробую купить сервер быстро
  модель: buying server · None · разметка: renting a server · 
- [379758](https://t.me/don_invest/5296?comment=379758) разметка related/- — модель unrelated/None, evidence []
  > О, интересно, расскажешь, если стоит того
  модель: server experience · None · разметка: renting a server · 
- [379759](https://t.me/don_invest/5296?comment=379759) разметка related/- — модель unrelated/None, evidence []
  > я сам только 10 мин как включил но 88 градусов многовато если там 10+ часов висит минт у меня 14 пишет
  модель: GPU temperature · None · разметка: GPU temperature · 
- [379760](https://t.me/don_invest/5296?comment=379760) разметка related/- — модель unrelated/None, evidence []
  > как будто стоит выключить в таком случае
  модель: mining advice · None · разметка: stop mining · 
- [379761](https://t.me/don_invest/5296?comment=379761) разметка related/- — модель unrelated/None, evidence []
  > поздновато мы конечно
  модель: timing · None · разметка: late to the mint · 
- [379762](https://t.me/don_invest/5296?comment=379762) разметка related/- — модель unrelated/None, evidence []
  > хорошо ему, ферма дорогая должна быть
  модель: farm cost · None · разметка: farms · 
- [379763](https://t.me/don_invest/5296?comment=379763) разметка related/- — модель unrelated/None, evidence []
  > Не очень. Думаю на ферме из 8 видях, которые майнят что-то забирать этих котов на раз два. Но скорей всего он знал запуск, взял в аренду карты и вперед.
  модель: farm strategy · None · разметка: farms · 
- [379764](https://t.me/don_invest/5296?comment=379764) разметка related/- — модель unrelated/None, evidence []
  > идея кстати интересная
  модель: idea · None · разметка: mining idea · 
- [379767](https://t.me/don_invest/5296?comment=379767) разметка related/- (спорная) — модель unrelated/None, evidence []
  > типа таких майнят
  модель: server mining · None · разметка: what GPUs mine · refers to the image above
- [379768](https://t.me/don_invest/5296?comment=379768) разметка related/- — модель unrelated/None, evidence []
  > оно жрет только визуал даже память не жрет [media]
  модель: GPU usage · None · разметка: GPU load · 
- [379769](https://t.me/don_invest/5296?comment=379769) разметка related/- — модель unrelated/None, evidence []
  > с таким шансом пусть идут нахуй) [media]
  модель: scam suspicion · None · разметка: mint odds · 
- [379770](https://t.me/don_invest/5296?comment=379770) разметка related/- — модель unrelated/None, evidence []
  > что за карта?
  модель: GPU model · None · разметка: which GPU · 
- [379775](https://t.me/don_invest/5296?comment=379775) разметка related/- — модель unrelated/None, evidence []
  > надо на будущее себе подготовить тоже такие сервера, чтоб в пару кликов поднимать.. нужно найти недорогие варианты
  модель: server preparation · None · разметка: servers for future mints · 
- [379782](https://t.me/don_invest/5296?comment=379782) разметка related/- — модель unrelated/None, evidence []
  > 5090 не дешево будет, главное почасовку брать а не фиксу за месяц, тогда нормально и выгодно может получиться
  модель: server rental · None · разметка: renting 5090 servers · 
- [379792](https://t.me/don_invest/5296?comment=379792) разметка related/- (спорная) — модель unrelated/None, evidence []
  > пробуй, смотри нагрузку
  модель: mining advice · None · разметка: GPU load · parent missing
- [379794](https://t.me/don_invest/5296?comment=379794) разметка related/- — модель unrelated/None, evidence []
  > типа если 80-90 градусов висит, то себе дороже
  модель: temperature advice · None · разметка: GPU temperature · 
- [379796](https://t.me/don_invest/5296?comment=379796) разметка direct/other (спорная) — модель direct/payment, evidence ['379796']
  > 0.148 eth
  модель: mint price · None · разметка: NFT price in ETH · parent missing; price of the NFT quoted in ETH: ETH as unit of account, neither ETH market nor spending
- [379797](https://t.me/don_invest/5296?comment=379797) разметка related/- (спорная) — модель contextual/None, evidence ['post']
  > https://opensea.io/collection/hash-cats [media]
  модель: collection link · None · разметка: collection link · parent missing
- [379798](https://t.me/don_invest/5296?comment=379798) разметка related/- (спорная) — модель unrelated/None, evidence []
  > ну если 10+ часов на минт будет держать то пасту бы точно поменять
  модель: thermal paste · None · разметка: thermal paste · parent missing
- [379800](https://t.me/don_invest/5296?comment=379800) разметка related/- — модель unrelated/None, evidence []
  > Нужен контакт сервисного инженера из какого-нибудь дата центра, договориться несколько серваков запустить на это дело тихонько ночью :)
  модель: data center contact · None · разметка: renting data-centre servers · joke
- [379802](https://t.me/don_invest/5296?comment=379802) разметка unclear/- — модель unrelated/None, evidence []
  > ну так и надо было в идеале
  модель: ideal approach · None · разметка: 1 · 
- [379804](https://t.me/don_invest/5296?comment=379804) разметка related/- (спорная) — модель unrelated/None, evidence []
  > конкуренция всё больше
  модель: competition · None · разметка: mining competition · parent missing
- [379807](https://t.me/don_invest/5296?comment=379807) разметка related/- (спорная) — модель unrelated/None, evidence []
  > ну да, рандом
  модель: randomness · None · разметка: mint randomness · parent missing
- [379820](https://t.me/don_invest/5296?comment=379820) разметка unclear/- — модель unrelated/None, evidence []
  > копейки
  модель: cost · None · разметка: 1 · 
- [379823](https://t.me/don_invest/5296?comment=379823) разметка unclear/- — модель unrelated/None, evidence []
  > зайди и все поймешь
  модель: checking site · None · разметка:  · 
- [379824](https://t.me/don_invest/5296?comment=379824) разметка unclear/- — модель unrelated/None, evidence []
  > да
  модель: confirmation · None · разметка:  · 
- [379847](https://t.me/don_invest/5296?comment=379847) разметка unclear/- — модель unrelated/None, evidence []
  > как решить вопрос? [media]
  модель: technical issue · None · разметка:  · 
- [379848](https://t.me/don_invest/5296?comment=379848) разметка unclear/- — модель unrelated/None, evidence []
  > Другой браузер
  модель: browser suggestion · None · разметка: 1 · 
- [379879](https://t.me/don_invest/5296?comment=379879) разметка related/- — модель unrelated/None, evidence []
  > Всем салам 👋🏻 У кого-нибудь получилось сминтить? Я так понимаю сложность растет в такой прогрессии что rtx 5070 в лучшем случае за месяц сминтит в данный момент.
  модель: minting difficulty · None · разметка: mining difficulty · 
- [379880](https://t.me/don_invest/5296?comment=379880) разметка related/- — модель unrelated/None, evidence []
  > привет, вон выше инфа.. по 5-30 видях уже ставят, и там рандом же, может выпасть и за 1 час как я понял но нужны мощности, конкуреция
  модель: competition info · None · разметка: mining competition · 
- [379891](https://t.me/don_invest/5296?comment=379891) разметка direct/payment — модель contextual/payment, evidence ['post']
  > на кошеле 7 баксов в эфире сети robinhood
  модель: wallet balance · None · разметка: ETH wallet balance · 
- [379892](https://t.me/don_invest/5296?comment=379892) разметка contextual/payment (спорная) — модель unrelated/None, evidence []
  > Так ты глянь цену минта
  модель: mint price check · None · разметка: mint price vs balance · advice
- [379893](https://t.me/don_invest/5296?comment=379893) разметка related/- (спорная) — модель unrelated/None, evidence []
  > где глянуть?
  модель: where to check · None · разметка: where to see the mint price · follows 379892 in time, but replies to the post
- [379895](https://t.me/don_invest/5296?comment=379895) разметка contextual/payment — модель direct/payment, evidence ['379895']
  > Такой же вопрос, 55$ в сети тоже не хватило
  модель: insufficient balance · None · разметка: not enough ETH to mint · 
- [379896](https://t.me/don_invest/5296?comment=379896) разметка related/- (спорная) — модель unrelated/None, evidence []
  > Ошибка таже
  модель: same error · None · разметка: mint error · same error as 379890, but replies to the post
- [379898](https://t.me/don_invest/5296?comment=379898) разметка related/- — модель unrelated/None, evidence []
  > Что только не придумают, чтоб развести народ на бабки😂
  модель: scam opinion · None · разметка: project is a scam · 
- [379899](https://t.me/don_invest/5296?comment=379899) разметка related/- (спорная) — модель unrelated/None, evidence []
  > Да уже закинул 500 все равно не получается заминтить, ошибка при переводе…
  модель: mint failure · None · разметка: funding the mint · deposit to mint; ETH implied by 379895/379897, not in its reply chain
- [379904](https://t.me/don_invest/5296?comment=379904) разметка related/- — модель unrelated/None, evidence []
  > Кошелёк законектил с сайтом и если на сам кошелёк нажать когда сконектил, там есть профиль. Можно посмотреть сколько отображается на балансе.
  модель: wallet balance check · None · разметка: checking wallet balance · 
- [379905](https://t.me/don_invest/5296?comment=379905) разметка related/- — модель unrelated/None, evidence []
  > Но лучше не связываться, всё равно обманут😁
  модель: scam warning · None · разметка: project is a scam · 
- [379908](https://t.me/don_invest/5296?comment=379908) разметка related/- — модель unrelated/None, evidence []
  > Короче заминтил, это метамаск мозг делал, осталось продать в профит…
  модель: mint success · None · разметка: minted, now selling · 
- [379909](https://t.me/don_invest/5296?comment=379909) разметка direct/other (спорная) — модель direct/market, evidence ['379909']
  > Да это наверное будет самое сложное, этих нфт там уже 5732 штуки, цена самой дёшевой была около 0.16 eth, сейчас опустилась к 0.14 уже
  модель: floor price · None · разметка: NFT floor in ETH · NFT price in ETH: unit of account
- [379911](https://t.me/don_invest/5296?comment=379911) разметка related/- — модель unrelated/None, evidence []
  > Сколько за минт отдал? На какой карте замайнил?
  модель: mint cost and GPU · None · разметка: mint cost and GPU · question
- [379912](https://t.me/don_invest/5296?comment=379912) разметка related/- (спорная) — модель direct/market, evidence ['379912']
  > Да они сейчас любой картой майнится быстро. Цена за минт от 0.16+ начинается уже. Всё не выгодно уже. Обманули как обычно😂
  модель: mint price · None · разметка: mint price · '0.16+' without unit; ETH implied by same author's 379897, not in chain
- [379913](https://t.me/don_invest/5296?comment=379913) разметка related/- — модель unrelated/None, evidence []
  > 3070 да я из уже штук 10 замайнил не мог просто метамаск отработать
  модель: minting experience · None · разметка: how many minted · 
- [379914](https://t.me/don_invest/5296?comment=379914) разметка related/- — модель unrelated/None, evidence []
  > Да, так и есть походу. Но вроде можно сжечь за 1000 их крипты бля пздц
  модель: burn option · None · разметка: burning the NFT · 
- [379918](https://t.me/don_invest/5296?comment=379918) разметка related/- — модель unrelated/None, evidence []
  > Капец как так? У меня 5070 ни одного минта до сих пор. Или ты с самого начала прям майнишь?
  модель: minting comparison · None · разметка: mint speed · 
- [379919](https://t.me/don_invest/5296?comment=379919) разметка related/- — модель unrelated/None, evidence []
  > Уже не надо, в первые сутки норм профит был
  модель: profit timing · None · разметка: first-day profit · 
- [379920](https://t.me/don_invest/5296?comment=379920) разметка related/- — модель unrelated/None, evidence []
  > Да утром запустил
  модель: start time · None · разметка: mint speed · 
- [379927](https://t.me/don_invest/5296?comment=379927) разметка related/- — модель unrelated/None, evidence []
  > кто тебе мешал посмотреть стоимость флора и стоимость минта ?)
  модель: cost check · None · разметка: mint vs floor · 
- [379928](https://t.me/don_invest/5296?comment=379928) разметка related/- — модель unrelated/None, evidence []
  > Вроде никто, хотелось победить сам процесс
  модель: process motivation · None · разметка: mint vs floor · 
- [379929](https://t.me/don_invest/5296?comment=379929) разметка related/- — модель unrelated/None, evidence []
  > Печально конечно
  модель: sympathy · None · разметка: loss · 
- [379931](https://t.me/don_invest/5296?comment=379931) разметка related/- — модель unrelated/None, evidence []
  > Это скок вышло
  модель: cost question · None · разметка: loss · question
- [379933](https://t.me/don_invest/5296?comment=379933) разметка related/- — модель unrelated/None, evidence []
  > У меня на 3050 показало 6 дней, закрыл нафиг))
  модель: mining time · None · разметка: time to mint · 
- [379937](https://t.me/don_invest/5296?comment=379937) разметка related/- — модель unrelated/None, evidence []
  > Запустил на 1070 Ti, почти сразу дало сминтить, но у меня бабок нет)
  модель: mint opportunity · None · разметка: mint on 1070 Ti · 
- [379938](https://t.me/don_invest/5296?comment=379938) разметка related/- — модель unrelated/None, evidence []
  > потому что 0 конкуренции в сети
  модель: competition · None · разметка: network competition · 
- [379939](https://t.me/don_invest/5296?comment=379939) разметка related/- — модель contextual/market, evidence ['post']
  > Там уже и цена на минт такая же как флор на опенси
  модель: price comparison · None · разметка: mint vs floor · 
- [379940](https://t.me/don_invest/5296?comment=379940) разметка related/- — модель unrelated/None, evidence []
  > выше
  модель: price comparison · None · разметка: mint vs floor · 

## Все метки модели

| id | relation | mention | subject | aspect | claim | stance | evidence | текст |
|---|---|---|---|---|---|---|---|---|
| [379741](https://t.me/don_invest/5296?comment=379741) | unrelated |  | mining hardware |  |  | unclear |  | я походу мимо с своей тоже |
| [379744](https://t.me/don_invest/5296?comment=379744) | unrelated |  | mining hardware |  |  | unclear |  | Я со своей 1660 super... |
| [379745](https://t.me/don_invest/5296?comment=379745) | unrelated |  | mining load |  |  | unclear |  | а реально нагрузка идет какая то? я включил, вроде ниче) |
| [379746](https://t.me/don_invest/5296?comment=379746) | unrelated |  | fan noise |  |  | unclear |  | чертолет) щас на пропеллерах нахуй из дома улетит |
| [379747](https://t.me/don_invest/5296?comment=379747) | unrelated |  | mining time estimate |  |  | unclear |  | да, у меня грузит нормально так компьютер но и 8 часов показывает до минта |
| [379748](https://t.me/don_invest/5296?comment=379748) | unrelated |  | GPU temperature |  |  | unclear |  | rx 7800xt 100% 67 градусов |
| [379750](https://t.me/don_invest/5296?comment=379750) | unrelated |  | moderation |  |  | unclear |  | Без мата пожалуйста) |
| [379752](https://t.me/don_invest/5296?comment=379752) | unclear |  |  |  |  | unclear |  |  [media] |
| [379753](https://t.me/don_invest/5296?comment=379753) | unrelated |  | farms mining |  |  | unclear |  | Там тип фермой все забирает |
| [379754](https://t.me/don_invest/5296?comment=379754) | unrelated |  | mining advice |  |  | unclear |  | мне лучше выключить, да? |
| [379755](https://t.me/don_invest/5296?comment=379755) | unrelated |  | buying server |  |  | unclear |  | сейчас попробую купить сервер быстро |
| [379758](https://t.me/don_invest/5296?comment=379758) | unrelated |  | server experience |  |  | unclear |  | О, интересно, расскажешь, если стоит того |
| [379759](https://t.me/don_invest/5296?comment=379759) | unrelated |  | GPU temperature |  |  | unclear |  | я сам только 10 мин как включил но 88 градусов многовато если там 10+ часов висит минт у меня 14 пишет |
| [379760](https://t.me/don_invest/5296?comment=379760) | unrelated |  | mining advice |  |  | unclear |  | как будто стоит выключить в таком случае |
| [379761](https://t.me/don_invest/5296?comment=379761) | unrelated |  | timing |  |  | unclear |  | поздновато мы конечно |
| [379762](https://t.me/don_invest/5296?comment=379762) | unrelated |  | farm cost |  |  | unclear |  | хорошо ему, ферма дорогая должна быть |
| [379763](https://t.me/don_invest/5296?comment=379763) | unrelated |  | farm strategy |  |  | unclear |  | Не очень. Думаю на ферме из 8 видях, которые майнят что-то забирать этих котов на раз два. Но скорей всего он знал запус |
| [379764](https://t.me/don_invest/5296?comment=379764) | unrelated |  | idea |  |  | unclear |  | идея кстати интересная |
| [379766](https://t.me/don_invest/5296?comment=379766) | unclear |  |  |  |  | unclear |  |  [media] |
| [379767](https://t.me/don_invest/5296?comment=379767) | unrelated |  | server mining |  |  | unclear |  | типа таких майнят |
| [379768](https://t.me/don_invest/5296?comment=379768) | unrelated |  | GPU usage |  |  | unclear |  | оно жрет только визуал даже память не жрет [media] |
| [379769](https://t.me/don_invest/5296?comment=379769) | unrelated |  | scam suspicion |  |  | unclear |  | с таким шансом пусть идут нахуй) [media] |
| [379770](https://t.me/don_invest/5296?comment=379770) | unrelated |  | GPU model |  |  | unclear |  | что за карта? |
| [379774](https://t.me/don_invest/5296?comment=379774) | unrelated |  | moderation |  |  | unclear |  | Без мата пожалуйста |
| [379775](https://t.me/don_invest/5296?comment=379775) | unrelated |  | server preparation |  |  | unclear |  | надо на будущее себе подготовить тоже такие сервера, чтоб в пару кликов поднимать.. нужно найти недорогие варианты |
| [379776](https://t.me/don_invest/5296?comment=379776) | unrelated |  | swearing in crypto |  |  | unclear |  | а как в крипте без мата лол) ты бы еще такое на заводе производстве заявил ) со смеху все бы упали |
| [379777](https://t.me/don_invest/5296?comment=379777) | unrelated |  | moderation |  |  | unclear |  | Ну мы не на заводе вроде |
| [379778](https://t.me/don_invest/5296?comment=379778) | unclear |  |  |  |  | unclear |  |  [media] |
| [379779](https://t.me/don_invest/5296?comment=379779) | unrelated |  | crypto as factory |  |  | unclear |  | крипта=завод, это мне кажется тебе любой мем об крипте докажет |
| [379782](https://t.me/don_invest/5296?comment=379782) | unrelated |  | server rental |  |  | unclear |  | 5090 не дешево будет, главное почасовку брать а не фиксу за месяц, тогда нормально и выгодно может получиться |
| [379792](https://t.me/don_invest/5296?comment=379792) | unrelated |  | mining advice |  |  | unclear |  | пробуй, смотри нагрузку |
| [379794](https://t.me/don_invest/5296?comment=379794) | unrelated |  | temperature advice |  |  | unclear |  | типа если 80-90 градусов висит, то себе дороже |
| [379796](https://t.me/don_invest/5296?comment=379796) | direct | eth | mint price | payment |  | unclear | 379796 | 0.148 eth |
| [379797](https://t.me/don_invest/5296?comment=379797) | contextual |  | collection link |  |  | unclear | post | https://opensea.io/collection/hash-cats [media] |
| [379798](https://t.me/don_invest/5296?comment=379798) | unrelated |  | thermal paste |  |  | unclear |  | ну если 10+ часов на минт будет держать то пасту бы точно поменять |
| [379800](https://t.me/don_invest/5296?comment=379800) | unrelated |  | data center contact |  |  | unclear |  | Нужен контакт сервисного инженера из какого-нибудь дата центра, договориться несколько серваков запустить на это дело ти |
| [379802](https://t.me/don_invest/5296?comment=379802) | unrelated |  | ideal approach |  |  | unclear |  | ну так и надо было в идеале |
| [379804](https://t.me/don_invest/5296?comment=379804) | unrelated |  | competition |  |  | unclear |  | конкуренция всё больше |
| [379807](https://t.me/don_invest/5296?comment=379807) | unrelated |  | randomness |  |  | unclear |  | ну да, рандом |
| [379817](https://t.me/don_invest/5296?comment=379817) | unclear |  |  |  |  | unclear |  | ? |
| [379820](https://t.me/don_invest/5296?comment=379820) | unrelated |  | cost |  |  | unclear |  | копейки |
| [379823](https://t.me/don_invest/5296?comment=379823) | unrelated |  | checking site |  |  | unclear |  | зайди и все поймешь |
| [379824](https://t.me/don_invest/5296?comment=379824) | unrelated |  | confirmation |  |  | unclear |  | да |
| [379846](https://t.me/don_invest/5296?comment=379846) | unrelated |  | scam warning |  |  | unclear |  | ❗❗❗Scam ,машенники |
| [379847](https://t.me/don_invest/5296?comment=379847) | unrelated |  | technical issue |  |  | unclear |  | как решить вопрос? [media] |
| [379848](https://t.me/don_invest/5296?comment=379848) | unrelated |  | browser suggestion |  |  | unclear |  | Другой браузер |
| [379849](https://t.me/don_invest/5296?comment=379849) | unrelated |  | scam discussion |  |  | unclear |  | Спасибо. Удалил. Дон вот как раз по тому что мы говорили днем. Тип поменял своё сообщение на скам. Также он мог поменять |
| [379851](https://t.me/don_invest/5296?comment=379851) | unrelated |  | gate suggestion |  |  | unclear |  | Ну тут наверно гейт нужен, чтобы ловил такое, а то ночью или под утро никто не увидит |
| [379852](https://t.me/don_invest/5296?comment=379852) | unrelated |  | agreement |  |  | unclear |  | Ага. |
| [379878](https://t.me/don_invest/5296?comment=379878) | unrelated |  | previous deletion |  |  | unclear |  | Я спомнил что когда то писал что мое сообщение било удалено из етого чата и писал 18+ как помню и ешо один человек писал |
| [379879](https://t.me/don_invest/5296?comment=379879) | unrelated |  | minting difficulty |  |  | unclear |  | Всем салам 👋🏻 У кого-нибудь получилось сминтить? Я так понимаю сложность растет в такой прогрессии что rtx 5070 в лучшем |
| [379880](https://t.me/don_invest/5296?comment=379880) | unrelated |  | competition info |  |  | unclear |  | привет, вон выше инфа.. по 5-30 видях уже ставят, и там рандом же, может выпасть и за 1 час как я понял но нужны мощност |
| [379890](https://t.me/don_invest/5296?comment=379890) | direct | ether | mint error | payment |  | unclear | 379890 | Чет не врубаюсь. Вроде бы намайнил, пишет: Not sent Not enough ether for the price and the gas |
| [379891](https://t.me/don_invest/5296?comment=379891) | contextual |  | wallet balance | payment |  | unclear | post | на кошеле 7 баксов в эфире сети robinhood |
| [379892](https://t.me/don_invest/5296?comment=379892) | unrelated |  | mint price check |  |  | unclear |  | Так ты глянь цену минта |
| [379893](https://t.me/don_invest/5296?comment=379893) | unrelated |  | where to check |  |  | unclear |  | где глянуть? |
| [379895](https://t.me/don_invest/5296?comment=379895) | direct | eth | insufficient balance | payment |  | unclear | 379895 | Такой же вопрос, 55$ в сети тоже не хватило |
| [379896](https://t.me/don_invest/5296?comment=379896) | unrelated |  | same error |  |  | unclear |  | Ошибка таже |
| [379897](https://t.me/don_invest/5296?comment=379897) | direct | eth | mint price | payment |  | unclear | 379897 | Дак там же написано цена минта 0,16 eth примерно, 55$ маловато будет. |
| [379898](https://t.me/don_invest/5296?comment=379898) | unrelated |  | scam opinion |  |  | unclear |  | Что только не придумают, чтоб развести народ на бабки😂 |
| [379899](https://t.me/don_invest/5296?comment=379899) | unrelated |  | mint failure |  |  | unclear |  | Да уже закинул 500 все равно не получается заминтить, ошибка при переводе… |
| [379904](https://t.me/don_invest/5296?comment=379904) | unrelated |  | wallet balance check |  |  | unclear |  | Кошелёк законектил с сайтом и если на сам кошелёк нажать когда сконектил, там есть профиль. Можно посмотреть сколько ото |
| [379905](https://t.me/don_invest/5296?comment=379905) | unrelated |  | scam warning |  |  | unclear |  | Но лучше не связываться, всё равно обманут😁 |
| [379908](https://t.me/don_invest/5296?comment=379908) | unrelated |  | mint success |  |  | unclear |  | Короче заминтил, это метамаск мозг делал, осталось продать в профит… |
| [379909](https://t.me/don_invest/5296?comment=379909) | direct | eth | floor price | market |  | unclear | 379909 | Да это наверное будет самое сложное, этих нфт там уже 5732 штуки, цена самой дёшевой была около 0.16 eth, сейчас опустил |
| [379911](https://t.me/don_invest/5296?comment=379911) | unrelated |  | mint cost and GPU |  |  | unclear |  | Сколько за минт отдал? На какой карте замайнил? |
| [379912](https://t.me/don_invest/5296?comment=379912) | direct | eth | mint price | market |  | unclear | 379912 | Да они сейчас любой картой майнится быстро. Цена за минт от 0.16+ начинается уже. Всё не выгодно уже. Обманули как обычн |
| [379913](https://t.me/don_invest/5296?comment=379913) | unrelated |  | minting experience |  |  | unclear |  | 3070 да я из уже штук 10 замайнил не мог просто метамаск отработать |
| [379914](https://t.me/don_invest/5296?comment=379914) | unrelated |  | burn option |  |  | unclear |  | Да, так и есть походу. Но вроде можно сжечь за 1000 их крипты бля пздц |
| [379918](https://t.me/don_invest/5296?comment=379918) | unrelated |  | minting comparison |  |  | unclear |  | Капец как так? У меня 5070 ни одного минта до сих пор. Или ты с самого начала прям майнишь? |
| [379919](https://t.me/don_invest/5296?comment=379919) | unrelated |  | profit timing |  |  | unclear |  | Уже не надо, в первые сутки норм профит был |
| [379920](https://t.me/don_invest/5296?comment=379920) | unrelated |  | start time |  |  | unclear |  | Да утром запустил |
| [379927](https://t.me/don_invest/5296?comment=379927) | unrelated |  | cost check |  |  | unclear |  | кто тебе мешал посмотреть стоимость флора и стоимость минта ?) |
| [379928](https://t.me/don_invest/5296?comment=379928) | unrelated |  | process motivation |  |  | unclear |  | Вроде никто, хотелось победить сам процесс |
| [379929](https://t.me/don_invest/5296?comment=379929) | unrelated |  | sympathy |  |  | unclear |  | Печально конечно |
| [379931](https://t.me/don_invest/5296?comment=379931) | unrelated |  | cost question |  |  | unclear |  | Это скок вышло |
| [379933](https://t.me/don_invest/5296?comment=379933) | unrelated |  | mining time |  |  | unclear |  | У меня на 3050 показало 6 дней, закрыл нафиг)) |
| [379937](https://t.me/don_invest/5296?comment=379937) | unrelated |  | mint opportunity |  |  | unclear |  | Запустил на 1070 Ti, почти сразу дало сминтить, но у меня бабок нет) |
| [379938](https://t.me/don_invest/5296?comment=379938) | unrelated |  | competition |  |  | unclear |  | потому что 0 конкуренции в сети |
| [379939](https://t.me/don_invest/5296?comment=379939) | contextual |  | price comparison | market |  | unclear | post | Там уже и цена на минт такая же как флор на опенси |
| [379940](https://t.me/don_invest/5296?comment=379940) | unrelated |  | price comparison |  |  | unclear |  | выше |
| [379999](https://t.me/don_invest/5296?comment=379999) | unrelated |  | traffic request |  |  | unclear |  | Гайс, кто трафик лить умеет? В лс |
