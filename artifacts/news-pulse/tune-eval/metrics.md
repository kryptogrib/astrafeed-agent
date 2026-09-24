# Независимая оценка news-first Pulse

Маленькая выборка — демо-проверка, не доказательство качества на всех данных. Общий балл не вычисляется.

Разметка: None. SHA256 всех файлов manifest.json проверены.
MD5 БД до/после: `8618099125a806df376354286ccd982e` / `8618099125a806df376354286ccd982e`.

Воспроизведение: `python3 docs/research/news_pulse_eval.py --db astrafeed.db`

Синтетические тесты: `python3 -m unittest discover -s tests/research -p test_news_pulse_eval.py -v`

| Метрика | Числитель | Знаменатель | Порог | Статус |
|---|---:|---:|---|---|
| Точность отбора новостей | 31 | 32 | 0.95 | pass |
| Полнота отбора новостей | 31 | 34 | 0.9 | pass |
| Ошибочное объединение отрицательных пар | 0 | 12 | = 0 ошибок | pass |
| Полнота объединения положительных пар | 9 | 12 | 0.9 | fail |
| Правильность заявленных связей комментарий → событие | 1 | 1 | 0.9 | pass |
| Записи и ссылки вне окна | 0 | 59815 | = 0 ошибок | pass |
| Граничные пробы [start,end) | 0 | 0 | 1 | unverified |
| Правильность числовых агрегатов | 24506 | 24506 | 1 | pass |
| Подтверждённость фактов брифа | 8840 | 8840 | 0.95 | pass |
| Выдуманные цены, даты, авторство, официальное подтверждение | 0 | 8840 | = 0 ошибок | pass |
| Согласие сегментных классов | 7 | 43 | нет | unverified |
| Согласие происхождения | 18 | 43 | нет | unverified |
| Согласие роли источника | 27 | 43 | нет | unverified |

## Методика

- Для семантических метрик используется замороженное самое широкое coverage-окно; узкое окно его не заменяет.
- Единица отбора — пара (пост, тема); пары и комментарии также проверяются отдельно по теме.
- Нет решения: false negative для recall, unverified для precision/отрицательных пар. Fail имеет приоритет при наблюдаемом нарушении порога.
- coverage.publications/channels/comments — все записи БД в окне; topic_publications — уникальные selected_news. Групповые счётчики — уникальные публикации, не сегменты.
- Автор берётся только из author_id/author_key БД; канал не подменяет автора. Origin пересчитывается по решениям, его истинность оценивается отдельно.
- Проверка времени охватывает сериализованные записи и ссылки, но не доказывает отсутствие скрытого влияния будущего на LLM.

Связи комментариев: `{"claimed_event_links": 1, "abstentions": 14, "other_types": 9, "missing": 0, "type:other_subject": 7, "type:topic_level": 14, "type:project": 2}`.
Явно помеченная предыстория: 0 вхождений; список в metrics.json.

## Отсутствующие входы

Нет.

## Точность отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой"}

## Полнота отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой"}

## Ошибочное объединение отрицательных пар

Ошибки и непроверенные случаи:

Ошибок не обнаружено.

## Полнота объединения положительных пар

Ошибки и непроверенные случаи:

- Ошибка: {"pair": "tune-pair-09", "topic": "zec", "links": ["https://t.me/whitelist1/7150", "https://t.me/WEB3_AGGREGATOR/423534"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-10", "topic": "zec", "links": ["https://t.me/whitelist1/7151", "https://t.me/whitelist1/7152"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-11", "topic": "zec", "links": ["https://t.me/cryptoattack24/96796", "https://t.me/crypto_hd/31503"], "common_event_ids": []}

## Правильность заявленных связей комментарий → событие

Ошибки и непроверенные случаи:

Ошибок не обнаружено.

## Записи и ссылки вне окна

Числитель — нарушения; знаменатель — проверенные вхождения времени/ссылок. Включает время < start; явная предыстория отдельно.

Ошибок не обнаружено.

## Граничные пробы [start,end)

Ошибки и непроверенные случаи:

Категория не проверена.

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

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7151"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7152"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event", "redistribution"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96747"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96773"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96794"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96795"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96796"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96819"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96824"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96827"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96837"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96838"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96862"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "promo_service"], "actual": ["event", "participant_reaction", "promo_service"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422896"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422902"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423011"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423316"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "promo_service", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423395"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423534"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["promo_service"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31503"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31517"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21039"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21055"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21060"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21109"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21121"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21158"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}

## Согласие происхождения

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96747"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96794"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96795"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96819"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96827"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96837"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96862"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3265"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3266"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3269"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423011"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423395"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "own"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21039"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21060"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21109"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21121"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21127"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}

## Согласие роли источника

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "editorial"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96747"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96773"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96824"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3265"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3266"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3269"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "editorial"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423316"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "editorial"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31517"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21151"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
