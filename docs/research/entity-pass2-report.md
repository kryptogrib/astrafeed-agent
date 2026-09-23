# Entity candidates, pass 2: before/after comparison

Date: 2026-09-23. Snapshot: `astrafeed.db`, MD5 `8618099125a806df376354286ccd982e`. The MD5 is the same before and after every run; the database is opened with `?mode=ro`.

Reproduce:

```bash
python3 docs/research/entity_candidates.py astrafeed.db artifacts/entity-candidates docs/research/entity_aliases.tsv
python3 docs/research/entity_eval.py docs/research/entity_gold.tsv before=<v1 dump> after=artifacts/entity-candidates
```

## What changed

| Item | v1 | v2 |
|---|---|---|
| Singleton candidates | removed by `MIN_DOCS` | kept, `rank_eligible=false`; the md has a separate sample of 40, strong signals first |
| Repeated lines | removed as a template | flagged `template_candidate`; counts `mentions` vs `mentions_outside_templates` |
| Contract addresses | removed as noise | candidates with rule `address` (255 detections, 145 unique; 42 in template candidates) |
| Russian forms | none | open registry `entity_aliases.tsv`; whole-word match, no prefix matching |
| «эфир», «тон», «хайпер» | — | never merged: stored as `ambiguous` or `rejected` (reject regex in a ±60-char window) and counted separately |
| Ethereum ↔ ETH | not linked | `related (asset_symbol)` link; the candidates are not merged |
| «CEO Nvidia» | candidates `ceo`, `ceo nvidia` | role word from the registry → the tail is the candidate (`after_role`) |
| Bracket pairs | any «Name (SYM)» | alias only if the first letters match; «Time (UTC)» and «Circle (WSJ)» → `alias_pairs_rejected` |
| Detection records | aggregates only | `detections.jsonl`: document, line, position, exact fragment, candidate, rules, status |
| Short caps lines («💰BTC $76 000») | treated as headlines and skipped | headline check needs ≥12 letters |

## Counts

| | v1 | v2 |
|---|---:|---:|
| Candidates | 2060 (after deletion) | 5019, of which 2024 in the ranking and 2995 singletons |
| Comment–candidate pairs | 248 | 436 |
| Unique comments with ≥1 confirmed mention | 142 | 245 of 1556 non-empty |
| Comments with only an ambiguous mention | — | 12 |
| Ambiguous / rejected detections | — | 42 / 5 (ethereum 35/3, ton 4/2, hyperliquid 3/0) |

The v1 figure of 248 counted comment–candidate pairs. Unique comments are counted separately now.

## Hand-checked sample (`entity_gold.tsv`, 36 rows)

| Check | v1 | v2 |
|---|---|---|
| Mentions (22) | 7 found, 15 missed | 16 found, 5 ambiguous, 1 missed |
| Non-mentions (9) | 4 false positives (`ceo` ×3, `time`) | 0; all 5 «эфир»/«тон» traps are `rejected` |
| Pairs that must not be aliases (3) | 3 proposed | 0 |
| Pairs that should be linked (2) | 1 | 2 |

The 5 ambiguous mentions are correct under the rules. «по эфиру на 2300», «До 3к эфир», «в эфире сети robinhood», «тон по 8$» and «у хайпера» mean assets, but the registry keeps them unconfirmed. The support hint shows why each looks like an asset, for example `support: 2300`.

## Error examples

**Misses**
- `treadfi` in https://t.me/WEB3_AGGREGATOR/423040: a lowercase project name in a post. The posts-first dictionary is used only for comments, and the word appears in only 7 places in the corpus.
- «эфир» with no context signal (10 of 42 ambiguous detections): «у многих в сумках до сих пор лежит эфир» (WEB3_AGGREGATOR/423486), «эфир по 10кило» (rawa_imagination/21055?comment=342484). These are assets, but the ±60-character window has no support word.

**Unresolved ambiguity (kept on purpose)**
- «пошел в эфир и выбил бы Standard Reserve» (WEB3_AGGREGATOR/422826). This could be a broadcast or the asset, so it stays `ambiguous` with `no support`.

**False positives**
- The ≥12-letter headline rule adds noise from marketfeed: `est` («07:00-16:30 EST», 36 docs), `mln`, `bln`, `sells`, `prev`. All of them rank. This is the price of finding BTC, ETH, SOL and TON in +17…18 more posts each. The fix is to add these words to the registry as `not_entity`, or to treat units and time zones as a separate class.
- `sep` («decision to Sep 23»): a month abbreviation read as a Title word.
- `address` also matches inside explorer URLs (Defiscamcheck/4871, `hypurrscan.io/address/0x…`). This is useful for linking to the address, but it is not a mention in the text.
- A donation address in a footer (WEB3_AGGREGATOR/422900 «Поддержать … 0x1D7A…») is correctly marked `template_candidate`.
- `after_role` can return a product name instead of a company: «CEO Hot Wallet» → `hot wallet`. That is acceptable, but it is a singleton.

## What is not solved and does not block the first Pulse

- Russian forms outside the registry, such as «эфирок» or new slang, are not linked. They are not lost either: capitalised words still become candidates.
- Ambiguous mentions are kept in a separate column. Pulse can show them as «± N неоднозначных» and not add them to the total.
- The sample has 36 rows. It catches regressions but does not give reliable precision or recall.
