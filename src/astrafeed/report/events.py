from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from astrafeed.report.dedup import MergedItem
from astrafeed.report.entities import extract_entities

_ItemKey = tuple[str, str]  # (channel_ref, external_id)

# --- frozen schemas (frozen before implementation; see spec "Schemas") --------


@dataclass(frozen=True)
class EventGroup:
    """One model-proposed partition inside a component. ``ids`` are component-LOCAL
    indices (strings) into the component's member list; ``framing`` maps each id to
    ``"distinct"`` or ``"redundant"`` (subfact selection, used in slice 03)."""

    ids: tuple[str, ...] = ()
    confidence: float = 0.0
    framing: Mapping[str, str] = field(default_factory=dict)
    subfacts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentJudgment:
    """The judge's verdict for ONE input component: zero or more groups plus the
    ids it explicitly rejected (each falls back to its own bullet)."""

    groups: tuple[EventGroup, ...] = ()
    rejected_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventJudgeResult:
    """Nested-per-component result. ``components[i]`` is positionally aligned with
    input ``components[i]``; a ``len`` mismatch is malformed (all → bullets)."""

    components: tuple[ComponentJudgment, ...] = ()
    validation_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventBlock:
    """A synthetic cross-channel event (Increment 1). ``member_item_ids`` is the
    union of every consumed member's stable keys, so the original ``MergedItem``
    set is reconstructible (reversibility). Render arm lands in slice 03; declared
    with defaults so the fail-closed render dispatch can still construct it."""

    headline_gist: str = ""
    headline_link: str = ""
    subfacts: tuple[tuple[str, str], ...] = ()
    sources: tuple[tuple[str, str], ...] = ()
    importance: int = 1
    interests: tuple[str, ...] = ()
    member_item_ids: tuple[_ItemKey, ...] = ()


# --- recall ------------------------------------------------------------------

# Action/event terms (stems, casefolded). A post "has" a term when the stem
# appears as a substring, which tolerates Russian morphology
# (``закры``→``закрыл``/``закрывается``). Recall-only — never a decision gate.
_ACTION_STEMS = frozenset(
    {
        "отозва",
        "закры",
        "приостанов",
        "экспорт",
        "jailbreak",
        "выпуск",
        "benchmark",
        "shutdown",
        "shut down",
        "shutting",
        "релиз",
        "release",
        "launch",
        "запуск",
        "ban",
        "запрет",
        "hack",
        "взлом",
        "leak",
        "утечк",
        "acqui",
        "покуп",
        "merge",
    }
)

_URL_RE = re.compile(r"https?://([^/\s]+)(?:/\S*)?", re.IGNORECASE)
_FULL_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Jaccard is ONE recall route, never a required gate. Set high: the spec records a
# true same-channel arc at Jaccard 0.039/0.065 and unrelated posts at 0.024, so a
# high cutoff keeps Jaccard from manufacturing spurious cross-channel edges; the
# entity+action and shared-URL routes do the real recall work.
_JACCARD_RECALL = 0.5

# Topic vocabulary does not identify a concrete event in the gist/source route.
# Like the entity denylist, this is a recall heuristic, never a merge decision.
_CONTEXT_GENERIC = frozenset(
    {
        "model",
        "models",
        "image",
        "images",
        "editing",
        "generation",
        "модель",
        "модели",
        "моделей",
        "изображения",
        "изображений",
        "картинки",
        "картинок",
        "редактирование",
        "редактирования",
        "генерация",
        "генерации",
    }
)

# A shared publisher plus a generic announcement verb is insufficient evidence of
# one event: companies routinely announce several unrelated products on the same
# day.  These words may help recall, but cannot be the only corroboration used to
# consume two news items after the model proposes a merge.
_ANNOUNCEMENT_ACTIONS = frozenset({"выпуск", "релиз", "release", "launch", "запуск"})


@dataclass(frozen=True)
class _Features:
    """Per-MergedItem recall features, derived once."""

    key: _ItemKey
    channel_ref: str
    ts_hours: float  # item.timestamp as epoch hours (for window math)
    entities: frozenset[str]
    actions: frozenset[str]
    domains: frozenset[str]
    urls: frozenset[str]
    tokens: frozenset[str]
    cluster_id: str
    gist_tokens: frozenset[str]
    short_ids: frozenset[str]
    event_key: str


def _merged_key(m: MergedItem) -> _ItemKey:
    rep = m.representative_item
    if rep is not None:
        return (rep.channel_ref, rep.external_id)
    if m.member_item_ids:
        return m.member_item_ids[0]
    return ("", m.cluster_id)


def _domains(text: str) -> frozenset[str]:
    return frozenset(d.casefold() for d in _URL_RE.findall(text or ""))


def _urls(text: str) -> frozenset[str]:
    normalized: set[str] = set()
    for raw in _FULL_URL_RE.findall(text or ""):
        parsed = urlsplit(raw.rstrip(".,);]"))
        path = parsed.path.rstrip("/")
        if not path:
            continue
        query = urlencode(
            [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if not key.casefold().startswith("utm_")
            ]
        )
        normalized.add(
            urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, query, ""))
        )
    return frozenset(normalized)


def _actions(text: str) -> frozenset[str]:
    low = (text or "").casefold()
    return frozenset(stem for stem in _ACTION_STEMS if stem in low)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(w.casefold() for w in _WORD_RE.findall(text or "") if len(w) >= 3)


def _features(m: MergedItem) -> _Features | None:
    rep = m.representative_item
    if rep is None:
        return None
    text = rep.text or ""
    ts = rep.timestamp
    return _Features(
        key=_merged_key(m),
        channel_ref=rep.channel_ref,
        ts_hours=ts.timestamp() / 3600.0,
        entities=extract_entities(text),
        actions=_actions(text),
        domains=_domains(text),
        urls=_urls(text),
        tokens=_tokens(text),
        cluster_id=m.cluster_id,
        gist_tokens=_tokens(m.gist),
        short_ids=_short_ids(f"{text} {m.gist}"),
        event_key=m.event_key,
    )


def _short_ids(text: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _WORD_RE.findall(text or "")
        if len(token) <= 2
        and token.casefold() not in {"a", "i", "an", "to", "of", "in", "on"}
        and (any(c.isupper() for c in token) or any(c.isdigit() for c in token))
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _actors_agree(a: _Features, b: _Features) -> bool:
    """Two reports of one event name the same actor. When both sides expose
    entities and none is shared, shared wording alone ("компания … объявила …
    модели") is topic overlap, not corroboration. A side with no entities keeps
    the looser lexical route rather than losing recall outright."""
    if not a.entities or not b.entities:
        return True
    return bool(a.entities & b.entities)


def _is_candidate_edge(a: _Features, b: _Features, *, window_h: float, proximity_h: float) -> bool:
    """Deterministic, conjunctive, cross-channel-only recall. Each route can
    independently propose an edge; high Jaccard is a route, never a gate."""
    if a.channel_ref == b.channel_ref:
        return False
    dt = abs(a.ts_hours - b.ts_hours)
    if dt > window_h:
        return False
    # Route 2: shared cluster_id / shared-URL signature.
    if a.cluster_id and a.cluster_id == b.cluster_id:
        return True
    if a.domains & b.domains:
        return True
    # Route 0: the scorer named the same event. A rewrite may share no wording
    # with its original, and this is the only signal that survives that. Bounded
    # to the proximity window so a recurring story does not collapse into one
    # event; the judge still has to confirm the pair.
    if dt <= proximity_h and a.event_key and a.event_key == b.event_key:
        return True
    # Route 1: shared significant entity AND (shared action OR shared URL), within
    # the tighter entity-proximity window.
    if dt <= proximity_h and (a.entities & b.entities) and (a.actions & b.actions):
        return True
    # Summaries expose the event when source wording/actions differ. Recall only:
    # the judge still separates distinct events, and all existing caps apply.
    if (
        dt <= proximity_h
        and _actors_agree(a, b)
        and len(a.gist_tokens & b.gist_tokens) >= 3
        and _jaccard(a.gist_tokens, b.gist_tokens) >= 0.2
    ):
        return True
    # A summary can name the event omitted from a short reaction's original.
    # Require a shared source entity and two substantial context terms. This
    # merely exposes the pair to the judge; it never consumes either source.
    if dt <= proximity_h and a.entities & b.entities:
        for gist, source in ((a.gist_tokens, b.tokens), (b.gist_tokens, a.tokens)):
            terms = {
                t
                for t in gist & source
                if len(t) >= 6 and t not in a.entities | b.entities | _CONTEXT_GENERIC
            }
            if len(terms) >= 2:
                return True
    # Route 3: high Jaccard.
    return _jaccard(a.tokens, b.tokens) >= _JACCARD_RECALL


# --- union-find clustering ---------------------------------------------------


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def assemble_components(
    items: Sequence[MergedItem],
    *,
    window_h: float = 48.0,
    proximity_h: float = 24.0,
    max_pairs: int = 200,
    max_component_size: int = 12,
    max_components: int = 20,
) -> list[list[MergedItem]]:
    """Deterministic recall → union-find components, bounded by the cost caps.

    Returns the multi-member components (≥2 items) to hand the judge, in stable
    first-appearance order. Single-item components and over-cap remainders stay
    bullets (never judged). Empty input is handled (no ``min()`` on empty)."""
    if not items:
        return []
    feats: list[_Features | None] = [_features(m) for m in items]
    uf = _UnionFind(len(items))
    pairs = 0
    # Pairwise scan, bounded by max_pairs candidate EDGES added (cost cap so a
    # dense component can't blow up the work or the judge bill).
    for i in range(len(items)):
        fi = feats[i]
        if fi is None:
            continue
        for j in range(i + 1, len(items)):
            fj = feats[j]
            if fj is None:
                continue
            if _is_candidate_edge(fi, fj, window_h=window_h, proximity_h=proximity_h):
                uf.union(i, j)
                pairs += 1
                if pairs >= max_pairs:
                    break
        if pairs >= max_pairs:
            break

    # Group members by root, preserving first-appearance order of components and
    # of members within a component.
    comps: dict[int, list[int]] = {}
    order: list[int] = []
    for idx in range(len(items)):
        if feats[idx] is None:
            continue
        root = uf.find(idx)
        if root not in comps:
            comps[root] = []
            order.append(root)
        comps[root].append(idx)

    out: list[list[MergedItem]] = []
    for root in order:
        members = comps[root]
        if len(members) < 2:
            continue
        # Component-size cap: keep the first N members (stable), drop the tail back
        # to bullets — a single dense component never overruns the judge.
        members = members[:max_component_size]
        out.append([items[k] for k in members])
        if len(out) >= max_components:
            break
    return out


# --- merge -------------------------------------------------------------------


def merge_events(
    components: Sequence[Sequence[MergedItem]],
    result: EventJudgeResult,
    *,
    min_confidence: float = 0.6,
) -> tuple[list[EventBlock], list[MergedItem]]:
    """Validate the judge result against the input components and build EventBlock
    candidates. Returns ``(blocks, consumed)`` where ``consumed`` is the list of
    ``MergedItem``s folded into some block (the caller stamps
    ``consumed_member_item_ids`` on them and retains the originals for
    reversibility).

    Degradation contract (spec): a ``len`` mismatch ⇒ ALL to bullets; within a
    component a duplicated id (across groups or group∩rejected) ⇒ THAT component to
    bullets (siblings unaffected); a missing id ⇒ that id stays a bullet; a group
    below ``min_confidence`` or with <2 valid members ⇒ bullets."""
    if not components:
        return [], []
    # Length mismatch — the judge lost positional alignment: all to bullets.
    if len(result.components) != len(components):
        return [], []

    blocks: list[EventBlock] = []
    consumed: list[MergedItem] = []
    for comp, judgment in zip(components, result.components, strict=True):
        n = len(comp)
        valid_ids = {str(i) for i in range(n)}

        # Per-component coverage accounting. A duplicate id (seen twice across any
        # group or in both a group and rejected) degrades THIS component.
        seen: set[str] = set()
        duplicate = False
        for group in judgment.groups:
            for gid in group.ids:
                if gid in seen:
                    duplicate = True
                seen.add(gid)
        for rid in judgment.rejected_ids:
            if rid in seen:
                duplicate = True
            seen.add(rid)
        # An id outside the component's local namespace is malformed too.
        if any(s not in valid_ids for s in seen):
            duplicate = True
        if duplicate:
            continue  # whole component → bullets

        for group in judgment.groups:
            if group.confidence < min_confidence:
                continue
            # Keep only in-range ids (a missing id simply never appears here →
            # stays a bullet). A real event needs ≥2 distinct members. ``valid_gids``
            # are the original component-local id strings (possibly non-sequential,
            # e.g. ("0","2")); framing must be looked up by those ids, NOT by member
            # position — otherwise a non-ascending group misattributes framing.
            valid_gids = [g for g in dict.fromkeys(group.ids) if g in valid_ids]
            members = [comp[int(g)] for g in valid_gids]
            if len(members) < 2:
                continue
            if not _is_coherent_event_group(members):
                continue
            blocks.append(_build_block(members, valid_gids, group.framing, group.subfacts))
            consumed.extend(members)
    return blocks, consumed


def _is_coherent_event_group(members: Sequence[MergedItem]) -> bool:
    """Require deterministic corroboration beyond a model's confidence score.

    Members may form a chain (A corroborates B, B corroborates C), so validation
    checks graph connectivity rather than requiring every pair to repeat the same
    wording.
    """
    features = [_features(member) for member in members]
    if any(feature is None for feature in features):
        return False
    concrete = [feature for feature in features if feature is not None]
    connected = {0}
    while True:
        expanded = set(connected)
        for i in connected:
            for j in range(len(concrete)):
                if j not in connected and _has_merge_corroboration(concrete[i], concrete[j]):
                    expanded.add(j)
        if expanded == connected:
            return len(connected) == len(concrete)
        connected = expanded


def _has_merge_corroboration(a: _Features, b: _Features) -> bool:
    if (a.cluster_id and a.cluster_id == b.cluster_id) or a.urls & b.urls:
        return True
    shared_entities = a.entities & b.entities
    if len(shared_entities) >= 2:
        return True
    if a.gist_tokens and a.gist_tokens == b.gist_tokens:
        return True
    shared_actions = a.actions & b.actions
    if shared_actions - _ANNOUNCEMENT_ACTIONS:
        return bool(shared_entities)
    # Short uppercase/digit product identifiers (X, R1, 4o) are intentionally
    # absent from the general recall token set, but can safely corroborate a group
    # that the model has already proposed.
    short_a = _short_identifiers(a)
    short_b = _short_identifiers(b)
    return bool(short_a & short_b)


def _short_identifiers(feature: _Features) -> frozenset[str]:
    return feature.short_ids


def _build_block(
    members: Sequence[MergedItem],
    member_ids: Sequence[str],
    framing: Mapping[str, str],
    details: Mapping[str, tuple[str, ...]],
) -> EventBlock:
    top = max(members, key=lambda m: m.importance)
    interests: list[str] = []
    sources: list[tuple[str, str]] = []
    member_keys: list[_ItemKey] = []
    for m in members:
        for t in m.interests:
            if t not in interests:
                interests.append(t)
        for s in m.sources:
            if s not in sources:
                sources.append(s)
        for k in m.member_item_ids or (_merged_key(m),):
            if k not in member_keys:
                member_keys.append(k)
    # Subfacts: distinct-framed member gists kept verbatim (code-selected). The
    # headline member (``top``) is EXCLUDED here — it is already rendered verbatim as
    # the headline, so emitting it as a subfact would both duplicate it and eat a
    # slot from ``event_subfacts_max``. With the headline removed at build time, the
    # render cap ``subfacts[:event_subfacts_max]`` means exactly "N rendered subfact
    # lines". ``framing`` keys are the original component-local ids (``member_ids``),
    # looked up per member — never by member position.
    subfacts: list[tuple[str, str]] = []
    seen_facts = {" ".join(top.gist.split())}
    for gid, m in zip(member_ids, members, strict=True):
        source = m.representative_item.text if m.representative_item else ""
        normalized_source = " ".join(source.split())
        for quote in details.get(gid, ()):
            fact = " ".join(quote.split())
            if fact and fact in normalized_source and fact not in seen_facts:
                subfacts.append((fact, m.anchor_link))
                seen_facts.add(fact)
        if m is top:
            continue
        if (
            framing.get(gid, "distinct") == "distinct"
            and m.gist
            and " ".join(m.gist.split()) not in seen_facts
        ):
            subfacts.append((m.gist, m.anchor_link))
    return EventBlock(
        headline_gist=top.gist,
        headline_link=top.anchor_link,
        subfacts=tuple(subfacts),
        sources=tuple(sources),
        importance=top.importance,
        interests=tuple(interests),
        member_item_ids=tuple(member_keys),
    )
