"""News-first Pulse: build(topic, window) → JSON, Markdown generated from JSON.

python3 docs/research/news_pulse_build.py astrafeed.db zec 2026-09-17..2026-09-19
PULSE_REUSE=1 skips the network and uses artifacts/news-pulse/cache/ only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from news_pulse_classify import EVENT_STEM, FLOW_HEADER, Observation, classify_segments, find_mentions
from news_pulse_events import EventGroup, from_observation, group_events, group_to_dict
from news_pulse_link import link_comment
from news_pulse_llm import DEFAULT_MODEL, LLMClient
from news_pulse_load import (
    Snapshot,
    Window,
    db_md5,
    load_aliases,
    load_snapshot,
    parse_aliases_env,
    parse_window,
    previous_window,
    resolve_topic,
    window_dir_name,
)

NO_REACTION = "в собранных обсуждениях реакция не найдена"
ALIAS_PATH = Path("docs/research/entity_aliases.tsv")
OUT_ROOT = Path("artifacts/news-pulse")


def build_from_parts(
    *,
    topic: str,
    window: str,
    events: list[dict],
    positions: list[dict],
    discussion: list[dict],
    changes: dict,
    coverage: dict,
    limitations: list[str],
    evidence: list[dict],
    status: str | None = None,
    spend_usd: float = 0.0,
) -> dict[str, Any]:
    rows = list(discussion)
    if events and not rows:
        rows = [
            {
                "target": "none",
                "text": NO_REACTION,
                "basis": "к событиям окна нет связанных комментариев",
                "url": None,
                "quote": None,
            }
        ]
    short: list[str] = []
    # the most widely spread events first: channels, then publications; ties keep time order
    ranked = sorted(
        events,
        key=lambda ev: (-(ev.get("counts") or {}).get("channels", 0), -(ev.get("counts") or {}).get("publications", 0)),
    )
    for ev in ranked:
        if ev.get("headline"):
            short.append(str(ev["headline"]))
        if len(short) >= 5:
            break
    if not events:
        for row in rows:
            text = row.get("text") or ""
            if text and text != NO_REACTION:
                short.append(text)
            if len(short) >= 5:
                break
    if not status:
        if events or any((r.get("text") or "") != NO_REACTION for r in rows):
            status = "ok"
        else:
            status = "no_data"
    payload = {
        "topic": topic,
        "window": {"requested": window},
        "status": status,
        "events": events,
        "distribution_and_positions": positions,
        "discussion": rows,
        "changes": changes,
        "short_observations": short[:5],
        "coverage": coverage,
        "limitations": limitations,
        "evidence": evidence,
        "spend_usd": spend_usd,
        "numbers_by": "code",
    }
    payload["brief_markdown"] = render_markdown(payload)
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    topic = payload.get("topic") or ""
    window = (payload.get("window") or {}).get("requested") or ""
    lines = [f"# Pulse (news-first): {topic}, окно {window.replace('..', ' – ')}", ""]
    lines += ["## Коротко", ""]
    obs = payload.get("short_observations") or []
    if obs:
        lines += [f"- {x}" for x in obs]
    else:
        lines.append("- Содержательных наблюдений в окне нет.")
    lines += ["", "## События и заявления", ""]
    events = payload.get("events") or []
    if not events:
        lines.append("Новостных событий в собранном окне не найдено.")
    for ev in events:
        c = ev.get("counts") or {}
        lines.append(f"- **{ev.get('headline') or ev.get('event_id')}**")
        lines.append(
            f"  публикации {c.get('publications', 0)}, каналы {c.get('channels', 0)}, "
            f"известные авторы {c.get('known_authors', 0)}, первоисточники {c.get('found_origins', 0)}, "
            f"перепечатки {c.get('reprints', 0)}, неизвестное происхождение {c.get('unknown_origin', 0)}."
        )
        for m in (ev.get("members") or [])[:3]:
            if m.get("url"):
                lines.append(f"  - {m.get('url')}: «{(m.get('quote') or '')[:160]}»")
    lines += ["", "## Кто распространяет информацию и какие позиции", ""]
    positions = payload.get("distribution_and_positions") or []
    if not positions:
        lines.append("Отдельных авторских позиций сверх событий не выделено.")
    for p in positions:
        lines.append(f"- {p.get('text') or p.get('quote') or p.get('kind')}")
        if p.get("url"):
            lines.append(f"  {p['url']}")
    lines += ["", "## Вопросы, аргументы и опыт участников", ""]
    discussion = payload.get("discussion") or []
    if not discussion:
        lines.append("Обсуждений в окне нет.")
    for row in discussion:
        lines.append(f"- {row.get('text')}")
        if row.get("basis"):
            lines.append(f"  основание: {row['basis']}")
        if row.get("url"):
            lines.append(f"  {row['url']}")
    lines += ["", "## Изменения относительно предыдущего периода", ""]
    ch = payload.get("changes") or {}
    appeared = ch.get("events_appeared") or []
    gone = ch.get("events_gone") or []
    cov = ch.get("source_coverage") or {}
    lines.append(f"- Появившиеся события: {len(appeared)}.")
    lines.append(f"- Исчезнувшие события: {len(gone)}.")
    lines.append(
        f"- Изменение охвата источников: +{len(cov.get('added_channels') or [])} "
        f"/ −{len(cov.get('removed_channels') or [])} каналов."
    )
    if ch.get("topic_comments") is not None:
        lines.append(
            f"- Комментарии по теме: {ch['topic_comments']} в текущем окне, "
            f"{ch.get('previous_topic_comments', 0)} в предыдущем."
        )
    lines += ["", "## Охват и ограничения", ""]
    coverage = payload.get("coverage") or {}
    lines.append(
        f"- Публикации {coverage.get('publications', 0)}, комментарии {coverage.get('comments', 0)}, "
        f"каналы {coverage.get('channels', 0)}."
    )
    for lim in payload.get("limitations") or []:
        lines.append(f"- {lim}")
    lines += ["", "## Основания", ""]
    evidence = payload.get("evidence") or []
    if not evidence:
        lines.append("- Отдельных evidence-записей нет.")
    for ev in evidence[:20]:
        lines.append(f"- {ev.get('url') or ev.get('id')}: «{(ev.get('quote') or '')[:160]}»")
    lines.append("")
    return "\n".join(lines)


def observations_for_events(obs: list[Observation]) -> list:
    """Events plus retellings that still name a concrete action (inflow, listing, vote)."""
    out = []
    for o in obs:
        if o.status != "ok" or o.topic_role == "context":
            continue
        if o.kind == "event":
            out.append(from_observation(o))
        elif o.kind == "redistribution" and (
            EVENT_STEM.search(f"{o.quote or ''} {o.text or ''}") or FLOW_HEADER.search(o.context or "")
        ):
            row = from_observation(o)
            row.kind = "event"
            out.append(row)
    return out


def _positions(obs: list[Observation]) -> list[dict]:
    out = []
    for o in obs:
        if o.kind != "author_position" or o.status not in {"ok", "held"}:
            continue
        if o.segment_role in {"quote_line", "footer", "promo"}:
            continue
        out.append(
            {
                "obs_id": o.obs_id,
                "publication_id": o.publication_id,
                "kind": o.kind,
                "text": o.quote,
                "quote": o.quote,
                "url": o.url,
                "origin": o.origin,
                "source_role": o.source_role,
            }
        )
    return out


def _evidence(obs: list[Observation], events: list[dict], discussion: list[dict]) -> list[dict]:
    rows = []
    for ev in events:
        for m in ev.get("members") or []:
            rows.append(
                {
                    "id": m.get("obs_id"),
                    "url": m.get("url"),
                    "quote": m.get("quote"),
                    "span": m.get("span"),
                    "publication_id": m.get("publication_id"),
                }
            )
    for o in obs:
        if o.kind in {"event", "author_position"} and o.status == "ok":
            rows.append(
                {
                    "id": o.obs_id,
                    "url": o.url,
                    "quote": o.quote,
                    "span": list(o.span),
                    "publication_id": o.publication_id,
                }
            )
    for d in discussion:
        if d.get("quote") and d.get("url"):
            rows.append({"id": d.get("url"), "url": d.get("url"), "quote": d.get("quote")})
    seen: set[tuple[str, str]] = set()
    uniq = []
    for r in rows:
        key = (str(r.get("url") or ""), str(r.get("quote") or ""))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _limitations(snap: Snapshot, client: LLMClient | None, not_processed: int) -> list[str]:
    rows = [
        "Режим publication_replay: discovered_at в снимке отсутствует, «впервые системой» не заявляется.",
        "Роль источника unknown: в базе нет редакционного реестра.",
        "Неизвестные авторы не объединяются.",
        f"Отсечено после cutoff {snap.cutoff.isoformat()}: {snap.dropped_after_cutoff}.",
    ]
    if not_processed:
        rows.append(f"Сегментов без модельной классификации: {not_processed} (held/not_processed).")
    if client and client.budget.stopped:
        rows.append(f"Остановлено по бюджету NEWS_PULSE_MAX_USD ({client.budget.max_usd}).")
    return rows


def _event_signature(ev: dict) -> str:
    return "|".join(
        str(x or "")
        for x in (ev.get("actor"), ev.get("action"), ev.get("object"), ev.get("headline"))
    )


def _changes(
    snap: Snapshot,
    prev_snap: Snapshot,
    *,
    events: list[dict],
    prev_events: list[dict],
    discussion: list[dict],
    prev_discussion: list[dict],
) -> dict[str, Any]:
    """Topic dynamics only; the snapshot-wide comment volume belongs to coverage, not here.
    Channels are keyed by source_id so the evaluator can recompute them from the DB."""
    cur_keys = {_event_signature(e) for e in events}
    prev_keys = {_event_signature(e) for e in prev_events}
    cur_ch = {str(p.source_id) for p in snap.publications}
    prev_ch = {str(p.source_id) for p in prev_snap.publications}
    return {
        "previous_window": prev_snap.window.requested,
        "previous_events": sorted(prev_keys),
        "events_appeared": sorted(cur_keys - prev_keys),
        "events_gone": sorted(prev_keys - cur_keys),
        "topic_comments": sum(1 for row in discussion if row.get("url")),
        "previous_topic_comments": sum(1 for row in prev_discussion if row.get("url")),
        "source_coverage": {
            "added_channels": sorted(cur_ch - prev_ch),
            "removed_channels": sorted(prev_ch - cur_ch),
            "current_channels": len(cur_ch),
            "previous_channels": len(prev_ch),
        },
    }


def _iso(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _comment_link_target(link: dict) -> str:
    target = link.get("target")
    if target == "event":
        eid = link.get("target_id")
        return f"event:{eid}" if eid else "unlinked"
    if target in {"author_thesis", "project", "other_subject", "topic_level", "unlinked"}:
        return str(target)
    return "unlinked"


def _publication_status(rows: list[Observation]) -> str:
    statuses = {o.status for o in rows}
    if "not_processed" in statuses:
        return "not_processed"
    if "held" in statuses:
        return "held"
    return "processed"


def _publication_origin_role(rows: list[Observation]) -> tuple[str, str]:
    preferred = [o for o in rows if o.kind in {"event", "author_position"}]
    pick = preferred[0] if preferred else (rows[0] if rows else None)
    if pick is None:
        return "unknown", "unknown"
    origin = pick.origin if pick.origin in {"own", "retelling", "repost", "unknown"} else "unknown"
    role = pick.source_role if pick.source_role in {"official", "editorial", "author", "participant", "unknown"} else "unknown"
    return origin, role


def assemble_decisions(
    *,
    topic: str,
    window: Window,
    publications: list,
    comments: list,
    topic_spec,
    observations: list[Observation],
    events: list[dict],
    comment_links: dict[str, dict],
) -> dict[str, Any]:
    """Machine decisions for every topic-mention post and every comment in the window."""
    obs_by_pub: dict[str, list[Observation]] = {}
    for o in observations:
        obs_by_pub.setdefault(o.publication_id, []).append(o)
    selected: set[str] = set()
    event_ids_by_pub: dict[str, list[str]] = {}
    for ev in events:
        eid = str(ev.get("event_id") or "")
        for m in ev.get("members") or []:
            pid = m.get("publication_id")
            if not pid:
                continue
            selected.add(pid)
            if eid and eid not in event_ids_by_pub.setdefault(pid, []):
                event_ids_by_pub[pid].append(eid)

    pub_rows = []
    for pub in publications:
        if getattr(pub, "kind", "post") == "comment":
            continue
        if not find_mentions(pub.text, topic_spec):
            continue
        rows = obs_by_pub.get(pub.pub_id, [])
        origin, role = _publication_origin_role(rows)
        segments = []
        for o in rows:
            if o.kind not in {"event", "author_position", "redistribution", "participant_reaction", "promo_service"}:
                continue
            start, end = (o.span[0], o.span[1]) if o.span else (0, 0)
            segments.append({"class": o.kind, "start": int(start), "end": int(end), "quote": o.quote})
        pub_rows.append(
            {
                "source_id": pub.source_id,
                "external_id": str(pub.message_external_id),
                "link": pub.url,
                "published_at": _iso(pub.published_at),
                "author_id": pub.author_id,
                "topic_mention": True,
                "selected_news": pub.pub_id in selected,
                "segments": segments,
                "event_ids": event_ids_by_pub.get(pub.pub_id, []),
                "origin": origin,
                "source_role": role,
                "status": _publication_status(rows),
            }
        )

    comment_rows = []
    for c in comments:
        link = comment_links.get(c.pub_id) or {}
        comment_rows.append(
            {
                "comment_key": c.metadata.get("comment_key") or f"{c.source_id}:{c.message_external_id}",
                "link": c.url or link.get("url") or "",
                "published_at": _iso(c.published_at),
                "link_target": _comment_link_target(link),
                "basis": link.get("basis") or "связь не устанавливалась",
            }
        )

    by_link = {p["link"]: p for p in pub_rows if p.get("link")}
    event_rows = []
    for ev in events:
        members = ev.get("members") or []
        uniq: dict[str, dict] = {}
        for m in members:
            pid = m.get("publication_id")
            url = m.get("url")
            rec = by_link.get(url) or {}
            key = pid or url
            if not key or key in uniq:
                continue
            uniq[key] = {
                "url": url,
                "origin": rec.get("origin") or m.get("origin") or "unknown",
                "author_id": rec.get("author_id") if rec else m.get("author_id"),
                "source_id": rec.get("source_id") if rec else m.get("source_id"),
            }
        rows = list(uniq.values())
        pub_links = list(dict.fromkeys(r["url"] for r in rows if r.get("url")))
        origin_links = [r["url"] for r in rows if r.get("origin") == "own" and r.get("url")]
        counts = {
            "events": 1,
            "publications": len(rows),
            "channels": len({r.get("source_id") for r in rows}),
            "known_authors": len({r.get("author_id") for r in rows if r.get("author_id")}),
            "unknown_authors": sum(1 for r in rows if not r.get("author_id")),
            "found_origins": sum(1 for r in rows if r.get("origin") == "own"),
            "reprints": sum(1 for r in rows if r.get("origin") in {"retelling", "repost"}),
            "unknown_origin": sum(1 for r in rows if r.get("origin") == "unknown"),
        }
        ev["counts"] = counts
        event_rows.append(
            {
                "event_id": ev.get("event_id"),
                "publications": pub_links,
                "n_publications": counts["publications"],
                "n_channels": counts["channels"],
                "n_known_authors": counts["known_authors"],
                "found_origins": origin_links,
                "n_reprints": counts["reprints"],
                "n_unknown_origin": counts["unknown_origin"],
            }
        )
    return {
        "topic": topic,
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat(), "interval": "[start,end)"},
        "publications": pub_rows,
        "comments": comment_rows,
        "events": event_rows,
    }


def _process_window(
    snap: Snapshot,
    topic_spec,
    client: LLMClient | None,
) -> tuple[list[Observation], list[EventGroup], list[dict], list[dict], dict[str, dict]]:
    pubs = list(snap.publications)
    comments = list(snap.comments)
    llm = None
    if client is not None:
        def llm(items: list[dict]) -> list[dict]:
            return client.classify_batch(items)

    obs = classify_segments(pubs + comments, topic_spec, llm=llm)
    event_obs = observations_for_events(obs)

    def _judge_payload(obs) -> dict:
        published = obs.published_at.isoformat() if hasattr(obs.published_at, "isoformat") else str(obs.published_at)
        return {
            "quote": obs.quote,
            "actor": obs.actor,
            "action": obs.action,
            "object": obs.object,
            "qualifiers": obs.qualifiers,
            "url": obs.url,
            "time": published,
        }

    def judge_many(pairs):
        if client is None:
            return ["unclear"] * len(pairs)
        return client.judge_many([(_judge_payload(a), _judge_payload(b)) for a, b in pairs])

    groups = group_events(event_obs, judge_many=judge_many if client is not None else None)
    event_dicts = [group_to_dict(g) for g in groups]
    theses = [
        {"obs_id": o.obs_id, "quote": o.quote, "text": o.quote, "url": o.url}
        for o in obs
        if o.kind == "author_position" and o.status == "ok"
    ]
    discussion = []
    comment_links: dict[str, dict] = {}
    obs_by_pub: dict[str, list[dict]] = {}
    for o in obs:
        obs_by_pub.setdefault(o.publication_id, []).append(
            {
                "publication_id": o.publication_id,
                "kind": o.kind,
                "quote": o.quote,
                "object": o.object,
                "segment_role": o.segment_role,
            }
        )
    # a comment belongs to the topic only if it names the topic or sits under a post that does
    topic_threads = {p.pub_id for p in pubs if find_mentions(p.text, topic_spec)}
    for c in comments:
        post_obs = obs_by_pub.get(c.thread_id or "", []) + obs_by_pub.get(c.parent_id or "", [])
        link = link_comment(
            c,
            event_dicts,
            theses=theses,
            post_observations=post_obs,
            thread_comments=comments,
        )
        comment_links[c.pub_id] = link
        named = any(t.casefold() in (c.text or "").casefold() for t in topic_spec.confirmed)
        in_topic_thread = (c.thread_id or "") in topic_threads
        # a doubtful link inside a topic thread stays as topic_level discussion (spec §4), not dropped
        if named or in_topic_thread:
            discussion.append(link)
    return obs, groups, event_dicts, discussion, comment_links


def build(
    db_path: str | Path,
    topic: str,
    window: str,
    *,
    reuse: bool | None = None,
    write: bool = False,
    aliases_path: str | Path | None = None,
    extra_aliases: dict | None = None,
    model: str | None = None,
    max_usd: float | None = None,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    win = parse_window(window)
    extra = dict(extra_aliases or {})
    env_aliases = parse_aliases_env(os.environ.get("ALIASES"))
    if "" in env_aliases:
        extra.setdefault(topic, [])
        extra[topic] = list(dict.fromkeys([*extra[topic], *env_aliases.pop(""), topic]))
    for key, names in env_aliases.items():
        extra.setdefault(key, [])
        extra[key] = list(dict.fromkeys([*extra[key], *names]))
    aliases = load_aliases(aliases_path or ALIAS_PATH, extra=extra or None)
    topic_spec = resolve_topic(topic, aliases)
    snap = load_snapshot(db_path, win)
    reuse_flag = bool(os.environ.get("PULSE_REUSE")) if reuse is None else bool(reuse)
    client = LLMClient(
        model=model or os.environ.get("NEWS_PULSE_MODEL") or DEFAULT_MODEL,
        max_usd=max_usd,
        reuse=reuse_flag,
        cache_root=cache_root or Path("artifacts/news-pulse/cache"),
        cutoff=snap.cutoff.isoformat(),
        db_md5=snap.db_md5,
        topic=topic_spec.topic,
    )
    obs, _groups, events, discussion, comment_links = _process_window(snap, topic_spec, client)
    prev = previous_window(win)
    prev_snap = load_snapshot(db_path, prev)
    prev_client = LLMClient(
        model=client.model,
        max_usd=max(0.0, client.budget.max_usd - client.budget.spent),
        reuse=reuse_flag,
        cache_root=client.cache_root,
        cutoff=prev_snap.cutoff.isoformat(),
        db_md5=prev_snap.db_md5,
        topic=topic_spec.topic,
    )
    prev_client.budget.spent = 0.0
    # share the same remaining budget
    prev_client.budget.max_usd = max(0.0, client.budget.max_usd - client.budget.spent)
    _, _, prev_events, prev_discussion, _ = _process_window(prev_snap, topic_spec, prev_client)
    client.budget.spent += prev_client.budget.spent
    if prev_client.budget.stopped:
        client.budget.stopped = True

    changes = _changes(
        snap,
        prev_snap,
        events=events,
        prev_events=prev_events,
        discussion=discussion,
        prev_discussion=prev_discussion,
    )
    not_processed = sum(1 for o in obs if o.status == "not_processed")
    decisions = assemble_decisions(
        topic=topic_spec.topic,
        window=win,
        publications=snap.publications,
        comments=snap.comments,
        topic_spec=topic_spec,
        observations=obs,
        events=events,
        comment_links=comment_links,
    )
    coverage = {
        "publications": len(snap.publications),
        "comments": len(snap.comments),
        "channels": len({p.source_id for p in snap.publications}),
        "topic_publications": sum(1 for p in decisions["publications"] if p.get("selected_news")),
        "not_processed": not_processed,
        "db_md5": snap.db_md5,
        "cutoff": snap.cutoff.isoformat(),
    }
    payload = build_from_parts(
        topic=topic_spec.topic,
        window=win.requested,
        events=events,
        positions=_positions(obs),
        discussion=discussion if discussion else ([] if events else []),
        changes=changes,
        coverage=coverage,
        limitations=_limitations(snap, client, not_processed),
        evidence=_evidence(obs, events, discussion),
        spend_usd=round(client.budget.spent, 6),
    )
    payload["window"] = {
        "requested": win.requested,
        "start": win.start.isoformat(),
        "end": win.end.isoformat(),
        "cutoff": snap.cutoff.isoformat(),
        "previous": prev.requested,
        "mode": "publication_replay",
    }
    payload["model"] = client.model
    payload["llm"] = {
        "calls": client.calls + prev_client.calls,
        "cache_hits": client.cache_hits + prev_client.cache_hits,
        "spent_usd": round(client.budget.spent, 6),
        "errors": (client.errors + prev_client.errors)[:20],
    }
    if write:
        write_run(payload, topic_spec.topic, win.requested, snap.db_md5, decisions=decisions)
    return payload


def write_run(
    payload: dict,
    topic: str,
    window: str,
    md5: str,
    decisions: dict | None = None,
    root: Path | None = None,
) -> Path:
    out = (root or OUT_ROOT) / topic / window_dir_name(window)
    out.mkdir(parents=True, exist_ok=True)
    pulse_path = out / "pulse.json"
    brief_path = out / "brief.md"
    files = ["pulse.json", "brief.md", "manifest.json"]
    if decisions is not None:
        (out / "decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n")
        files.append("decisions.json")
    manifest = {
        "topic": topic,
        "window": window,
        "created_at": datetime.now(UTC).isoformat(),
        "db_md5": md5,
        "model": payload.get("model"),
        "spend_usd": payload.get("spend_usd"),
        "status": payload.get("status"),
        "files": files,
    }
    pulse_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    brief_path.write_text(payload["brief_markdown"])
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return out


def load_cached_pulse(topic: str, window: str) -> dict | None:
    path = OUT_ROOT / topic / window_dir_name(window) / "pulse.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def news_pulse(db_path: str | Path, topic: str, window: str | None) -> dict[str, Any]:
    """HTTP entry: saved pulse.json or rebuild from LLM cache only. No network."""
    if not window:
        raise ValueError("window must be YYYY-MM-DD..YYYY-MM-DD or ISO_DATETIME..ISO_DATETIME")
    parse_window(window)
    cached = load_cached_pulse(topic, window)
    if cached:
        return cached
    aliases = load_aliases(ALIAS_PATH)
    if topic not in aliases and topic not in {t.topic for t in aliases.values()}:
        # still allow a new topic with aliases; unknown empty topic is 404 only if nothing in corpus later
        pass
    try:
        return build(db_path, topic, window, reuse=True, write=False)
    except ValueError:
        raise
    except Exception as e:
        raise LookupError(f"news pulse for {topic!r} / {window!r} is not cached: {e}") from e


def main(db_path: str, topic: str, window: str) -> None:
    payload = build(db_path, topic, window, write=True)
    print(
        f"{topic} {window}: events={len(payload['events'])} discussion={len(payload['discussion'])} "
        f"spend=${payload.get('spend_usd')} status={payload.get('status')}"
    )
    print(f"wrote artifacts/news-pulse/{topic}/{window_dir_name(window)}/")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main(*sys.argv[1:])
