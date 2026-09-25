# Possible paid AstraFeed service after the free demo

**Status: proposal, not deployed.** The listed [OKX.AI #13877](https://www.okx.ai/agents/13877) A2MCP endpoint remains free and returns HTTP 200 for an empty POST. No customer demand, conversion, or price has been validated.

## Proposed offer

- Buyer: an agent that repeatedly polls the published agenda or retrieves a source-backed story card.
- Unit: one paid read call to a **separate** A2MCP service endpoint. Agenda deltas, search and story detail would each be billable; a price of **$0.001 per call** is only a test hypothesis. At four polls per hour, that would be $0.096 per day before search and card calls.
- The shared background collection and LLM cycle stays separate from individual reads. A paid read would not run an LLM; it would fund collection, hosting and maintenance. The example configuration has a $5/day LLM budget cap; this is neither a deployed-setting claim nor a measured cost or proof of margin.

## Payment flow to validate

1. A client calls the separate paid HTTPS endpoint without payment. It returns HTTP 402 with a standard payment challenge.
2. The client pays using an OKX-supported wallet and repeats the same request with the payment proof.
3. The OKX Payment SDK verifies and settles the payment, then the existing snapshot read returns its result. A failed verification does not expose the result.
4. Test the complete 402 → payment → replay → result sequence before calling the service live, and register it separately with a matching per-call price.

The existing free endpoint stays available because OKX [checks a free A2MCP endpoint for HTTP 200](https://web3.okx.com/onchainos/dev-docs/okxai/howtomcp). The paid service would follow OKX's [seller SDK guide](https://web3.okx.com/onchainos/dev-docs/payments/service-seller-sdk); this document does not claim the payment code is implemented.
