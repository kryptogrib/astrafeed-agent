Вот структурированный обзор референсов по трём направлениям. Я разделил на **продуктовые ориентиры** (что брать как вдохновение по UX, метрикам, value) и **что можно переиспользовать в движке** (open-source / готовые компоненты).

### 1. Продукты для анализа крипто-комьюнити (продуктовые ориентиры)

| Продукт | Что сильного | Почему полезно тебе |

|---------|--------------|---------------------|

| **LunarCrush** | Galaxy Score, AltRank, social volume + sentiment по тысячам активов, X/Reddit/YouTube/TikTok | Классика social score. Бери идею единого «социального ранга» + корреляции с ценой. |

| **Santiment** | Social + on-chain + developer activity, weighted sentiment, social dominance | Лучший пример, как social-данные стыковать с on-chain. API + историческая глубина. |

| **Kaito** | Mindshare (доля внимания), narrative tracking, KOL-влияние (yapper-weighted) | Самый близкий по смыслу к «narrative intelligence». Дорогой ($800+/мес), но формат отчётов и leaderboards — отличный ориентир. |

| **Dexu** | Mindshare + KOL + narrative по 6 платформам (включая Telegram), MCP-инструменты | Прямо agent-native (MCP). Хороший пример, как упаковать social-intelligence в инструменты для LLM. |

| **Augmento** | 93 категории эмоций (не просто pos/neg), X/Reddit/Bitcointalk | Глубокая гранулярность sentiment. Можно взять taxonomy эмоций. |

| **The TIE** | Institutional NLP на Twitter, низкая latency, bot-detection | Эталон «чистого» sentiment-сигнала для квантов. |

| [**TGScanner.ai**](http://TGScanner.ai) | Мониторинг 1000+ crypto TG-каналов, cross-channel ticker/CA mentions, velocity | Самый близкий конкурент по Telegram. Смотри, как они показывают «когда несколько каналов упоминают одно и то же». |

| **Vibewatch** | Читает Discord + Telegram **изнутри** серверов (бот), community health | Если когда-нибудь захочешь идти в private communities. |

**Что брать как ориентир продукта:**

- Executive summary + key events + narratives + sentiment by asset + actionable insights (как мы обсуждали).

- Mindshare / narrative strength (из Kaito/Dexu).

- Cross-source confirmation (когда одно событие всплывает в нескольких каналах/платформах).

### 2. Обработка обсуждений (NLP, clustering, narrative detection)

**Open-source / готовые пайплайны, которые можно переиспользовать:**

- **Catalyst** (GitHub: overdosesol/Catalyst)  

  Полный open-source AI trend intelligence: сбор → дедупликация → clustering narratives (embeddings + entity matching) → LLM scoring → Telegram-алерты + dashboard.  

  **Сильно подходит** как референс архитектуры твоего пайплайна (особенно cost-aware LLM scoring).

- **CryptoMinute News MCP** (GitHub: zkoranges/cryptominute-news-mcp)  

  MCP-сервер: AI story clustering, Reddit sentiment, Telegram flash posts, significance scoring. Уже в формате, удобном для агентов. Можно смотреть структуру tools и clustering.

- **BigBrother** (GitHub: botta0oss/BigBrother)  

  Анализ Telegram-разговоров: Sentiment + Topic Modeling (BERTopic) + local LLM для лейблов кластеров + Streamlit dashboard.  

  Хороший пример модульного NLP-пайплайна именно для TG.

- **Narrative Monitor** (GitHub: Charubak/narrative-monitor)  

  Сканирует новости, scoring narrative potential через LLM, генерирует ready-to-post drafts.  

  Идея scoring «urgency + angle» полезна.

**Библиотеки/подходы, которые стоит использовать:**

- Embeddings (sentence-transformers) + clustering (BERTopic / HDBSCAN / UMAP).

- Crypto-specific sentiment (или fine-tune на сленге).

- Entity extraction (токены, CA, проекты, люди).

- Deduplication до LLM (чтобы не жечь токены).

### 3. Сбор данных с платформ (особенно Telegram)

**Готовые инструменты и библиотеки:**

| Инструмент | Назначение | Комментарий |

|------------|------------|-------------|

| **Telethon** / **Pyrogram** (Pyrofork) | Основной MTProto-клиент для Python | Стандарт для userbot/scraper. Telethon стабильнее, Pyrogram чуть быстрее из коробки. |

| **Nyan** (GitHub: NyanNyanovich/nyan) | Автоматический агрегатор новостей из TG-каналов + clustering | Отличный русскоязычный референс: scrape → cluster → единый feed. |

| **Telegram RSS Parser** (shmlkv/telegram-rss-parser-web) | Любой TG-канал → RSS / JSON | Удобно для быстрого инжеста в AI. |

| [**TGScanner.ai**](http://TGScanner.ai) (коммерческий) | 1000+ crypto-каналов, CA/ticker tracking | Смотри UX и метрики (velocity, cross-mentions). |

| **telegram\_scan** (bret99) | OSINT + analytics framework на Pyrogram | Глубокий анализ каналов/групп. |

| Разные MCP-коннекторы для Telegram | Чтение публичных каналов без MTProto | Можно использовать как лёгкий fallback. |

**Практические советы по сбору:**

- Для публичных каналов — Telethon + SQLite/FTS5 (как в статьях на Habr про локальные архивы).

- Обязательно: rate-limit handling, flood-wait, session management.

- Сохраняй raw + нормализованный JSON (timestamp, channel, text, reactions, replies, media).

- Для комментариев — отдельный пайплайн (часто нужно читать discussion-группы).

### Краткий вывод — что брать прямо сейчас

**Продуктовый ориентир (смотреть UX и отчёты):**

1. Kaito / Dexu — narrative + mindshare.

2. LunarCrush / Santiment — social scores + API.

3. TGScanner — Telegram-specific alpha.

**Переиспользовать в движке:**

1. **Catalyst** — архитектура narrative detection + LLM scoring.

2. **CryptoMinute MCP** — формат tools + clustering.

3. **Telethon + Nyan / BigBrother** — сбор и базовая обработка TG.

4. Embeddings + BERTopic / HDBSCAN — clustering обсуждений.

5. Structured JSON output в стиле research-агентов на [OKX.AI](http://OKX.AI).

Если нужно — могу глубже разобрать любой из проектов (архитектуру Catalyst, схему выходных данных Dexu/Kaito, или конкретный пайплайн на Telethon + clustering).