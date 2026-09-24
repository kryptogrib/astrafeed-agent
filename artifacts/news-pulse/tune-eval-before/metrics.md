# Независимая оценка news-first Pulse

Маленькая выборка — демо-проверка, не доказательство качества на всех данных. Общий балл не вычисляется.

Разметка: None. SHA256 всех файлов manifest.json проверены.
MD5 БД до/после: `8618099125a806df376354286ccd982e` / `8618099125a806df376354286ccd982e`.

Воспроизведение: `python3 docs/research/news_pulse_eval.py --db astrafeed.db`

Синтетические тесты: `python3 -m unittest discover -s tests/research -p test_news_pulse_eval.py -v`

| Метрика | Числитель | Знаменатель | Порог | Статус |
|---|---:|---:|---|---|
| Точность отбора новостей | 27 | 32 | 0.95 | fail |
| Полнота отбора новостей | 27 | 34 | 0.9 | fail |
| Ошибочное объединение отрицательных пар | 0 | 12 | = 0 ошибок | pass |
| Полнота объединения положительных пар | 1 | 12 | 0.9 | fail |
| Правильность заявленных связей комментарий → событие | 0 | 0 | 0.9 | unverified |
| Записи и ссылки вне окна | 0 | 19912 | = 0 ошибок | unverified |
| Граничные пробы [start,end) | 0 | 0 | 1 | unverified |
| Правильность числовых агрегатов | 11512 | 11770 | 1 | fail |
| Подтверждённость фактов брифа | 0 | 0 | 0.95 | unverified |
| Выдуманные цены, даты, авторство, официальное подтверждение | 0 | 0 | = 0 ошибок | unverified |
| Согласие сегментных классов | 3 | 43 | нет | unverified |
| Согласие происхождения | 10 | 43 | нет | unverified |
| Согласие роли источника | 22 | 43 | нет | unverified |

## Методика

- Для семантических метрик используется замороженное самое широкое coverage-окно; узкое окно его не заменяет.
- Единица отбора — пара (пост, тема); пары и комментарии также проверяются отдельно по теме.
- Нет решения: false negative для recall, unverified для precision/отрицательных пар. Fail имеет приоритет при наблюдаемом нарушении порога.
- coverage.publications/channels/comments — все записи БД в окне; topic_publications — уникальные selected_news. Групповые счётчики — уникальные публикации, не сегменты.
- Автор берётся только из author_id/author_key БД; канал не подменяет автора. Origin пересчитывается по решениям, его истинность оценивается отдельно.
- Проверка времени охватывает сериализованные записи и ссылки, но не доказывает отсутствие скрытого влияния будущего на LLM.

Связи комментариев: `{"claimed_event_links": 0, "abstentions": 24, "other_types": 0, "missing": 0, "type:topic_level": 24}`.
Явно помеченная предыстория: 0 вхождений; список в metrics.json.

## Отсутствующие входы

- Отсутствует artifacts/news-pulse/eth/2026-09-17..2026-09-19/decisions.json
- Отсутствует artifacts/news-pulse/zec/2026-09-17..2026-09-19/decisions.json

## Точность отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422896"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31517"], "topic": "zec", "reason": "Решение не совпало с разметкой"}

## Полнота отбора новостей

Ошибки и непроверенные случаи:

- Ошибка: {"links": ["https://t.me/icryptocom/8099"], "topic": "zec", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21127"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21151"], "topic": "eth", "reason": "Решение не совпало с разметкой"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21158"], "topic": "eth", "reason": "Решение не совпало с разметкой"}

## Ошибочное объединение отрицательных пар

Ошибки и непроверенные случаи:

Ошибок не обнаружено.

## Полнота объединения положительных пар

Ошибки и непроверенные случаи:

- Ошибка: {"pair": "tune-pair-01", "topic": "eth", "links": ["https://t.me/cryptoattack24/96773", "https://t.me/rawa_imagination/21109"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-02", "topic": "eth", "links": ["https://t.me/cryptoattack24/96795", "https://t.me/rawa_imagination/21117"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-03", "topic": "eth", "links": ["https://t.me/cryptoattack24/96819", "https://t.me/rawa_imagination/21121"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-04", "topic": "eth", "links": ["https://t.me/cryptoattack24/96862", "https://t.me/rawa_imagination/21151"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-05", "topic": "eth", "links": ["https://t.me/cryptoattack24/96890", "https://t.me/rawa_imagination/21158"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-06", "topic": "eth", "links": ["https://t.me/cryptoattack24/96862", "https://t.me/crypto_hd/31561"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-07", "topic": "eth", "links": ["https://t.me/crypto_hd/31561", "https://t.me/rawa_imagination/21151"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-08", "topic": "eth", "links": ["https://t.me/cryptoattack24/96819", "https://t.me/rawa_imagination/21127"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-09", "topic": "zec", "links": ["https://t.me/whitelist1/7150", "https://t.me/WEB3_AGGREGATOR/423534"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-10", "topic": "zec", "links": ["https://t.me/whitelist1/7151", "https://t.me/whitelist1/7152"], "common_event_ids": []}
- Ошибка: {"pair": "tune-pair-11", "topic": "zec", "links": ["https://t.me/cryptoattack24/96796", "https://t.me/crypto_hd/31503"], "common_event_ids": []}

## Правильность заявленных связей комментарий → событие

Ошибки и непроверенные случаи:

Категория не проверена.

## Записи и ссылки вне окна

Числитель — нарушения; знаменатель — проверенные вхождения времени/ссылок. Включает время < start; явная предыстория отдельно.

- Не проверено: {"run": "artifacts/news-pulse/eth/2026-09-17..2026-09-19", "reason": "Нет decisions.json"}
- Не проверено: {"run": "artifacts/news-pulse/zec/2026-09-17..2026-09-19", "reason": "Нет decisions.json"}
- Не проверено: "Отсутствует artifacts/news-pulse/eth/2026-09-17..2026-09-19/decisions.json"
- Не проверено: "Отсутствует artifacts/news-pulse/zec/2026-09-17..2026-09-19/decisions.json"

## Граничные пробы [start,end)

Ошибки и непроверенные случаи:

Категория не проверена.

## Правильность числовых агрегатов

Ошибки и непроверенные случаи:

- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "coverage.topic_publications", "actual": 163, "expected": 77, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e7-22b42433f32828c2.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422864"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e7-22b42433f32828c2.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422864"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e7-22b42433f32828c2.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422864"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e7-22b42433f32828c2.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/422864"], "links": ["https://t.me/WEB3_AGGREGATOR/422864"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e8-90c23fd28093f866.counts.unknown_authors", "actual": 6, "expected": 4, "links": ["https://t.me/WEB3_AGGREGATOR/422875", "https://t.me/WEB3_AGGREGATOR/422881", "https://t.me/WEB3_AGGREGATOR/422890", "https://t.me/cryptoattack24/96700"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e8-90c23fd28093f866.counts.found_origins", "actual": 6, "expected": 4, "links": ["https://t.me/WEB3_AGGREGATOR/422875", "https://t.me/WEB3_AGGREGATOR/422881", "https://t.me/WEB3_AGGREGATOR/422890", "https://t.me/cryptoattack24/96700"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e14-404fcfb394d23199.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e14-404fcfb394d23199.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e14-404fcfb394d23199.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e15-973a1583a4f608e0.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e15-973a1583a4f608e0.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e15-973a1583a4f608e0.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e16-9c92264eab36d2e6.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e16-9c92264eab36d2e6.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e16-9c92264eab36d2e6.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e17-e082de458c806ee3.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e17-e082de458c806ee3.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e17-e082de458c806ee3.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e17-e082de458c806ee3.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/422908"], "links": ["https://t.me/WEB3_AGGREGATOR/422908"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e21-16f78728ce8e3b83.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422923"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e21-16f78728ce8e3b83.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422923"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e25-e19f408c075bdc35.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/whitelist1/7135"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e25-e19f408c075bdc35.counts.found_origins", "actual": 3, "expected": 1, "links": ["https://t.me/whitelist1/7135"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e26-88529cb7a1df6223.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/whitelist1/7135"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e26-88529cb7a1df6223.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/whitelist1/7135"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e26-88529cb7a1df6223.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/whitelist1/7135"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e29-7c75f8da91a1694f.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422986"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e29-7c75f8da91a1694f.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422986"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e29-7c75f8da91a1694f.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422986"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e46-6e3370cdcd3a20a2.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e46-6e3370cdcd3a20a2.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e53-016e829b1d954627.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423117"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e53-016e829b1d954627.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423117"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e59-fc76b3cacccdad42.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423151"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e59-fc76b3cacccdad42.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423151"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e73-47c4ef28758dec5b.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423244"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "decisions.e73-47c4ef28758dec5b.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423244"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e73-47c4ef28758dec5b.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423244"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e77-ee2be10c2dc48116.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423252"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-09..2026-09-23", "path": "pulse.e77-ee2be10c2dc48116.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423252"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "coverage.topic_publications", "actual": 52, "expected": 29, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e3-8a75dfb4c419fe87.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e3-8a75dfb4c419fe87.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "decisions.e3-8a75dfb4c419fe87.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/423100"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e4-6e3370cdcd3a20a2.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e4-6e3370cdcd3a20a2.counts.found_origins", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "decisions.e4-6e3370cdcd3a20a2.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e4-6e3370cdcd3a20a2.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "decisions.e4-6e3370cdcd3a20a2.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/423100"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/423100"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e20-fc76b3cacccdad42.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423151"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "decisions.e20-fc76b3cacccdad42.n_unknown_origin", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423151"]}
- Ошибка: {"run": "artifacts/news-pulse/arc/2026-09-16T11-01-01-00-00..2026-09-17T11-01-01-00-00", "path": "pulse.e20-fc76b3cacccdad42.counts.unknown_origin", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423151"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "coverage.topic_publications", "actual": 324, "expected": 200, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e12-73023517f884f322.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21038"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e12-73023517f884f322.n_unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/rawa_imagination/21038"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e12-73023517f884f322.counts.unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/rawa_imagination/21038"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e20-82b5b1f337480d15.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e20-82b5b1f337480d15.n_unknown_origin", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e20-82b5b1f337480d15.counts.unknown_origin", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e21-1887f0929ee5fc89.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e21-1887f0929ee5fc89.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e21-1887f0929ee5fc89.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e21-1887f0929ee5fc89.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422716"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e24-c5789369b62148d8.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/422727"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e24-c5789369b62148d8.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422727"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e24-c5789369b62148d8.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422727"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e24-c5789369b62148d8.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/422727"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/422727"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e80-66c13803e6f5dcc6.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422959"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e80-66c13803e6f5dcc6.counts.found_origins", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422959"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e102-e54cfdccf7a9af09.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31434"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e102-e54cfdccf7a9af09.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31434"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e114-4a80791d4d373ca9.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21099"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e114-4a80791d4d373ca9.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21099"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e114-4a80791d4d373ca9.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21099"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e120-082c10a3e41004ce.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e120-082c10a3e41004ce.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e120-082c10a3e41004ce.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e132-73a28409f802189b.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e132-73a28409f802189b.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e132-73a28409f802189b.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e132-73a28409f802189b.found_origins", "actual": ["https://t.me/crypto_hd/31476"], "expected": [], "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e140-ccb3348375727b67.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423249"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e140-ccb3348375727b67.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423249"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e143-d57ff52e9ff96871.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/cryptoattack24/96795"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e143-d57ff52e9ff96871.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/cryptoattack24/96795"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e143-d57ff52e9ff96871.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/cryptoattack24/96795"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e143-d57ff52e9ff96871.found_origins", "actual": [], "expected": ["https://t.me/cryptoattack24/96795"], "links": ["https://t.me/cryptoattack24/96795"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e167-bac60b19c932c9f7.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e167-bac60b19c932c9f7.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e180-de601007cbbd0021.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e180-de601007cbbd0021.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e180-de601007cbbd0021.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e190-214105df9740c721.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e190-214105df9740c721.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e190-214105df9740c721.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e190-214105df9740c721.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423486"], "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e191-8e897d7cf4cc9e5a.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e191-8e897d7cf4cc9e5a.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e191-8e897d7cf4cc9e5a.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e191-8e897d7cf4cc9e5a.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423486"], "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e192-4135e6e469d135c8.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e192-4135e6e469d135c8.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e192-4135e6e469d135c8.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e192-4135e6e469d135c8.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423486"], "links": ["https://t.me/WEB3_AGGREGATOR/423486"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e194-6c9ebc2a9189c3e3.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423491"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e194-6c9ebc2a9189c3e3.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423491"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e194-6c9ebc2a9189c3e3.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423491"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e194-6c9ebc2a9189c3e3.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/423491"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/423491"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e220-f9edb4e95b2ba139.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96890"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "decisions.e220-f9edb4e95b2ba139.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96890"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-09..2026-09-23", "path": "pulse.e220-f9edb4e95b2ba139.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96890"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "coverage.topic_publications", "actual": 149, "expected": 100, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e12-66c13803e6f5dcc6.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422959"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e12-66c13803e6f5dcc6.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422959"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e12-66c13803e6f5dcc6.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/422959"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e19-e36d939aea9f7b50.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/spidersjournal/18913"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e19-e36d939aea9f7b50.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/spidersjournal/18913"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e19-e36d939aea9f7b50.n_unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/spidersjournal/18913"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e19-e36d939aea9f7b50.counts.unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/spidersjournal/18913"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e33-0214b32ee97f5b0e.n_reprints", "actual": 0, "expected": 2, "links": ["https://t.me/WEB3_AGGREGATOR/423051", "https://t.me/moni_talks/12225"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e33-0214b32ee97f5b0e.counts.reprints", "actual": 0, "expected": 2, "links": ["https://t.me/WEB3_AGGREGATOR/423051", "https://t.me/moni_talks/12225"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e33-0214b32ee97f5b0e.n_unknown_origin", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423051", "https://t.me/moni_talks/12225"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e33-0214b32ee97f5b0e.counts.unknown_origin", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423051", "https://t.me/moni_talks/12225"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e49-35468ac9257fbf2b.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e49-35468ac9257fbf2b.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e49-35468ac9257fbf2b.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31457"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e62-73a28409f802189b.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e62-73a28409f802189b.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e62-73a28409f802189b.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e62-73a28409f802189b.found_origins", "actual": ["https://t.me/crypto_hd/31476"], "expected": [], "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e69-1b1b8d85d0809f34.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423249"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e69-1b1b8d85d0809f34.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423249"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e69-1b1b8d85d0809f34.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423249"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e97-82ecaa6ca7cc3ec2.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e97-82ecaa6ca7cc3ec2.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e97-82ecaa6ca7cc3ec2.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e97-82ecaa6ca7cc3ec2.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/rawa_imagination/21126"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e100-28952caa1756900e.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423399"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e100-28952caa1756900e.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423399"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e100-28952caa1756900e.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423399"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e108-833ae36cd4bdc767.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "decisions.e108-833ae36cd4bdc767.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/eth/2026-09-14T12-33-46-00-00..2026-09-21T12-44-54-00-00", "path": "pulse.e108-833ae36cd4bdc767.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423462"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "coverage.topic_publications", "actual": 221, "expected": 116, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e3-971d32ab6b572c62.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31368"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e3-971d32ab6b572c62.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31368"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e3-971d32ab6b572c62.n_unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/crypto_hd/31368"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e3-971d32ab6b572c62.counts.unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/crypto_hd/31368"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e4-ac0f45885f27c970.n_reprints", "actual": 0, "expected": 2, "links": ["https://t.me/Defiscamcheck/4864", "https://t.me/WEB3_AGGREGATOR/422763"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e4-ac0f45885f27c970.counts.reprints", "actual": 0, "expected": 2, "links": ["https://t.me/Defiscamcheck/4864", "https://t.me/WEB3_AGGREGATOR/422763"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e4-ac0f45885f27c970.n_unknown_origin", "actual": 2, "expected": 0, "links": ["https://t.me/Defiscamcheck/4864", "https://t.me/WEB3_AGGREGATOR/422763"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e4-ac0f45885f27c970.counts.unknown_origin", "actual": 2, "expected": 0, "links": ["https://t.me/Defiscamcheck/4864", "https://t.me/WEB3_AGGREGATOR/422763"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e17-6725051e7f89c31d.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e17-6725051e7f89c31d.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e17-6725051e7f89c31d.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e18-a3c0fab7151541aa.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e18-a3c0fab7151541aa.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e18-a3c0fab7151541aa.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e18-a3c0fab7151541aa.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423054"], "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e20-b763e88877c22058.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e20-b763e88877c22058.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e20-b763e88877c22058.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e20-b763e88877c22058.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423054"], "links": ["https://t.me/WEB3_AGGREGATOR/423054"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e34-6b3a56c4451e89dd.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e34-6b3a56c4451e89dd.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e34-6b3a56c4451e89dd.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e34-6b3a56c4451e89dd.found_origins", "actual": ["https://t.me/crypto_hd/31476"], "expected": [], "links": ["https://t.me/crypto_hd/31476"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e38-ffc17b4e4f13ed92.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31484"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e38-ffc17b4e4f13ed92.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/crypto_hd/31484"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e61-c7b91c81e0131a7b.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423315"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e61-c7b91c81e0131a7b.n_unknown_origin", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423315"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e61-c7b91c81e0131a7b.counts.unknown_origin", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423315"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e62-d88b56862e4c8afd.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e62-d88b56862e4c8afd.n_reprints", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e62-d88b56862e4c8afd.counts.reprints", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e63-5a98b5b841cf7d8f.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e63-5a98b5b841cf7d8f.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e63-5a98b5b841cf7d8f.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e63-5a98b5b841cf7d8f.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e64-3b4cd34bf36b1935.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e64-3b4cd34bf36b1935.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e64-3b4cd34bf36b1935.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e64-3b4cd34bf36b1935.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e80-a01178250b644dc1.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/Defiscamcheck/4873"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e80-a01178250b644dc1.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/Defiscamcheck/4873"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e84-a01178250b644dc1.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423360"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e84-a01178250b644dc1.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423360"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e86-9e44c58cc44b5092.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423362"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e86-9e44c58cc44b5092.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423362"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e86-9e44c58cc44b5092.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423362"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e86-9e44c58cc44b5092.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423362"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e104-ee68fd1f0d990054.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e104-ee68fd1f0d990054.n_unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e104-ee68fd1f0d990054.counts.unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e105-e3785ee6e408a419.counts.found_origins", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e105-e3785ee6e408a419.n_unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e105-e3785ee6e408a419.counts.unknown_origin", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e105-e3785ee6e408a419.found_origins", "actual": [], "expected": ["https://t.me/WEB3_AGGREGATOR/423441"], "links": ["https://t.me/WEB3_AGGREGATOR/423441"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e108-8494c169af5ec96a.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e108-8494c169af5ec96a.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e108-8494c169af5ec96a.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e108-8494c169af5ec96a.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e109-2d0dd397f65da950.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e109-2d0dd397f65da950.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e109-2d0dd397f65da950.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e109-2d0dd397f65da950.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/markettwits/385538"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e122-bd230e73c42da7a6.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423488"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e122-bd230e73c42da7a6.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423488"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e122-bd230e73c42da7a6.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423488"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e129-876cb86f25cacfe3.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e129-876cb86f25cacfe3.counts.found_origins", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e129-876cb86f25cacfe3.n_reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e129-876cb86f25cacfe3.counts.reprints", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e129-876cb86f25cacfe3.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/423506"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e130-a2017af155651dcb.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e130-a2017af155651dcb.counts.found_origins", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e130-a2017af155651dcb.found_origins", "actual": ["https://t.me/WEB3_AGGREGATOR/423506"], "expected": [], "links": ["https://t.me/WEB3_AGGREGATOR/423506"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e146-0b7d431d19eb08f2.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e146-0b7d431d19eb08f2.n_reprints", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e146-0b7d431d19eb08f2.counts.reprints", "actual": 2, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e147-b267d67ceebe60db.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e147-b267d67ceebe60db.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e147-b267d67ceebe60db.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e147-b267d67ceebe60db.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e148-f377aa4e826bdaf7.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e148-f377aa4e826bdaf7.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e148-f377aa4e826bdaf7.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e148-f377aa4e826bdaf7.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e149-b46902bb8c2875d9.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e149-b46902bb8c2875d9.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e149-b46902bb8c2875d9.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e149-b46902bb8c2875d9.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e150-a9254976e2b50adf.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e150-a9254976e2b50adf.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e150-a9254976e2b50adf.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e150-a9254976e2b50adf.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e151-4a18d08909169790.n_reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e151-4a18d08909169790.counts.reprints", "actual": 1, "expected": 0, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "decisions.e151-4a18d08909169790.n_unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-09..2026-09-23", "path": "pulse.e151-4a18d08909169790.counts.unknown_origin", "actual": 0, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423606"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "coverage.topic_publications", "actual": 122, "expected": 71, "links": []}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e11-cbe062b0da67e3df.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423204"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "decisions.e11-cbe062b0da67e3df.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423204"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e11-cbe062b0da67e3df.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423204"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e12-ffc17b4e4f13ed92.counts.unknown_authors", "actual": 3, "expected": 1, "links": ["https://t.me/crypto_hd/31484"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "decisions.e12-ffc17b4e4f13ed92.n_reprints", "actual": 3, "expected": 1, "links": ["https://t.me/crypto_hd/31484"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e12-ffc17b4e4f13ed92.counts.reprints", "actual": 3, "expected": 1, "links": ["https://t.me/crypto_hd/31484"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e25-105292f1b15b7551.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96794"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "decisions.e25-105292f1b15b7551.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96794"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e25-105292f1b15b7551.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/cryptoattack24/96794"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e34-d88b56862e4c8afd.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "decisions.e34-d88b56862e4c8afd.n_reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e34-d88b56862e4c8afd.counts.reprints", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423316"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e51-a01178250b644dc1.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/Defiscamcheck/4873"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e51-a01178250b644dc1.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/Defiscamcheck/4873"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e55-a01178250b644dc1.counts.unknown_authors", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423360"]}
- Ошибка: {"run": "artifacts/news-pulse/zec/2026-09-16T06-10-19-00-00..2026-09-21T06-04-32-00-00", "path": "pulse.e55-a01178250b644dc1.counts.found_origins", "actual": 2, "expected": 1, "links": ["https://t.me/WEB3_AGGREGATOR/423360"]}
- Не проверено: {"run": "artifacts/news-pulse/eth/2026-09-17..2026-09-19", "reason": "Без decisions нельзя пересчитать отбор и группы"}
- Не проверено: {"run": "artifacts/news-pulse/zec/2026-09-17..2026-09-19", "reason": "Без decisions нельзя пересчитать отбор и группы"}
- Не проверено: "Отсутствует artifacts/news-pulse/eth/2026-09-17..2026-09-19/decisions.json"
- Не проверено: "Отсутствует artifacts/news-pulse/zec/2026-09-17..2026-09-19/decisions.json"

## Подтверждённость фактов брифа

ручная проверка; задача D2

Категория не проверена.

## Выдуманные цены, даты, авторство, официальное подтверждение

ручная проверка; задача D2

Категория не проверена.

## Согласие сегментных классов

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7151"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7152"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96747"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96773"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96794"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96795"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96796"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96819"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96824"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96827"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96837"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96838"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96862"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96890"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "event", "promo_service"], "actual": ["event", "participant_reaction", "promo_service"]}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["author_position", "promo_service"], "actual": ["event"]}
- Ошибка: {"links": ["https://t.me/icryptocom/8099"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": ["event"], "actual": ["promo_service"]}
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
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21039"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21055"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["author_position"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21060"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21109"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21121"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["event", "promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21127"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21151"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21158"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": ["event", "promo_service", "redistribution"], "actual": ["promo_service"]}

## Согласие происхождения

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7151"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/whitelist1/7152"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/Defiscamcheck/4878"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96747"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96773"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96795"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96819"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96827"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96837"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3265"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3266"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3269"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/icryptocom/8099"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422896"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422902"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423316"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423395"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "repost", "actual": "own"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423534"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31368"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "own", "actual": "retelling"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21039"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21060"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21109"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21121"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "own"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21127"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21151"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21158"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "retelling", "actual": "unknown"}

## Согласие роли источника

Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.

- Ошибка: {"links": ["https://t.me/whitelist1/7150"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7152"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/cryptoattack24/96795"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3265"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3266"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3267"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "editorial"}
- Ошибка: {"links": ["https://t.me/cryptonftded/3269"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/whitelist1/7156"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/icryptocom/8099"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/Slavik_investor_updates/6910"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/422896"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "unknown", "actual": "author"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423316"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "author", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/WEB3_AGGREGATOR/423534"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31517"], "topic": "zec", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "author"}
- Ошибка: {"links": ["https://t.me/crypto_hd/31561"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21039"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21051"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21117"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21127"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21151"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
- Ошибка: {"links": ["https://t.me/rawa_imagination/21158"], "topic": "eth", "reason": "Решение не совпало с разметкой", "expected": "editorial", "actual": "unknown"}
