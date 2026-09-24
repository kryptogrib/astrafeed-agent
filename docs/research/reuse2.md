Ниже — не просто список ссылок, а карта референсов для твоего **Telegram-native Narrative Pulse / Community Intelligence Agent**: что посмотреть как продукт, что можно заимствовать как UX и какие open-source-компоненты реально помогут быстро собрать MVP.

Главный вывод: не пытайся повторить Kaito, Santiment или LunarCrush как «всё-в-одном crypto terminal». Твой wedge — **объяснимый анализ динамики комьюнити вокруг конкретного токена/события**: органический интерес vs coordinated promotion, стадия нарратива, качество дискуссии и evidence по ключевым claims. Большие продукты дают social volume и общий sentiment; ты можешь сделать удобный агентный ответ на вопрос: *«почему этот токен обсуждают и можно ли доверять этому вниманию?»*[[spark](https://www.spark.money/tools/crypto-sentiment-tool-comparison)][[vibewatch](https://vibewatch.io/guides/best-crypto-social-listening-tools)]

## 1. Продуктовые референсы

### Kaito — ориентир по narrative intelligence

Kaito — ближайший high-level референс по тому, как упаковывать крипто-информацию в research product: он объединяет social, research и community-источники, чтобы отслеживать нарративы, изменение sentiment и катализаторы. В обзорах его описывают как crypto-social intelligence продукт, который агрегирует данные из X, Discord, Telegram, форумов и длинных research-материалов.[[addressable](https://www.addressable.io/blog/crypt-tools-2026)][[flipster](https://flipster.io/blog/what-is-kaito-the-ai-powered-crypto-intelligence-platform-explained)]

**Что взять:**

- Не показывать пользователю просто ленту постов. Показывать ответ на исследовательский вопрос.
- У каждого токена должен быть “narrative state”: что сейчас обсуждают, что ускоряется, что затухает.
- Делать поиск не только по exact ticker, но по проекту, продукту, команде, экосистеме, конкурентам и связанным темам.
- Отдельно считать *mindshare / share of attention*: не “у XYZ 500 сообщений”, а “доля XYZ в наблюдаемой crypto-дискуссии выросла с 0.4% до 1.8%”.
- Сравнивать с baseline: 300 сообщений сами по себе ничего не говорят; 300 сообщений при норме 20 в час — важный сдвиг.

**Чего не копировать:**

- Огромный универсальный search index как MVP.
- Попытку охватить тысячи источников.
- Сложную tokenomics-модель внимания, которая станет отдельным продуктом.

**Для твоего pitch:**

> Kaito tells you what crypto is talking about. Narrative Pulse tells an agent whether that attention is organic, coordinated, early, crowded, or decaying.

Это не обязательно буквально истинное маркетинговое утверждение по всем фичам Kaito, а удачное позиционирование относительно класса продуктов.

---

### Santiment — ориентир по метрикам и baseline

Santiment объединяет on-chain, social и development-данные; его привычные для трейдеров метрики — social volume, social dominance и sentiment. Внешние обзоры также отмечают, что ценность появляется при сравнении social-сигналов с движением цены, активностью кошельков и другими рыночными метриками, а не в isolated sentiment score.[[aisystemscommerce](https://www.aisystemscommerce.com/post/santiment-review-ai-powered-behavioral-analytics-for-crypto-commerce-operators)][[santiment](https://santiment.net/)]

**Что взять:**

- Временные ряды: `mentions/hour`, `unique authors/hour`, `unique communities/hour`.
- Baseline на 24 часа, 72 часа и 7 дней.
- `Social dominance`: доля дискуссии о токене среди всего отслеживаемого universe.
- Alert не на абсолютное число упоминаний, а на **аномалию против baseline**.
- Простой механизм дивергенций:
  - attention растёт, цена стоит;
  - цена растёт, community interest не подтверждает движение;
  - цена падает, но растут risk-discussion и claims об exploit/unlock;
  - hype растёт, а depth discussion падает.

**Что добавить поверх Santiment:**

- Они хорошо показывают *сколько говорят*.
- Ты должен показать *как говорят и почему этот рост может быть ненадёжным*:
  - копипаст;
  - один origin;
  - один referral URL;
  - синхронные публикации;
  - мало новых реальных участников;
  - слишком низкая глубина дискуссии.

---

### LunarCrush — ориентир по трейдерскому UX

LunarCrush известен social-intelligence метриками, агрегированием социальных сигналов и попыткой связать их с рыночным движением. В обзорах упоминаются Galaxy Score, AltRank и CreatorRank, а также фильтрация социальных данных и отслеживание влиятельных аккаунтов.[[vibewatch](https://vibewatch.io/guides/best-crypto-social-listening-tools)][[thestreet](https://www.thestreet.com/crypto/innovation/navigating-the-crypto-landscape-with-ai-analytics)]

**Что взять:**

- “Карточка токена” как entry point.
- Короткий итог вверху экрана: что изменилось и что делать дальше.
- Score должен быть разложен на факторы, а не быть чёрным ящиком.
- Alerts должны иметь строгие причины, например:
  - `mentions_velocity > 3× baseline`;
  - `independent_communities +5`;
  - `coordination_risk high`;
  - `official claim still unverified`.

**Не брать:**

- Один супер-score, будто он является торговым сигналом.
- Экран с десятками vanity metrics.
- Обещания, что social score сам по себе прогнозирует цену.

---

### Vibewatch — ориентир по community health

Vibewatch — интересный референс именно потому, что работает не как трейдерский social terminal, а как слой понимания собственного комьюнити. Он подключается к Discord/Telegram-серверам и объединяет их с другими площадками, а фокусируется на состоянии сообщества, активности, качестве обсуждения и сегментации участников.[[vibewatch](https://vibewatch.io/guides/best-crypto-social-listening-tools)]

**Что взять:**

- Отличать `broadcast activity` от `conversation activity`.
- Смотреть не только на посты админов, но на replies, вопросы, ответы, retention и recurring contributors.
- Давать “community health” как отдельный уровень результата.
- Строить профили поведения:
  - core contributors;
  - newcomers;
  - lurkers;
  - promoters;
  - skeptics;
  - support-seekers.

**Твоё отличие:**

- Vibewatch полезен для команды конкретного проекта.
- Ты строишь внешний наблюдатель для трейдера / фонда / research agent, который сравнивает десятки сообществ и замечает изменения раньше, чем человек вручную прочитает всё.

---

### Telemetry — ориентир по crypto OSINT

Telemetry стоит изучить как референс по TG-native research, а не по UX. Они делают поиск и аналитическую работу поверх Telegram-данных, включая crypto/Web3 intelligence, anti-fraud и исследование взаимосвязей между каналами. Их позиционирование показывает, что Telegram может быть самостоятельным источником OSINT-сигналов — не просто лентой для sentiment.[[telemetryapp](https://www.telemetryapp.io/blog/post/telegram-crypto-web3-intelligence-osint)]

**Что взять:**

- Граф “канал → ссылка → wallet → домен → токен → claim”.
- Источник первого упоминания (`probable origin`).
- Временная синхронность: каналы написали одновременно или история распространялась естественно.
- Концентрация доменов/ссылок: один landing page, referral URL, X-post, contract address.
- Признаки coordinated promotion:
  - одинаковые CTA;
  - одинаковые фразы;
  - одинаковые изображения;
  - одна ссылка;
  - публикации в узком временном окне;
  - один origin и сеть репостов.

**Не надо для MVP:**

- Расследование всей сети кошельков.
- Полный channel graph всего Telegram.
- Автоматические обвинения в мошенничестве.

В отчёте используй осторожные формулировки:

```
Высокая концентрация сообщений вокруг одной ссылки.
```

а не:

```
Это скоординированный скам.
```

---

### Nodiens — ориентир по decision-ready output

Nodiens — пример продукта, который объединяет market, risk, fundamentals и community signals и подаёт их как готовые к решению выводы, а не как разрозненные дашборды.[[nodiens](https://www.nodiens.com/)]

**Что взять:**

- Один экран / один API-ответ = одно решение.
- Небольшой набор действий: `ignore`, `monitor`, `investigate`, `risk_review`.
- “Why now?” как обязательное поле.
- “What changed versus baseline?” как обязательное поле.
- “What would invalidate this?” как обязательное поле.

Это особенно подходит твоему агентному формату: следующий агент должен получать не стену текста, а готовый контракт данных.

## 2. Что переиспользовать технически

### Сбор Telegram: Telethon + свой ingestion worker

Для public Telegram-каналов наиболее практичный базовый путь — Python-клиент на Telethon, который используется в нескольких открытых scraper-проектах. Например, `marekuzel/Telegram-scraper` работает с публичными Telegram-чатами через Telethon, а `ThBroth/telegram-scraper` заявляет continuous scraping, выгрузку медиа и данных.[[github](https://github.com/marekuzel/Telegram-scraper)][[github](https://github.com/ThBroth/telegram-scraper)]

**Как применять:**

- Не бери эти репозитории в production как готовый сервис: это примеры, а не надёжная инфраструктура.
- Возьми их как reference для login/session, pagination, `message_id`, `channel_id`, timestamp и media metadata.
- Сделай свой idempotent ingestion worker:
  - в базе хранится `channel_id + message_id`;
  - каждая запись идёт через upsert;
  - worker забирает только сообщения после последнего cursor;
  - удалённые/отредактированные сообщения маркируются как `edited` / `deleted`;
  - Telegram session и secrets хранятся отдельно от кода.

Минимальный исходный формат:

```
{
  "platform": "telegram",
  "message_id": "123456",
  "channel_id": "crypto_news_x",
  "author_id": null,
  "published_at": "2026-09-23T11:34:21Z",
  "text": "...",
  "reply_to_message_id": null,
  "forward_from": null,
  "urls": [],
  "views": 0,
  "forwards": 0,
  "reactions": {},
  "raw_payload_version": 1
}
```

**Юридическое и platform-risk замечание:** работай с публичными каналами или чатами, к которым у аккаунта есть законный доступ; учитывай правила Telegram, privacy expectations и не собирай/не раскрывай лишние персональные данные. Не строй продукт на обходе доступа к закрытым сообществам или на скрытом массовом профилировании пользователей.

---

### Discord: бот, а не scraper

Для Discord лучше строить официальный bot-based ingestion. Проекты вроде Cherub показывают базовую модель: бот собирает сообщения с metadata и сохраняет их в SQLite; ServerPulse следит за messages, joins и reactions и превращает их в activity insights.[[github](https://github.com/sizwinz/ServerPulse)][[github](https://github.com/J-umpy/cherub)]

**Почему это лучше:**

- Прозрачное разрешение сервера.
- Можно получить events, reactions, threads и role/context metadata.
- Значительно меньше platform/legal risk.
- Легче продавать проектам как community-monitoring интеграцию.

**Данные, которые реально нужны:**

```
{
  "platform": "discord",
  "server_id": "…",
  "channel_id": "…",
  "message_id": "…",
  "author_id_hash": "…",
  "created_at": "…",
  "text": "…",
  "reply_to_id": "…",
  "thread_id": "…",
  "reactions": {
    "rocket": 4,
    "eyes": 7
  },
  "roles_snapshot": ["member"]
}
```

Не надо собирать личные данные участников, если тебе достаточно анонимизированного `author_id_hash` для подсчёта unique authors и retention.

---

### Multi-platform ingestion: нормализованный event schema

Для X, Reddit, Telegram, Discord и news не создавай отдельный pipeline на выходе. Разные должны быть только коннекторы; дальше все события должны попадать в один canonical event model.

```
{
  "event_id": "uuid",
  "platform": "telegram",
  "source_id": "tg:channel_name",
  "source_type": "channel",
  "source_family": "unknown",
  "author_id_hash": null,
  "occurred_at": "2026-09-23T11:34:21Z",
  "text": "...",
  "language": "ru",
  "urls": [],
  "assets": ["XYZ"],
  "entities": ["XYZ", "Binance"],
  "engagement": {
    "views": 12000,
    "replies": 31,
    "forwards": 17,
    "reactions": 88
  },
  "reply_to_event_id": null,
  "forward_of_event_id": null,
  "is_deleted": false,
  "ingested_at": "2026-09-23T11:34:28Z"
}
```

Для ingestion-оркестрации можно посмотреть Meltano: это code-first open-source data integration engine с SDK для собственных extractors/loaders, совместимых со стандартом Singer. Он может быть полезен, если источников быстро станет много, но для hackathon-MVP скорее избыточен.[[github](https://github.com/meltano)][[github](https://github.com/meltano/meltano)]

**Практичный выбор для тебя:**

- Hackathon: один Python worker на Telethon + очередь + Postgres.
- После validation: отдельные source-adapters и единая schema.
- Когда источников 5–10+: Meltano/Singer или свой lightweight connector framework.

---

### Дедупликация: SimHash до embeddings

Для Telegram очень важны near-duplicates, потому что один claim может разлететься через десятки каналов. Начинать нужно с дешёвого двухступенчатого подхода:

1. Exact hash нормализованного текста.
2. SimHash / near-duplicate detection.
3. Только затем embeddings для semantic clustering.

`simhash-py` и `simhash-cluster` — открытые реализации для поиска near-duplicate текстов через Hamming distance. SimHash создаёт компактный fingerprint; похожие документы имеют близкие fingerprints, поэтому можно дешёво отделить копипаст от реально самостоятельных сообщений.[[github](https://github.com/seomoz/simhash-cluster)][[github](https://github.com/seomoz/simhash-py)]

Пайплайн:

```
Raw message
  → normalize: lower-case, URLs/ticker placeholder, remove emojis/noise
  → exact content hash
  → SimHash fingerprint
  → near-duplicate group
  → embedding
  → semantic story/narrative cluster
```

**Почему сначала не embeddings:**

- Exact copy и почти дословные репосты нужно ловить быстро и дёшево.
- Embeddings могут ошибочно “склеить” похожие, но независимые мнения.
- SimHash даёт тебе объяснимый сигнал: “11 из 17 сообщений похожи на origin message”.

---

### Поиск и similarity: OpenSearch или Postgres + pgvector

OpenSearch — открытый search/analytics стек с full-text и vector search, включая k-NN. Его стоит рассматривать, если появятся сотни тысяч/миллионы сообщений, быстрый text search, filters по источникам/токенам и semantic retrieval в одном месте.[[opensearch](https://opensearch.org/platform/vector-search/)][[docs.opensearch](https://docs.opensearch.org/latest/about/)]

Для hackathon я бы выбрал проще:


| Условие                                               | Выбор                                                   |
| ----------------------------------------------------- | ------------------------------------------------------- |
| До нескольких миллионов сообщений, небольшой MVP      | Postgres + `pgvector` + полнотекстовый поиск PostgreSQL |
| Нужен гибкий поиск, faceting, аналитика и рост объёма | OpenSearch                                              |
| Только быстрый offline semantic clustering            | FAISS                                                   |
| Нужна удобная observability + аналитические дашборды  | OpenSearch + Dashboards                                 |


FAISS — open-source библиотека Meta для efficient similarity search и clustering dense vectors; она подходит, если хранение и поиск векторных представлений хочется оставить отдельно от основной БД.[[instaclustr](https://www.instaclustr.com/education/vector-database/top-10-open-source-vector-databases/)]

## 3. Что брать как UX-референс

Твоему трейдеру или агенту не нужно показывать «sentiment dashboard». Покажи **одну карточку narrative event**.

### Narrative Pulse Card

```
XYZ — Attention spike detected
─────────────────────────────────
Stage: Acceleration
Community quality: Mixed
Coordination risk: High
Evidence status: Unverified claim

Why now
• Mentions: 4.6× above 72h baseline
• 9 communities mentioned XYZ for the first time
• 57% near-duplicate messages
• 43% posts carry the same URL
• Underlying listing claim: spreading, not confirmed

Interpretation
Visibility is rising, but message growth is outpacing independent discussion.
The current pattern is consistent with promotional amplification.

Recommended action
MONITOR — verify primary claim and wait for market confirmation

Machine handoff
{
  "attention_spike": true,
  "organic_attention": "medium",
  "coordination_risk": "high",
  "claim_status": "spreading",
  "trade_eligibility": "manual_review"
}
```

Это объединяет:

- Santiment-подобный baseline;
- Kaito-подобное narrative framing;
- Telemetry-подобные признаки сети и координации;
- Nodiens-подобный actionable output.

## 4. Что не строить

Для хакатона важно жёстко ограничить scope.

Не делай:

- Универсальный “Kaito для Telegram”.
- Поддержку сразу Telegram, X, Discord, Reddit, YouTube и web.
- Автоторговлю на основе social score.
- «Детектор скама» с обвинительными формулировками.
- Обещание предсказывать цену.
- Сложный social graph всех пользователей Telegram.
- Полноценную оценку ботов без качественного ground truth.
- Неразличённый `sentiment = bullish/bearish`.
- Незаметную для пользователя чёрную коробку из LLM scores.

Вместо этого сделай одну сильную цепочку:

```
Telegram public channels + comments
  → сообщения и engagement metadata
  → asset/entity extraction
  → exact + near-duplicate detection
  → clustering в narratives
  → baseline comparison
  → organic-vs-coordinated evidence
  → explanation + research action + JSON handoff
```

## Рекомендованный стек

С учётом того, что ты уже технически сильный и работаешь с Cloudflare/TypeScript, я бы разделил систему так:


| Слой                | Вариант для MVP                             | Причина                                                     |
| ------------------- | ------------------------------------------- | ----------------------------------------------------------- |
| Telegram ingestion  | Python + Telethon                           | Зрелый доступ к сообщениям и streaming/pagination примеры   |
| API и orchestration | Cloudflare Workers + Hono/Fastify-style API | Тебе близкий стек, быстрый публичный API                    |
| Очередь             | Cloudflare Queues или Postgres outbox       | Надёжное асинхронное извлечение и анализ                    |
| Основная БД         | Postgres                                    | Stories, messages, channels, feature snapshots, audit trail |
| Semantic similarity | `pgvector` сначала                          | Один operational surface                                    |
| Near-duplicate      | SimHash                                     | Быстро, объяснимо, дёшево                                   |
| LLM                 | Строгий structured extraction с JSON Schema | LLM не принимает финальное решение                          |
| Analysis            | Python worker или TypeScript worker         | Обогащение, scoring, baseline, story state                  |
| UI                  | Минимальный Next.js / React terminal        | Демо карточки, timeline, evidence drill-down                |
| Agent endpoint      | JSON schema + отдельный endpoint / skill    | Интеграция с [OKX.AI](http://OKX.AI) и другими агентами     |


Для web/X/Reddit-источников позднее можно использовать Crawlee или готовые Actors/инструменты Apify; Crawlee — open-source библиотека для web crawling и browser automation на Node.js/TypeScript, а Apify также предоставляет готовые scrapers и MCP-интеграцию.[[docs.apify](https://docs.apify.com/open-source)][[github](https://github.com/apify)]

## Итоговый shortlist

Если оставить только наиболее полезное:


| Референс / инструмент | Зачем смотреть                | Что брать                                           |
| --------------------- | ----------------------------- | --------------------------------------------------- |
| Kaito                 | Narrative / mindshare продукт | Narrative state, research-first output              |
| Santiment             | Social + on-chain metrics     | Baseline, dominance, divergences                    |
| LunarCrush            | UX для трейдера               | Разложенный score, alerts, token cards              |
| Vibewatch             | Community quality             | Discussion depth, retention, contributor profiles   |
| Telemetry             | TG-native OSINT               | Provenance, link graph, coordination indicators     |
| Nodiens               | Decision-ready terminal       | “Why now?”, “what changed?”, action labels          |
| Telethon              | Telegram ingestion            | Свой надёжный worker, не копировать scraper целиком |
| SimHash               | Дедуп постов                  | Копии отдельно от независимых источников            |
| Postgres + pgvector   | MVP datastore                 | Быстрый старт с metadata и embeddings               |
| OpenSearch            | Scale-up search               | Подключать после появления реальной нагрузки        |


Если выбирать **один продуктовый reference** — изучай Kaito + Telemetry.  
Если выбирать **один технический reference** — Telethon ingestion + SimHash deduplication + Postgres/pgvector.