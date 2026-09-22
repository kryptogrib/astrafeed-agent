from __future__ import annotations

import re

# Entity-extractor v1 (narrative spec, Increment 1). Recall-only signal: it feeds
# the deterministic cross-channel recall in ``events.py``; precision is the LLM
# judge's job, so over-extraction is acceptable and under-extraction (a missed
# merge) is the graceful failure.
#
# Strategy: Latin Capitalized tokens (product/model/company names stand out in an
# otherwise-Cyrillic feed) PLUS a small model/product alias dictionary that maps
# spelling variants to one canonical token. Everything is casefolded and run
# through a light morphology strip, then a denylist of generic AI vocabulary is
# removed so two unrelated posts don't "share" the entity ``model``/``agent``.

# Generic AI terms that are NOT discriminating entities (spec denylist).
_DENYLIST = frozenset({"agent", "model", "ai", "llm", "code"})

# A Latin token: starts with an uppercase Latin letter, may carry internal caps,
# digits, dots or hyphens (GPT-4, ChatGPT, o3, Claude, Stability.ai). Length ≥ 2
# avoids stray single initials.
_LATIN_TOKEN_RE = re.compile(r"[A-Z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)*")

# Alias dictionary: spelling/transliteration variants → canonical entity token.
# Deliberately small; extend as fixtures demand. Keys are casefolded.
_ALIASES: dict[str, str] = {
    "chatgpt": "gpt",
    "gpt-4": "gpt",
    "gpt4": "gpt",
    "gpt-4o": "gpt",
    "gpt-5": "gpt",
    "openai": "openai",
    "оpenai": "openai",  # cyrillic-о homoglyph guard
    "anthropic": "anthropic",
    "клод": "claude",
    "грок": "grok",
    "фейбл": "fable",
    "фэйбл": "fable",
}


def _normalize(token: str) -> str:
    """Casefold + a light morphology strip (drop a trailing possessive ``'s``
    and surrounding punctuation) so ``Fable's`` and ``Fable`` collide."""
    t = token.casefold().strip(".-")
    if t.endswith("'s"):
        t = t[:-2]
    return _ALIASES.get(t, t)


def extract_entities(text: str) -> frozenset[str]:
    """Return the significant-entity set of ``text`` for recall.

    Latin Capitalized tokens + alias-dictionary hits, normalized, minus the
    generic-term denylist. Empty/``None`` text yields the empty set."""
    if not text:
        return frozenset()
    found: set[str] = set()
    for raw in _LATIN_TOKEN_RE.findall(text):
        norm = _normalize(raw)
        if len(norm) >= 2 and norm not in _DENYLIST:
            found.add(norm)
    # Alias hits whose key is non-Latin (e.g. a Cyrillic transliteration) won't be
    # caught by the Latin regex above — scan the casefolded word stream for them.
    lowered = text.casefold()
    for alias, canonical in _ALIASES.items():
        if alias in lowered and canonical not in _DENYLIST:
            found.add(canonical)
    return frozenset(found)
