# Routing-override precedence: always_alert > model > digest_only

> **Status: Superseded** by the `keyword-alerts-channel-modes` feature. Model-driven
> alerting and the entire routing-override system were removed; keyword rules are now
> the only Alert mechanism and Interests are purely semantic (text + scope).
> This ADR is historical: it uses the old `Digest` / `digest_only` terminology that
> existed before the MVP rename to `Report`.

When the LLM has produced a routing decision for an Item (Alert or Digest — Drop means nothing matched), the per-Interest routing overrides on the matched Interests reconcile with that decision under a fixed precedence:

1. **Drop stays Drop.** If the model found no match, no override applies — overrides only act on Items that matched at least one Interest.
2. **`always_alert` wins over everything.** If any matched Interest is flagged `always_alert`, the Item is Alerted regardless of the model's Alert/Digest call.
3. **`digest_only` forces Digest only when nothing else justifies an Alert.** If a matched Interest is `digest_only` AND no matched Interest is `auto`, the Item is routed to Digest. If an `auto` Interest also matched, the model's decision stands (the Item is relevant for a reason the user did *not* mark digest-only, so the model is allowed to interrupt).
4. **Otherwise the model's decision stands.**

This lives as one pure function — `apply_routing_override(model_route, matched_overrides)` in `domain/routing.py` — fully unit-tested, and is the single place this product judgment is encoded.

## Why this shape

The cascade (ADR-0003) concatenates Global+Group+Channel Interests in `extend` mode, so a single Item can match several Interests carrying *different* overrides. We needed a deterministic tiebreak. The chosen order favors **not missing important things** (`always_alert` is absolute) while respecting that `digest_only` is a *suppression* signal the user attached to a specific narrow Interest — it should not silence an Alert the Item earned through a *different*, unrestricted (`auto`) Interest.

The pipeline aggregates **all** overrides for every matched Interest text before calling this function (a same-text Interest appearing at two cascade levels with different overrides contributes both), so no override is silently dropped — see `Pipeline._route`.

## Considered alternatives

- **Strict overrides win** — any matched `digest_only` forces Digest unless `always_alert`. Rejected as default: it lets a narrow digest-only Interest suppress Alerts the Item legitimately earned elsewhere. (User can still get this behavior by not also tagging broad Interests as `auto`.)
- **Model always wins; overrides are tiebreakers only** — rejected: makes `always_alert`/`digest_only` advisory, defeating their purpose as user controls.

## Consequences

- The precedence is a product decision, not a technical constraint: changing it is a one-function edit with its test suite. Revisit if real usage shows `digest_only` should be stronger.
- `RoutingOverride` is a closed enum (`auto`, `always_alert`, `digest_only`); adding a fourth mode means extending this function and its tests deliberately.
