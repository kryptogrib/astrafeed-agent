# AstraFeed — demo video script (2–4 min)

OKX Dev Day 2026, track "Build a Company" (OKX AI). Record the screen with a terminal and a browser. Speak in English. The target length is about 3 minutes.

Before recording:

- `curl https://cutememe.lol/healthz` returns `status: ok` with a fresh snapshot;
- pick a story that has a clean title and quotes from two channels (last run: Binance HYPE listing, `st-e5cf2256e3f917de`);
- open the OKX.AI listing page of AstraFeed.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Title slide with the AstraFeed logo and the line "Live agenda of crypto Telegram for AI agents". | Crypto news breaks in Telegram first, spread over dozens of channels. An agent that wants to know what is happening right now has no clean way to read it. AstraFeed turns those channels into a live, verifiable agenda that any agent can call on OKX.AI. |
| 0:20–0:45 | The OKX.AI listing: AstraFeed, the "AstraFeed Crypto Agenda" A2MCP service, the free price and the endpoint. | AstraFeed is an A2MCP service on OKX.AI. One HTTPS endpoint answers with no setup and no API key. An agent discovers it in the marketplace and calls it. |
| 0:45–1:25 | Terminal: `curl -X POST https://cutememe.lol/a2mcp/astrafeed \| jq '.result.stories[:3] \| map({title, channels})'`. | An empty call returns the current agenda: stories that are new or growing over the last 24 hours compared with the previous 24. Each snapshot has an ID, so follow-up calls read the same data. |
| 1:25–2:05 | `curl ... -d '{"query":"HYPE"}'`, then `-d '{"story_id":"st-…","snapshot_id":"snap-…"}'`. Show the claims and their `t.me` links. | The agent searches for a topic and opens the story. Every claim is an exact quote from a post and links to it. The Binance listing of HYPE appears in two channels. That shows spread, not independent confirmation, and the service says so. |
| 2:05–2:25 | Click a `t.me/...` link in the browser: the original post has the same sentence. | A person or an agent can check any sentence in one click. The service never adds numbers or details that the quotes do not contain. |
| 2:25–2:45 | `curl ... -d '{"format":"md"}'`, showing the Markdown brief. | The same snapshot is also available as a short Markdown brief for a human. |
| 2:45–3:05 | Diagram from the README: collect → LLM extract and assign → atomic snapshot → read-only API. `/healthz` shows the commit and the cycle. | Under the hood, a background cycle collects posts, extracts claims with an LLM, groups them into stories and publishes a snapshot atomically. Requests never call the LLM, so a call is cheap and fast. If a channel was not fully processed, it does not count as zero activity. |
| 3:05–3:25 | README section "Monetization on OKX.AI". | Next step is x402 on X Layer through the OKX Payment SDK. The agenda stays free, and search and story cards become paid calls, so agents pay per question in USDT0. |
| 3:25–3:35 | The GitHub repository and the OKX.AI listing link. | AstraFeed: the crypto Telegram agenda for AI agents, on OKX.AI. |

Don't:

- call it market sentiment or trading advice;
- show a story with a generic title or with broken quotes. Check the snapshot before recording.
