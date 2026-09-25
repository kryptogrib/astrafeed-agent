# AstraFeed — demo video script (2–4 min)

OKX Dev Day 2026, track "Build a Company" (OKX AI). Record the screen with a terminal and a browser. Speak in English. The target length is about 3 minutes.

Before recording:

- `curl https://cutememe.lol/healthz` returns `status: ok` with a fresh snapshot;
- pick a current story with a clean title and linked quotes; pin its `snapshot_id` before recording;
- stay on cards 1–3 (HYPE / Bitget / Polymarket or whatever is clean that day). Skip digest crumbs further down;
- after search, immediately open `story_id` + `snapshot_id`. Do not linger on the Russian hit list;
- open the public [OKX.AI listing #13877](https://www.okx.ai/agents/13877) and show its free service and A2MCP endpoint;
- do not scroll `/healthz` spend totals;
- run the exact commands below and check the returned fields against the recorded narration.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Title slide with the AstraFeed logo and the line "Source-backed crypto agenda for AI agents". | Crypto news moves across Telegram, RSS, Reddit and X. AstraFeed turns these posts into a live, verifiable agenda that an agent can call through OKX.AI. |
| 0:20–0:45 | [okx.ai/agents/13877](https://www.okx.ai/agents/13877), its free service and public A2MCP URL. | AstraFeed is publicly listed on OKX.AI as agent 13877. Its free Crypto Agenda service points to this working HTTPS endpoint. |
| 0:45–1:25 | Terminal: `curl -sS -X POST https://cutememe.lol/a2mcp/astrafeed -H 'content-type: application/json' -d '{}' \| jq '.result \| {snapshot_id, stories: [.stories[:3][] \| {title, current_channels}]}'`. | An empty call returns stories that appeared or gained channels over the last 24 hours. The snapshot ID pins the follow-up calls to the same report. |
| 1:25–2:05 | Search with `{"query":"HYPE"}`, then open a returned `story_id` with the returned `snapshot_id`. Show the count and linked source posts from that snapshot. | The agent searches and opens a story. Quotes link to original posts. The observed channel count shows spread, not independent confirmation; near-verbatim copies are marked separately. Read the actual count on screen rather than a memorized number. |
| 2:05–2:25 | Click a `t.me/...` link in the browser: the original post has the same sentence. | A person or an agent can check any sentence in one click. The service never adds numbers or details that the quotes do not contain. |
| 2:25–2:45 | `curl ... -d '{"format":"md"}'`, showing the Markdown brief. | The same snapshot is also available as a short Markdown brief for a human. |
| 2:45–3:05 | Diagram from the README: collect → LLM extract and assign → atomic snapshot → read-only API. `/healthz` shows the commit and the cycle. | Under the hood, a background cycle collects posts, extracts claims with an LLM, groups them into stories and publishes a snapshot atomically. Requests never call the LLM, so a call is cheap and fast. If a channel was not fully processed, it does not count as zero activity. |
| 3:05–3:25 | README section "The detail that matters: an evidence trail" and a source timeline. | The detail is the provenance trail: which observed channel posted first, how the story spread, and where wording or figures differ. Each signal has a source link and an explicit limit. |
| 3:25–3:35 | GitHub `kryptogrib/astrafeed-agent` and listing 13877. | AstraFeed: a source-backed crypto agenda for AI agents, available through OKX.AI. |

Don't:

- call it market sentiment or trading advice;
- claim x402 or a paid tier is live;
- show a story with a generic title or with broken quotes. Check the snapshot before recording.
