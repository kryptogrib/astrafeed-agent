"""Grounding check for news-first Pulse briefs.

brief.md is rendered deterministically from pulse.json, so the check has two parts:
  render    brief.md must equal render_markdown(pulse.json) byte for byte;
  claims    every claim in pulse.json is checked against the read-only database:
            headline / member quote / discussion text / evidence quote must be a verbatim
            substring of the linked publication or comment, every number in it must occur
            in that source, and event counters must be recomputable from the members.

Usage:
  python3 docs/research/news_pulse_ground.py --db astrafeed.db RUN_DIR [RUN_DIR ...] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from news_pulse_build import NO_REACTION, render_markdown  # noqa: E402
from news_pulse_link import BASES, _event_blob, _overlap  # noqa: E402

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_texts(db: Path) -> dict[str, str]:
    """Text by link for posts (raw_item.payload.link) and comments (comment.link), read-only."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[str, str] = {}
    try:
        for (payload,) in con.execute("SELECT payload FROM raw_item"):
            try:
                data = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if data.get("link"):
                out[data["link"]] = str(data.get("text") or "")
        for link, text in con.execute("SELECT link, text FROM comment"):
            if link:
                out[link] = str(text or "")
    finally:
        con.close()
    return out


def load_parents(db: Path) -> dict[str, str]:
    """Comment link -> link of the comment it replies to, read-only; the reply chain of a link."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT link, parent_comment_id FROM comment WHERE parent_comment_id IS NOT NULL").fetchall()
    finally:
        con.close()
    return {link: f"{link.split('?')[0]}?comment={parent}" for link, parent in rows if link}


def _ws(text: str) -> str:
    return " ".join((text or "").split())


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in NUMBER.findall(text or "")}


def _claim(kind: str, text: str, sources: list[str], where: str) -> dict:
    found = [s for s in sources if s]
    if kind == "headline" and text.endswith("…"):
        text = text[:-1]  # clipped at a word boundary; the rest must still be verbatim
    verbatim = any(_ws(text) in _ws(s) for s in found)
    numbers_ok = all(any(n in _numbers(s) for s in found) for n in _numbers(text))
    return {
        "kind": kind,
        "where": where,
        "text": text,
        "source_found": bool(found),
        "verbatim": verbatim,
        "numbers_from_source": numbers_ok,
        "grounded": bool(found) and verbatim and numbers_ok,
    }


def _structural(kind: str, where: str, text: str, ok: bool) -> dict:
    return {"kind": kind, "where": where, "text": text, "source_found": True,
            "verbatim": ok, "numbers_from_source": True, "grounded": ok}


def _link_claims(pulse: dict, texts: dict[str, str], parents: dict[str, str]) -> list[dict]:
    """A comment link is a claim too. Its basis must be one the linker emits for that target, a
    named target must exist in this run, and the predicate behind the basis is recomputed from
    the source: a repeated wording must really overlap the event, a reply to the post's event
    must sit under a member post, a thesis must overlap the comment or its reply chain.
    Abstentions (topic_level, project, other_subject) name no event and are checked structurally."""
    events = {ev.get("event_id"): ev for ev in pulse.get("events") or []}
    theses = {pos.get("obs_id"): pos for pos in pulse.get("distribution_and_positions") or []}
    out = []
    for row in pulse.get("discussion") or []:
        url = row.get("url")
        if not url:
            continue  # the "no reaction found" placeholder
        target, target_id, basis = row.get("target"), row.get("target_id"), row.get("basis") or ""
        ok = BASES.get(basis) == target
        text = texts.get(url, "")
        if ok and target == "event" and target_id is not None:
            event = events.get(target_id)
            ok = event is not None
            if ok and basis == "комментарий повторяет формулировку события":
                ok = _overlap(text, _event_blob(event))
            elif ok and basis == "реплика к посту с одним событием по теме и тому же предмету":
                ok = url.split("?")[0] in {m.get("url") for m in event.get("members") or []}
        elif ok and target == "author_thesis":
            thesis = theses.get(target_id)
            ok = thesis is not None and any(
                _overlap(chunk, str(thesis.get("quote") or thesis.get("text") or ""))
                for chunk in _chain_texts(url, texts, parents)
            )
        out.append(_structural("discussion_basis", url, f"{target}: {basis}", ok))
    return out


def _chain_texts(url: str, texts: dict[str, str], parents: dict[str, str]) -> list[str]:
    chain, seen = [texts.get(url, "")], {url}
    for _ in range(8):
        url = parents.get(url, "")
        if not url or url in seen:
            break
        seen.add(url)
        chain.append(texts.get(url, ""))
    return [chain[0], "\n".join(chain)]


def _short_claims(pulse: dict) -> list[dict]:
    """«Коротко» may only repeat event headlines or discussion texts, which are grounded themselves."""
    allowed = {ev.get("headline") for ev in pulse.get("events") or []}
    allowed |= {row.get("text") for row in pulse.get("discussion") or [] if row.get("url")}
    return [
        _structural("short_observation", "short_observations", text, text in allowed)
        for text in pulse.get("short_observations") or []
    ]


def check_run(run: Path, texts: dict[str, str], parents: dict[str, str] | None = None) -> dict:
    pulse = json.loads((run / "pulse.json").read_text(encoding="utf-8"))
    brief = (run / "brief.md").read_text(encoding="utf-8")
    decisions_path = run / "decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8")) if decisions_path.exists() else {}
    # counters use the publication-level origin recorded in decisions.json (a post with several
    # segments gets one origin), falling back to the member's own origin
    pub_by_link = {p["link"]: p for p in decisions.get("publications") or [] if p.get("link")}
    claims: list[dict] = []
    claims.append(
        {
            "kind": "render",
            "where": "brief.md",
            "text": "brief.md == render_markdown(pulse.json)",
            "source_found": True,
            "verbatim": brief == render_markdown(pulse),
            "numbers_from_source": True,
            "grounded": brief == render_markdown(pulse),
        }
    )
    for ev in pulse.get("events") or []:
        members = ev.get("members") or []
        eid = ev.get("event_id")
        srcs = [texts.get(m.get("url") or "", "") for m in members]
        if ev.get("headline"):
            claims.append(_claim("headline", ev["headline"], srcs, eid))
        for m in members:
            if m.get("quote"):
                claims.append(_claim("member_quote", m["quote"], [texts.get(m.get("url") or "", "")], m.get("url")))
        counts = ev.get("counts") or {}
        uniq: dict[str, str] = {}
        sources: dict[str, object] = {}
        for m in members:
            key = m.get("publication_id") or m.get("url")
            if key and key not in uniq:
                rec = pub_by_link.get(m.get("url") or "") or {}
                uniq[key] = rec.get("origin") or m.get("origin") or "unknown"
                sources[key] = rec.get("source_id") if rec else m.get("source_id")
        expect = {
            "publications": len(uniq),
            "channels": len(set(sources.values())),
            "found_origins": sum(1 for o in uniq.values() if o == "own"),
            "reprints": sum(1 for o in uniq.values() if o in {"retelling", "repost"}),
            "unknown_origin": sum(1 for o in uniq.values() if o == "unknown"),
        }
        ok = all(int(counts.get(k, -1)) == v for k, v in expect.items())
        claims.append({"kind": "counts", "where": eid, "text": json.dumps(counts, ensure_ascii=False),
                       "source_found": True, "verbatim": ok, "numbers_from_source": True, "grounded": ok})
    for row in pulse.get("discussion") or []:
        if not row.get("url"):
            continue
        for field in ("text", "quote"):
            text = row.get(field) or ""
            if text and text != NO_REACTION:
                claims.append(_claim(f"discussion_{field}", text, [texts.get(row["url"], "")], row["url"]))
    claims += _link_claims(pulse, texts, parents or {})
    claims += _short_claims(pulse)
    for pos in pulse.get("distribution_and_positions") or []:
        for field in ("text", "quote"):
            text = pos.get(field) or ""
            if text and pos.get("url"):
                claims.append(_claim(f"position_{field}", text, [texts.get(pos["url"], "")], pos["url"]))
    if pulse.get("brief_markdown") is not None and pulse["brief_markdown"] != brief:
        claims.append({"kind": "render", "where": "pulse.json", "text": "brief_markdown != brief.md",
                       "source_found": True, "verbatim": False, "numbers_from_source": True, "grounded": False})
    for ev in pulse.get("evidence") or []:
        url = ev.get("url") or ""
        if ev.get("quote") and url:
            claims.append(_claim("evidence", ev["quote"], [texts.get(url, "")], url))
    grounded = sum(1 for c in claims if c["grounded"])
    return {
        "run": str(run),
        "claims": len(claims),
        "grounded": grounded,
        "fabricated_numbers": sum(1 for c in claims if not c["numbers_from_source"]),
        "failures": [c for c in claims if not c["grounded"]],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="astrafeed.db")
    ap.add_argument("--out", default="artifacts/news-pulse/grounding")
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args(argv)
    db = Path(args.db)
    before = md5(db)
    texts, parents = load_texts(db), load_parents(db)
    reports = [check_run(Path(r), texts, parents) for r in args.runs if (Path(r) / "pulse.json").exists()]
    after = md5(db)
    total = sum(r["claims"] for r in reports)
    grounded = sum(r["grounded"] for r in reports)
    fabricated = sum(r["fabricated_numbers"] for r in reports)
    summary = {
        "db_md5_before": before,
        "db_md5_after": after,
        "claims": total,
        "grounded": grounded,
        "grounding_rate": grounded / total if total else None,
        "fabricated_numbers": fabricated,
        "runs": reports,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grounding.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Подтверждённость брифов news-first Pulse",
        "",
        "Бриф извлекающий: каждое утверждение — дословная цитата источника, числа считает код.",
        "Проверка: brief.md совпадает с рендером pulse.json; каждая цитата, заголовок, реплика и",
        "основание дословно есть в связанной публикации/комментарии БД; все числа из них есть в",
        "источнике; счётчики событий пересчитываются по участникам.",
        "",
        f"MD5 БД до/после: `{before}` / `{after}`.",
        "",
        "| Прогон | Утверждений | Подтверждено | Числа не из источника |",
        "|---|---:|---:|---:|",
    ]
    for r in reports:
        lines.append(f"| `{r['run']}` | {r['claims']} | {r['grounded']} | {r['fabricated_numbers']} |")
    lines += ["", f"Итого: {grounded}/{total} подтверждено, чисел не из источника: {fabricated}.", ""]
    for r in reports:
        for f in r["failures"]:
            lines.append(f"- `{r['run']}` {f['kind']} {f['where']}: {_ws(f['text'])[:160]}")
    (out / "grounding.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"grounded {grounded}/{total}, fabricated numbers {fabricated}; report: {out}")
    return 0 if grounded == total else 1


if __name__ == "__main__":
    sys.exit(main())
