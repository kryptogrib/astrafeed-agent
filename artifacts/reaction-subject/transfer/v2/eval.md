# Reaction subject v2 on transfer channels — generated tables

New channels, never used for dev or prompts. Labels are preliminary and not human-checked;
43 of 112 are disputed. Gold targets: {'event': 12, 'other_subject': 55, 'author_thesis': 18, 'unclear': 14, 'project': 13}.

## all

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 112 | 112 | 0 | 0 | 12 | 1 | 11 | 2 | 100 | 0 | 0 | 0.107 | 0.01 |
| v2 context | 112 | 112 | 0 | 5 | 94 | 61 | 33 | 2 | 13 | 0 | 0 | 0.839 | 0.622 |
| v2 context+id | 112 | 112 | 0 | 5 | 87 | 54 | 33 | 2 | 20 | 7 | 0 | 0.777 | 0.551 |
| v2 context+id+verify | 112 | 112 | 0 | 5 | 83 | 52 | 31 | 0 | 24 | 7 | 4 | 0.741 | 0.531 |

## undisputed

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 69 | 69 | 0 | 0 | 3 | 0 | 3 | 1 | 66 | 0 | 0 | 0.043 | 0.0 |
| v2 context | 69 | 69 | 0 | 4 | 55 | 46 | 9 | 0 | 10 | 0 | 0 | 0.797 | 0.807 |
| v2 context+id | 69 | 69 | 0 | 4 | 54 | 45 | 9 | 0 | 11 | 1 | 0 | 0.783 | 0.789 |
| v2 context+id+verify | 69 | 69 | 0 | 4 | 53 | 44 | 9 | 0 | 12 | 1 | 1 | 0.768 | 0.772 |

## disputed

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 43 | 43 | 0 | 0 | 9 | 1 | 8 | 1 | 34 | 0 | 0 | 0.209 | 0.024 |
| v2 context | 43 | 43 | 0 | 1 | 39 | 15 | 24 | 2 | 3 | 0 | 0 | 0.907 | 0.366 |
| v2 context+id | 43 | 43 | 0 | 1 | 33 | 9 | 24 | 2 | 9 | 6 | 0 | 0.767 | 0.22 |
| v2 context+id+verify | 43 | 43 | 0 | 1 | 30 | 8 | 22 | 0 | 12 | 6 | 3 | 0.698 | 0.195 |

## chain_complete

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 106 | 106 | 0 | 0 | 12 | 1 | 11 | 2 | 94 | 0 | 0 | 0.113 | 0.011 |
| v2 context | 106 | 106 | 0 | 5 | 91 | 58 | 33 | 2 | 10 | 0 | 0 | 0.858 | 0.617 |
| v2 context+id | 106 | 106 | 0 | 5 | 85 | 52 | 33 | 2 | 16 | 6 | 0 | 0.802 | 0.553 |
| v2 context+id+verify | 106 | 106 | 0 | 5 | 81 | 50 | 31 | 0 | 20 | 6 | 4 | 0.764 | 0.532 |

## missing_parent

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0.0 | 0.0 |
| v2 context | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0.0 | 0.0 |
| v2 context+id | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0.0 | 0.0 |
| v2 context+id+verify | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0.0 | 0.0 |

## nontext_parent

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0.0 | 0.0 |
| v2 context | 3 | 3 | 0 | 0 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 1.0 | 1.0 |
| v2 context+id | 3 | 3 | 0 | 0 | 2 | 2 | 0 | 0 | 1 | 1 | 0 | 0.667 | 0.667 |
| v2 context+id+verify | 3 | 3 | 0 | 0 | 2 | 2 | 0 | 0 | 1 | 1 | 0 | 0.667 | 0.667 |

## news

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 38 | 38 | 0 | 0 | 3 | 1 | 2 | 2 | 35 | 0 | 0 | 0.079 | 0.03 |
| v2 context | 38 | 38 | 0 | 2 | 34 | 20 | 14 | 2 | 2 | 0 | 0 | 0.895 | 0.606 |
| v2 context+id | 38 | 38 | 0 | 2 | 34 | 20 | 14 | 2 | 2 | 0 | 0 | 0.895 | 0.606 |
| v2 context+id+verify | 38 | 38 | 0 | 2 | 30 | 18 | 12 | 0 | 6 | 0 | 4 | 0.789 | 0.545 |

## topic_shift

| arm | n | answered | cache_miss | unprocessed | claimed | claim_correct | claim_wrong | false_event | abstained | status_no_id | status_rejected | coverage | recall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 74 | 74 | 0 | 0 | 9 | 0 | 9 | 0 | 65 | 0 | 0 | 0.122 | 0.0 |
| v2 context | 74 | 74 | 0 | 3 | 60 | 41 | 19 | 0 | 11 | 0 | 0 | 0.811 | 0.631 |
| v2 context+id | 74 | 74 | 0 | 3 | 53 | 34 | 19 | 0 | 18 | 7 | 0 | 0.716 | 0.523 |
| v2 context+id+verify | 74 | 74 | 0 | 3 | 53 | 34 | 19 | 0 | 18 | 7 | 0 | 0.716 | 0.523 |

## event и thesis отдельно (all)

| arm | event: верно / заявлено | event: найдено / в эталоне | ложных event | thesis: класс заявлен / в эталоне |
|---|---|---|---|---|
| baseline | 0/2 | 0/12 | 2 | 0/18 |
| v2 context | 5/7 | 5/12 | 2 | 5/18 |
| v2 context+id | 3/5 | 3/12 | 2 | 0/18 |
| v2 context+id+verify | 1/1 | 1/12 | 0 | 0/18 |

## Доступность цели и качество связи

Без извлечённого id связь по контракту невозможна: для таких меток верный ответ системы — воздержание (unclear/no_id), а промах — это пробел извлечения, не связывателя.

| arm | группа | в эталоне | связано верно | связано с другой целью | воздержание | прочие статусы |
|---|---|---|---|---|---|---|
| baseline | event, id есть в посте | 5 | 0 | 0 | 5 | 0 |
| baseline | event, событие не извлечено | 7 | 0 | 4 | 3 | 0 |
| baseline | thesis, тезис не извлечён | 18 | 0 | 2 | 16 | 0 |
| v2 context | event, id есть в посте | 5 | 3 | 2 | 0 | 0 |
| v2 context | event, событие не извлечено | 7 | 2 | 5 | 0 | 0 |
| v2 context | thesis, тезис не извлечён | 18 | 5 | 10 | 3 | 0 |
| v2 context+id | event, id есть в посте | 5 | 3 | 2 | 0 | 0 |
| v2 context+id | event, событие не извлечено | 7 | 0 | 5 | 2 | 0 |
| v2 context+id | thesis, тезис не извлечён | 18 | 0 | 10 | 8 | 0 |
| v2 context+id+verify | event, id есть в посте | 5 | 1 | 2 | 2 | 0 |
| v2 context+id+verify | event, событие не извлечено | 7 | 0 | 5 | 2 | 0 |
| v2 context+id+verify | thesis, тезис не извлечён | 18 | 0 | 10 | 8 | 0 |

Run: {'model': 'deepseek/deepseek-v4-flash', 'schemas': ['reaction-subject/v2', 'reaction-subject-verify/v2'], 'calls': 117, 'cache_hits': 0, 'cache_misses': 0, 'spent_usd': 0.01404, 'llm_seconds': 410.4, 'wall_seconds': 410.5, 'missing_estimate_usd': 0, 'note': 'verify misses appear only after the first pass for that comment is cached'}

