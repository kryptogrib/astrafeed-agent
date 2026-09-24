# Author-thesis extraction — regression experiment (not a holdout)

Transfer sample already seen at labelling and after v2. Labels are preliminary.
Old labels.jsonl was not edited. A specific link needs a matched gold claim, not the class name.

## Извлечение

- постов: 26; извлечено тезисов: 24
- ожидаемых авторских (rank 1–3): верных 10 / 41, пропусков 31
- overflow тоже извлечён: 0 / 2
- чужих/цитируемых извлечено: 0; лишних: 14
- доступность нужного тезиса для связывателя: 6 / 16

## Связи с конкретным тезисом

| arm | n | specific_ok | claimed | wrong | class_only | precision | recall_linkable | recall_available | unprocessed | cache_miss |
|---|---|---|---|---|---|---|---|---|---|---|
| A v2 context+id+verify | 18 | 0 | 0 | 0 | 0 | None | 0.0 | 0.0 | 0 | 0 |
| B v2 context+id+verify | 18 | 4 | 6 | 2 | 2 | 0.667 | 0.25 | 0.667 | 0 | 0 |
| A v2 context+id | 18 | 0 | 0 | 0 | 0 | None | 0.0 | 0.0 | 0 | 0 |
| B v2 context+id | 18 | 4 | 6 | 2 | 2 | 0.667 | 0.25 | 0.667 | 0 | 0 |

## Срезы (B vs A, context+id+verify)

| срез | n | A specific | B specific | A recall | B recall |
|---|---|---|---|---|---|
| all | 18 | 0 | 4 | 0.0 | 0.25 |
| undisputed | 4 | 0 | 3 | 0.0 | 0.75 |
| disputed | 14 | 0 | 1 | 0.0 | 0.083 |
| chain_complete | 17 | 0 | 4 | 0.0 | 0.267 |
| missing_parent | 0 | 0 | 0 | None | None |
| nontext_parent | 1 | 0 | 0 | 0.0 | 0.0 |

## Регрессия event-связей (старые метки)

| arm | event верно/заявлено | найдено/в эталоне | ложных event | общая полнота |
|---|---|---|---|---|
| A v2 context+id+verify | 1/1 | 1/12 | 0 | 0.531 |
| B v2 context+id+verify | 1/1 | 1/12 | 0 | 0.52 |
| A v2 context+id | 3/5 | 3/12 | 2 | 0.551 |
| B v2 context+id | 3/4 | 3/12 | 1 | 0.541 |

## Конкретные изменения A → B

### Новые верные конкретные связи (4)
- «Почему» gold=gold:Nat_Selection/7228:1 A=unclear/None/ok B=author_thesis/th-c9b6d6bfd3b1b6bb/ok
- «На чартах coinbase/Bitfinex (USA traders) на TF H1 кластера обьемные сверху в пин-баре. ИМХО если правильно понимаю, име» gold=gold:Nat_Selection/7228:1 A=unclear/None/no_id B=author_thesis/th-c9b6d6bfd3b1b6bb/ok
- «TLDR: такое если торговать, то после того, как увидим реакцию на такой пинбар» gold=gold:Nat_Selection/7228:1 A=unclear/None/no_id B=author_thesis/th-c9b6d6bfd3b1b6bb/ok
- «Shёрт 👇🏻» gold=gold:Nat_Selection/7228:1 A=project/None/ok B=author_thesis/th-c9b6d6bfd3b1b6bb/ok

### Новые ложные конкретные связи (2)
- «Что за медвежий div? Что за индикатор» gold=gold:CoinMetrika/4551:2 A=unclear/None/no_id B=author_thesis/th-0190679bbcbd2bb6/ok
- «Ну оно все уже не первой свежести. Мне только стандарт и нравится» gold=gold:maxshitpostit/842:2 A=other_subject/None/ok B=author_thesis/th-b1ab7f5c39f270af/ok

### Потерянные конкретные связи (0)
- нет

### Изменившиеся event-связи (0)
- нет

## Стоимость и задержка

- extract: calls=0 hits=26 usd=0.00389 llm_s=117.9
- A (cached v2): hits=117 usd=0.01404 (повторное чтение, не новый расход)
- B: calls=49 hits=67 usd=0.01329 llm_s=410.7
- новый расход этого шага (usage): extract $0.00389 + B-payloads с тезисами $0.00604 = $0.00993
- серия v1+v2+transfer+этот шаг: $0.04426 из $1

Полный разбор, Pulse до/после и команды: [report.md](report.md).

