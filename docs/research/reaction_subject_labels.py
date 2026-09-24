"""Preliminary agent labels for the reaction-subject experiment, written before the LLM prompt.

Key: (thread index in threads.jsonl, comment index). Value: (target, target_id, reason, disputed).
Targets: event | author_thesis | project | other_subject | unclear | skip (empty text, not scored).
author_thesis with target_id None means the author's claim exists in the post but was not extracted.
Regenerate labels.jsonl with: python3 docs/research/reaction_subject.py label
"""

E, T, P, O, U, S = "event", "author_thesis", "project", "other_subject", "unclear", "skip"

LABELS: dict[tuple[int, int], tuple[str, str | None, str, bool]] = {
    # T0 Jumper whitelist + Arc mainnet today
    (0, 0): (E, "e26-e5fbccdf7ac6907c", "поправка даты мейннета Arc («ващета сегодня»); автор благодарит за поправку", True),
    (0, 1): (E, "e26-e5fbccdf7ac6907c", "подтверждает поправку о дате мейннета", True),
    # T1 Aave accepts gold (PAXG) as collateral
    (1, 0): (O, None, "реклама раздачи позиций на Hyperliquid", False),
    (1, 1): (S, None, "пустой текст", False),
    (1, 2): (E, "e1-4bdb4a742211eda9", "оспаривает новизну события: XAUt уже был на v4", False),
    (1, 3): (E, "e1-4bdb4a742211eda9", "«Золото?» — реакция на приём золота в залог", False),
    (1, 4): (E, "e1-4bdb4a742211eda9", "«золото в крипте» — реакция на событие", False),
    (1, 5): (E, "e1-4bdb4a742211eda9", "«золото в крипте» — реакция на событие", False),
    # T2 Circle launches Arc
    (2, 0): (E, "e3-e183a9539dc7838b", "оценка запуска сети эмитентом USDC: «зашквар или новый уровень»", False),
    (2, 1): (S, None, "пустой текст", False),
    (2, 2): (E, "e3-e183a9539dc7838b", "«вот это поворот» под новостью о запуске", True),
    (2, 3): (E, "e3-e183a9539dc7838b", "«ждём новостей» под новостью о запуске", True),
    (2, 4): (E, "e3-e183a9539dc7838b", "«это ж круто, смотрю за развитием» о запуске", False),
    # T3 Arc mainnet tomorrow + referral links
    (3, 0): (O, None, "депозиты на fomo — реферальный сервис из поста, не событие", False),
    (3, 1): (O, None, "общий совет искать новые лаунчи", True),
    # T4 author's LP tool
    (4, 0): (O, None, "дизлайк бесплатной тулзе автора; Arc упомянут в посте мимоходом", False),
    # T5 Arc memecoin circus
    (5, 0): (U, None, "смех без предмета", False),
    # T6 daily digest
    (6, 0): (O, None, "машинный перевод поста", False),
    (6, 1): (O, None, "приветствие", False),
    (6, 2): (O, None, "спорит с тезисом поста «быки сильны» о BTC, не о теме", True),
    (6, 3): (O, None, "ответ про цену BTC 86к", True),
    (6, 4): (S, None, "пустой текст", False),
    (6, 5): (U, None, "ответ на пустую реплику", False),
    # T7 hashcats NFT mint
    (7, 0): (O, None, "цена NFT в ETH, предмет — коллекция", False),
    (7, 1): (O, None, "проблема с минтом NFT", False),
    (7, 2): (O, None, "цена минта NFT", False),
    (7, 3): (O, None, "продажа NFT", False),
    # T8 ZetaChain/Lisk shutdown
    (8, 0): (O, None, "как вывести средства из Lisk; ETH лишь актив свапа", False),
    # T9 JEV AI model
    (9, 0): (O, None, "спор с тезисом автора о применении ИИ-модели; вне темы", False),
    # T10 market phase advice
    (10, 0): (T, None, "уточняет совет автора держать удачные монеты: «hype или zec»", True),
    # T11 Arc early activity farming guide
    (11, 0): (O, None, "шутка про пиво", False),
    (11, 1): (T, None, "спор с установкой автора «несколько транзакций, без фанатизма»", True),
    (11, 2): (T, None, "продолжение спора о числе транзакций", True),
    (11, 3): (O, None, "опыт дропа Monad", True),
    (11, 4): (O, None, "дроп Monad за активность в других экосистемах", False),
    (11, 5): (P, None, "«забей на арк» — оценка проекта в целом", False),
    # T12 moni_talks digest
    (12, 0): (O, None, "реакция на пункт про Unipeg", False),
    (12, 1): (U, None, "«флагманский продукт» без явного предмета", True),
    (12, 2): (O, None, "лаунчпады и ботофермы", True),
    # T13 market + Paper Trade
    (13, 0): (U, None, "одобрение поста без предмета", False),
    # T14 golden cross BTC
    (14, 0): (T, None, "развивает тезис автора о росте после золотого креста, с оговорками по BTC/ETH", True),
    # T15 macro pulse
    (15, 0): (U, None, "ответ без контекста", False),
    (15, 1): (U, None, "ответ без контекста (Япония)", False),
    (15, 2): (U, None, "ответ без контекста", False),
    (15, 3): (U, None, "ответ без контекста", False),
    # T16 NEAR analysis
    (16, 0): (O, None, "согласие с анализом NEAR; ZEC только для сравнения", True),
    # T17 USDT.D
    (17, 0): (O, None, "перепост новостей NEAR", False),
    # T18 Fetch.ai / NuNet exploit
    (18, 0): (E, "e103-bac60b19c932c9f7", "причина эксплойта: украли ключ", False),
    (18, 1): (T, None, "предположение автора о компрометации подтвердилось", True),
    # T19 author market post
    (19, 0): (O, None, "вопрос про золото", False),
    (19, 1): (O, None, "золото и ставка", False),
    (19, 2): (O, None, "золото, индикаторы", False),
    # T20 macro pulse
    (20, 0): (O, None, "ETF msos", False),
    (20, 1): (O, None, "PMI и рынок", False),
    (20, 2): (O, None, "рынок вообще", False),
    (20, 3): (P, None, "покупка эфира на падении — о ETH в целом", True),
    (20, 4): (U, None, "шорты и неизвестные «Глиф и Р2»", False),
    (20, 5): (O, None, "шутка про альтсезон", False),
    # T21 author forecast ETH 3k
    (21, 0): (T, "telegram:8:2469#s0", "встречный прогноз «дальше 1500»", False),
    (21, 1): (T, "telegram:8:2469#s0", "согласие: «до 3к эфир подарочно выглядит»", False),
    (21, 2): (T, "telegram:8:2469#s0", "насмешка над позицией автора по эфиру", True),
    # T22 NFT watchlist
    (22, 0): (O, None, "коллекция Hazels", False),
    (22, 1): (O, None, "коллекция Kageuri", False),
    (22, 2): (O, None, "NFT Doodles на Robinhood", False),
    (22, 3): (O, None, "цена минта Hazels", False),
    (22, 4): (O, None, "благодарность за рубрику, Jpeg Frens", False),
    (22, 5): (O, None, "ответ канала", False),
    # T23 digest
    (23, 0): (O, None, "приветствие бота чата", False),
    (23, 1): (O, None, "бадж ArcHub — пункт дайджеста не по теме ETH", False),
    (23, 2): (O, None, "бадж ArcHub", False),
    (23, 3): (O, None, "аккаунт на хабе", False),
    # T24 Arc ecosystem list
    (24, 0): (O, None, "приветствие бота чата", False),
    (24, 1): (E, "e18-dcf0c45365b311ce", "«готовы ректоваться» перед мейннетом Arc", True),
    (24, 2): (U, None, "ответ без предмета", False),
    (24, 3): (S, None, "пустой текст", False),
    (24, 4): (U, None, "способ зайти в сеть через Ellipse; предмет неясен", True),
    (24, 5): (S, None, "пустой текст", False),
    # T25 digest, Arc mainnet today
    (25, 0): (S, None, "пустой текст", False),
    (25, 1): (O, None, "цепочка про закрытую регистрацию в faucet Starknet", False),
    (25, 2): (O, None, "«значит твой ip в блоке» в другой раскладке, цепочка про faucet", False),
    (25, 3): (O, None, "регистрация в faucet", False),
    (25, 4): (E, "e24-b79a9c89ea4254a0", "вопрос о времени запуска мейннета Arc", False),
    (25, 5): (E, "e24-b79a9c89ea4254a0", "цепочка про запуск Arc: «будешь гемблить?»", True),
    # T26 digest: Arc minted 10B, Ritual tokenomics
    (26, 0): (O, None, "приветствие бота чата", False),
    (26, 1): (U, None, "«не жирно ли работягам» — Ritual или Arc, неясно", True),
    (26, 2): (U, None, "та же цепочка", True),
    (26, 3): (U, None, "та же цепочка", True),
    (26, 4): (U, None, "та же цепочка", True),
    (26, 5): (U, None, "та же цепочка", True),
    # T27 Arc first-day results
    (27, 0): (T, None, "«согласен» с оценкой автора: ожидания были больше", True),
    (27, 1): (E, "e46-71403fc329aa2e81", "итоги минтов AKA и Arclings из итогов первого дня", True),
    (27, 2): (O, None, "претензия к лаунчпаду Minara", True),
    (27, 3): (U, None, "без предмета", False),
    (27, 4): (P, None, "стрим команды Arc: «а разрабы?»", True),
    (27, 5): (U, None, "шутка про внешность", False),
    # T28 digest
    (28, 0): (O, None, "приветствие бота чата", False),
    (28, 1): (S, None, "пустой текст", False),
    (28, 2): (U, None, "«запах денег» без предмета", False),
    (28, 3): (O, None, "Yield Fields", False),
    (28, 4): (O, None, "Yield Fields", False),
    (28, 5): (O, None, "Yield Fields", False),
    # T29 digest, Linera shutdown
    (29, 0): (O, None, "приветствие бота чата", False),
    (29, 1): (O, None, "Linera", False),
    (29, 2): (O, None, "Linera, сразу после предыдущей", True),
    (29, 3): (O, None, "Linera", False),
    (29, 4): (O, None, "Linera", False),
    (29, 5): (O, None, "Linera", False),
    # T30 1inch adds networks
    (30, 0): (O, None, "приветствие бота чата", False),
    (30, 1): (S, None, "пустой текст", False),
    (30, 2): (E, "e57-54d455f671306106", "«1inch реально качает» — похвала обновлениям из поста; или 1inch в целом", True),
    (30, 3): (S, None, "пустой текст", False),
}
