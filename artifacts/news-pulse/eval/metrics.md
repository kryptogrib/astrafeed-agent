# Независимая оценка news-first Pulse

Маленькая выборка — демо-проверка, не доказательство качества на всех данных. Общий балл не вычисляется.

Разметка: заморожено; предварительная агентская разметка. SHA256 всех файлов manifest.json проверены.
MD5 БД до/после: `8618099125a806df376354286ccd982e` / `8618099125a806df376354286ccd982e`.

Воспроизведение: `python3 docs/research/news_pulse_eval.py --db astrafeed.db`

Синтетические тесты: `python3 -m unittest discover -s tests/research -p test_news_pulse_eval.py -v`

| Метрика | Числитель | Знаменатель | Порог | Статус |
|---|---:|---:|---|---|
| Точность отбора новостей | 28 | 33 | 0.95 | fail |
| Полнота отбора новостей | 28 | 31 | 0.9 | pass |
| Ошибочное объединение отрицательных пар | 1 | 10 | = 0 ошибок | fail |
| Полнота объединения положительных пар | 5 | 10 | 0.9 | fail |
| Правильность заявленных связей комментарий → событие | 0 | 4 | 0.9 | fail |
| Записи и ссылки вне окна | 0 | 59815 | = 0 ошибок | pass |
| Граничные пробы [start,end) | 58 | 58 | 1 | pass |
| Правильность числовых агрегатов | 24506 | 24506 | 1 | pass |
| Подтверждённость фактов брифа | 8840 | 8840 | 0.95 | pass |
| Выдуманные цены, даты, авторство, официальное подтверждение | 0 | 8840 | = 0 ошибок | pass |
| Согласие сегментных классов | 9 | 43 | нет | unverified |
| Согласие происхождения | 17 | 43 | нет | unverified |
| Согласие роли источника | 26 | 43 | нет | unverified |

## Методика

- Для семантических метрик используется замороженное самое широкое coverage-окно; узкое окно его не заменяет.
- Единица отбора — пара (пост, тема); пары и комментарии также проверяются отдельно по теме.
- Нет решения: false negative для recall, unverified для precision/отрицательных пар. Fail имеет приоритет при наблюдаемом нарушении порога.
- coverage.publications/channels/comments — все записи БД в окне; topic_publications — уникальные selected_news. Групповые счётчики — уникальные публикации, не сегменты.
- Автор берётся только из author_id/author_key БД; канал не подменяет автора. Origin пересчитывается по решениям, его истинность оценивается отдельно.
- Проверка времени охватывает сериализованные записи и ссылки, но не доказывает отсутствие скрытого влияния будущего на LLM.

Связи комментариев: `{"claimed_event_links": 4, "abstentions": 18, "other_types": 4, "missing": 0, "type:topic_level": 18, "type:project": 1, "type:other_subject": 3}`.
Явно помеченная предыстория: 0 вхождений; список в metrics.json.

## Отсутствующие входы

Нет.

## Точность отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/don_invest/5299"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/icodrops_sergey/2431"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31493"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31511"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/PowsGemCalls/49106"], "topic": "zec", "reason": "Решение не совпало с разметкой"}

## Полнота отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/whitelist1/7139"], "topic": "arc", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/markettwits/385049"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31487"], "topic": "zec", "reason": "Решение не совпало с разметкой"}

## Ошибочное объединение отрицательных пар

Ошибки и непроверенные случаи:

- Ошибка: {"pair": "pair-12", "topic": "eth", "links": ["https://t.me/markettwits/384699", "https://t.me/markettwits/385603"], "common_event_ids": ["e41-5b311a56519bddda"]}

## Полнота объединения положительных пар

Ошибки и непроверенные случаи:

- Ошибка: {"pair": "pair-01", "topic": "zec", "links": ["https://t.me/marketfeed/1039055", "https://t.me/markettwits/385234"], "common_event_ids": []}
- Ошибка: {"pair": "pair-02", "topic": "zec", "links": ["https://t.me/marketfeed/1039055", "https://t.me/crypto_hd/31484"], "common_event_ids": []}
- Ошибка: {"pair": "pair-04", "topic": "zec", "links": ["https://t.me/marketfeed/1041046", "https://t.me/markettwits/385538"], "common_event_ids": []}
- Ошибка: {"pair": "pair-08", "topic": "eth", "links": ["https://t.me/markettwits/384699", "https://t.me/WEB3_AGGREGATOR/422950"], "common_event_ids": []}
- Ошибка: {"pair": "pair-09", "topic": "eth", "links": ["https://t.me/markettwits/384699", "https://t.me/rawa_imagination/21078"], "common_event_ids": []}

## Правильность заявленных связей комментарий → событие

Ошибки и непроверенные случаи:

- Ошибка: {"topic": "zec", "links": ["https://t.me/icodrops_sergey/2426?comment=150547"], "expected": "author_thesis", "actual": "event:e36-9e94ec9cc7c059c8", "mapped_events": ["zec-rank9-0917"]}
- Ошибка: {"topic": "zec", "links": ["https://t.me/icodrops_sergey/2426?comment=150550"], "expected": "author_thesis", "actual": "event:e36-9e94ec9cc7c059c8", "mapped_events": ["zec-rank9-0917"]}
- Ошибка: {"topic": "zec", "links": ["https://t.me/icodrops_sergey/2426?comment=150552"], "expected": "project", "actual": "event:e36-9e94ec9cc7c059c8", "mapped_events": ["zec-rank9-0917"]}
- Ошибка: {"topic": "eth", "links": ["https://t.me/rawa_imagination/21078?comment=342794"], "expected": "author_thesis", "actual": "event:e43-e81e760cff5cd185", "mapped_events": ["bitmine-buy-27180-0914"]}

## Записи и ссылки вне окна

Числитель — нарушения; знаменатель — проверенные вхождения времени/ссылок. Включает время < start; явная предыстория отдельно.

Ошибок не обнаружено.

## Граничные пробы [start,end)

Ошибки и непроверенные случаи:

Ошибок не обнаружено.

## Правильность числовых агрегатов

Ошибки и непроверенные случаи:

Ошибок не обнаружено.

## Подтверждённость фактов брифа

news_pulse_ground.py: brief.md = рендер pulse.json; цитаты, заголовки, реплики и основания дословно есть в источнике БД; счётчики пересчитываются по участникам.

Ошибок не обнаружено.

## Выдуманные цены, даты, авторство, официальное подтверждение

Число в утверждении брифа, которого нет в связанном источнике. Бриф извлекающий: авторство и подтверждение не генерируются.

Ошибок не обнаружено.

## Согласие сегментных классов

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7137"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/don_invest/5299"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6921"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptonftded/3270"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "promo_service"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/cryptonftded/3277"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "promo_service"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/cryptonftded/3282"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "promo_service"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/icodrops_sergey/2426"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/icodrops_sergey/2431"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/385008"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/385049"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/markettwits/385132"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/markettwits/385211"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/385234"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/markettwits/385262"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/markettwits/385442"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/385524"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/markettwits/385538"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/385603"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4871"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4873"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96809"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96830"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96857"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "participant_reaction"]}
- Ошибка: {"links": ["https://t.me/krasnovcrypto/3756"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "promo_service"], "actual": ["participant_reaction"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422950"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423167"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423360"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/markettwits/384699"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31484"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31487"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["author_position", "promo_service"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31493"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31511"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21078"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/PowsGemCalls/49106"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["participant_reaction"], "actual": ["event"]}

## Согласие происхождения

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7139"], "topic": "arc", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/whitelist1/7149"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6921"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3270"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3277"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3282"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/icodrops_sergey/2426"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/markettwits/385008"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/markettwits/385049"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/markettwits/385132"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/markettwits/385211"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/markettwits/385255"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/markettwits/385442"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/markettwits/385524"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "own"}
- Ошибка: {"links": ["https://t.me/markettwits/385538"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/markettwits/385603"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4873"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96789"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96857"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422950"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423167"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423360"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "own"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31487"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31488"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31493"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21078"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}

## Согласие роли источника

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7139"], "topic": "arc", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "participant"}
- Ошибка: {"links": ["https://t.me/whitelist1/7149"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6921"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3270"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3277"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3282"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/icodrops_sergey/2426"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "editorial"}
- Ошибка: {"links": ["https://t.me/markettwits/385049"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/markettwits/385603"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4873"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/krasnovcrypto/3756"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "participant"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422657"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422950"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423360"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31487"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31511"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/PowsGemCalls/49106"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "participant", "actual": "author"}
