# artifacts/

Frozen evidence, not product code. The live service does not read this folder.

| Path | What it is |
|---|---|
| `agenda-eval/` | Manual quote review of the live agenda: [quality-2026-09-25.md](agenda-eval/quality-2026-09-25.md), [live Docker smoke](agenda-eval/live-smoke.md) |
| `news-eval/`, `news-tune/` | Frozen hold-out and tuning samples from the earlier news-first Pulse probe |
| `news-pulse/`, `pulse-eth/`, `pulse-zec/`, `pulse-critique/` | Research runs of the topic Pulse that preceded the agenda ([history](../docs/product.md#история-направления)) |
| `reaction-subject/`, `comment-review/`, `entity-candidates/` | Comment-attribution and entity-alias experiments |

The LLM replay caches behind these runs (about 10k request/response files) are
kept out of the working tree. Research scripts under `docs/research/` read them
to rerun without spending credits; restore them with:

```sh
git checkout research-cache-2026-09 -- artifacts/news-pulse/cache artifacts/reaction-subject
```
