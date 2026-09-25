# Provenance

The earlier AstraFeed Token Brief engine was extracted from private AstraFeed at `7a64219` on 23 Sep 2026. Public commit `aa9a275` is the baseline: existing code with removals and wiring. The agenda work after that commit is the OKX Dev Day build-period contribution. The earlier `report/`, `pipeline/`, and `prefilter/` engine is not the live agenda path.

## Build-period evidence

| Area | Pre-existing baseline | Built 23–25 Sep 2026 |
|---|---|---|
| Source intake | Telegram reader and source `Item` in `src/astrafeed/adapters/source/telegram.py`, plus earlier `pipeline/` and `prefilter/` (`aa9a275`) | RSS and Reddit in `src/astrafeed/adapters/source/rss.py`, `src/astrafeed/application/rss_ingest.py`, and `reddit_ingest.py` (`a396b9ca`, `ccfa74b3`); sampled Xpoz collection in `src/astrafeed/adapters/source/xpoz.py` (`c7fe6a43`) |
| Story model | No `src/astrafeed/domain/agenda.py` at baseline (`aa9a275`) | Quote spans, comparable windows and agenda selection in `src/astrafeed/domain/agenda.py`; extraction and assignment in `src/astrafeed/application/agenda_extract.py` and `agenda_assign.py` (`2412c851`, `c9cf8e64`) |
| Snapshots and polling | Earlier report flow did not publish agenda snapshots (`aa9a275`) | Immutable agenda snapshot and HTTP read path in `src/astrafeed/application/agenda_snapshot.py`, `agenda_query.py`; client-owned `since_snapshot_id` comparison in `agenda_changes.py` (`2412c851`, `37042465`) |
| Evidence and prices | Earlier engine had no agenda evidence signals or OKX price context (`aa9a275`) | Source order, copies, sourcing and price context in `src/astrafeed/application/agenda_signals.py` and `src/astrafeed/adapters/http/okx_market.py` (`7b9d3e6e`, `df90f7af`) |
| OKX.AI access | No A2MCP service at baseline (`aa9a275`) | Free read-only `POST /a2mcp/astrafeed` in `src/astrafeed/adapters/http/a2mcp.py` (`94328301`, `943493ff`) |

Review the source and test changes from the baseline on the merged `main` branch:

```sh
git diff --stat aa9a275..main -- src tests
git log --oneline aa9a275..main -- src tests
```

The build-period table points to representative commits, not an exclusive ownership claim for every line in those modules. Frozen experiments under `docs/research/` and `artifacts/` are evidence and history, not product imports.
