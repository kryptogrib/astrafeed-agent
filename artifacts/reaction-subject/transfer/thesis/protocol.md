# Протокол: извлечение авторских тезисов (предварительная разметка)

Статус разметки: **предварительная, одного агента**. Выборка transfer уже просмотрена при разметке v2 и в отчёте fb3bd91. Это **регрессионный эксперимент**, не независимый holdout.

Зафиксировано **до** чтения ответов извлекателя и связывателя B.

## Что не меняется

- `artifacts/reaction-subject/labels.jsonl` и `transfer/labels.jsonl`
- `transfer/threads.jsonl`, `baseline.jsonl`, `snapshot.json`, обе БД
- кеши v1, v2 и transfer/v2 (новые ключи можно добавить, старые записи не переписывать)
- промпт связывателя v2, проверка событий, выборка, production, объединение событий, сборщик

## Вход извлекателя

Только `requested_topic` и текст исходного поста. Комментарии, эталонные метки, события и ответы связывателя в payload запрещены. Проверка `leaks_extract` это ловит.

## Что считается тезисом

Собственный прогноз, оценка или совет автора канала. Не событие, не реклама/рефка, не чужая позиция (питч Pendle, «аналитики считают», «команда думает»). Не придумывать тезис для каждого поста. Если явных тезисов больше трёх — в золоте `overflow`, извлекатель должен вернуть `truncated=true`.

## Сопоставление, не объявление моделью эталона

- У золота свой `gold_id` (`gold:<channel>/<post>:<rank>`).
- У извлечённого тезиса свой `thesis_id` = `th-` + sha256(url+quote)[:16]. Id модели отбрасывается.
- Совпадение: пересечение символьных границ **и** слова более короткой цитаты ⊆ словам более длинной.
- Старый `target_id=null` у thesis-меток **не** делает любой новый id ошибкой.
- Совпадение класса `author_thesis` **не** засчитывается как конкретная связь.

Контракт связывателя прежний: без id события/тезиса этого поста конкретной связи нет.

## Ветки сравнения

- **A:** уже сохранённый transfer v2, без добавленных тезисов.
- **B:** тот же v2 на копии веток, куда добавлены только прошедшие проверку цитаты. Промпт и верификатор не меняются.
- Новые ответы: `transfer/thesis/v2-b/`. Изменившийся контекст — новый вызов; идентичный пустой список тезисов может попасть в старый кеш v2, это не новый расход.

## Комментарии без установленной связи

Реплика остаётся в обсуждении темы. `other_subject` / `project` / `unclear` ничего не вычёркивают из ответа читателю.

## Контрольные md5 до прогона

| md5 | файл |
|---|---|
| c537d7d3e03edcbcebea51158ab0f6eb | artifacts/reaction-subject/labels.jsonl |
| ea73cf311ffe637ff74729f2c11a50f3 | transfer/labels.jsonl |
| 62a55130e6efdf13277ab277df25f1c5 | transfer/threads.jsonl |
| d9e284330e4c651e1c45f6edc878c6db | transfer/baseline.jsonl |
| b51d098e5d67f1416a3d51cedc99b1ec | transfer/snapshot.json |
| 89326a5efea473e1d14c9e345cfe1e88 | transfer/v2/llm.jsonl |
| 6057e6800684b7e5cee19a77eef37267 | transfer/v2/verify.jsonl |
| 9c0bcbd9c5e0a4dc3de4b4bb7d255aaf | transfer/v2/run.json |

Фактический расход серии до этого шага (usage в run.json): v1 $0.00854 + v2 $0.01175 + transfer v2 $0.01404 = **$0.03433**. Остаток от $1 ≈ **$0.965**. Оценка extract ≈ $0.004.

## Воспроизведение до прогона

```bash
python3 docs/research/reaction_subject_thesis.py label
python3 docs/research/author_thesis_extract.py check
python3 docs/research/author_thesis_extract.py estimate
python3 docs/research/reaction_subject_thesis.py estimate
uv run pytest -q tests/research/test_author_thesis_extract.py tests/research/test_reaction_subject_v2.py
```
