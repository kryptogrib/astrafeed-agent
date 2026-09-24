"""Experiment: what does a thread comment react to — an event, the author's thesis, the project, another subject?

Compares the production linker (news_pulse_link.link_comment) with a contextual LLM reading of the
thread. Research only: nothing here is imported by the news-pulse build.

    python3 docs/research/reaction_subject.py sample --db astrafeed.db   # threads, split, baseline
    python3 docs/research/reaction_subject.py llm --db astrafeed.db [--reuse] [--dry-run]
    python3 docs/research/reaction_subject.py eval                       # metrics + report

Labels in artifacts/reaction-subject/labels.jsonl are preliminary agent labels, fixed before the
prompt was written; `disputed` marks cases for human review. The test split is never used to tune.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path("artifacts/reaction-subject")
TOPICS = ("eth", "zec", "arc", "aave")
WINDOW = "2026-09-09..2026-09-23"
MAX_PER_THREAD = 6
GOLD = (
    "artifacts/news-eval/posts.jsonl",
    "artifacts/news-eval/comments.jsonl",
    "artifacts/news-tune/posts.jsonl",
    "artifacts/news-tune/comments.jsonl",
)
TARGETS = ("event", "author_thesis", "project", "other_subject", "unclear")
# production link targets in the experiment's vocabulary; topic_level is the linker's abstention
BASELINE_TARGET = {"topic_level": "unclear"}


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def gold_posts() -> set[str]:
    seen: set[str] = set()
    for name in GOLD:
        for row in _read(Path(name)):
            for key in ("link", "url"):
                if row.get(key):
                    seen.add(str(row[key]).split("?")[0])
    return seen


def process(db: str, topic: str, window: str = WINDOW, reuse: bool = True):
    """The production window pass, cache-only: snapshot, events, theses and baseline links."""
    from news_pulse_build import ALIAS_PATH, _process_window
    from news_pulse_llm import DEFAULT_MODEL, LLMClient
    from news_pulse_load import load_aliases, load_snapshot, parse_window, resolve_topic

    spec = resolve_topic(topic, load_aliases(ALIAS_PATH))
    snap = load_snapshot(db, parse_window(window))
    client = LLMClient(
        model=os.environ.get("NEWS_PULSE_MODEL") or DEFAULT_MODEL,
        reuse=reuse,
        cache_root=Path("artifacts/news-pulse/cache"),
        cutoff=snap.cutoff.isoformat(),
        db_md5=snap.db_md5,
        topic=spec.topic,
    )
    obs, _groups, events, discussion, links = _process_window(snap, spec, client)
    return snap, obs, events, discussion, links


def thread_kind(events: list[dict], theses: list[dict]) -> str:
    if events and theses:
        return "mixed"
    if theses:
        return "author_forecast"
    if events:
        return "news"
    return "topic_shift"


def _chain(comment, by_id: dict) -> list[dict]:
    """Ancestors only: every one is earlier than the comment, so no future context leaks in."""
    out, cur, seen = [], comment, {comment.pub_id}
    for _ in range(8):
        pid = cur.parent_id
        if not pid or pid not in by_id or pid in seen:
            break
        cur = by_id[pid]
        seen.add(cur.pub_id)
        out.append({"url": cur.url, "published_at": cur.published_at.isoformat(), "text": cur.text or ""})
    return list(reversed(out))


def sample(db: str) -> None:
    gold = gold_posts()
    threads: dict[str, dict] = {}
    baseline: list[dict] = []
    for topic in TOPICS:
        snap, obs, events, discussion, _links = process(db, topic)
        pubs = {p.pub_id: p for p in snap.publications}
        comments = {c.pub_id: c for c in snap.comments}
        by_url = {c.url: c for c in snap.comments}
        for row in discussion:
            c = by_url.get(row["url"])
            post = pubs.get(c.thread_id or "") if c else None
            if c is None or post is None or post.url in gold:
                continue
            post_events = [
                {
                    "event_id": e["event_id"],
                    "headline": e.get("headline"),
                    "quotes": [m.get("quote") for m in e.get("members") or [] if m.get("publication_id") == post.pub_id],
                }
                for e in events
                if any(m.get("publication_id") == post.pub_id for m in e.get("members") or [])
            ]
            theses = [
                {"thesis_id": o.obs_id, "quote": o.quote}
                for o in obs
                if o.publication_id == post.pub_id and o.kind == "author_position" and o.status == "ok"
            ]
            key = f"{topic}|{post.url}"
            th = threads.setdefault(
                key,
                {
                    "thread": post.url,
                    "topic": topic,
                    "kind": thread_kind(post_events, theses),
                    "post": {"url": post.url, "published_at": post.published_at.isoformat(), "text": post.text or ""},
                    "events": post_events,
                    "theses": theses,
                    "comments": [],
                },
            )
            th["comments"].append(
                {
                    "id": f"{topic}|{c.url}",
                    "url": c.url,
                    "published_at": c.published_at.isoformat(),
                    "text": c.text or "",
                    "chain": _chain(c, comments),
                }
            )
            baseline.append(
                {
                    "id": f"{topic}|{c.url}",
                    "target": BASELINE_TARGET.get(row["target"], row["target"]),
                    "target_id": row.get("target_id"),
                    "basis": row.get("basis"),
                }
            )
    # a post discussed under several topics is kept once, under the topic with the most replies
    best: dict[str, dict] = {}
    for th in threads.values():
        cur = best.get(th["thread"])
        if cur is None or (len(th["comments"]), bool(th["events"] or th["theses"])) > (
            len(cur["comments"]),
            bool(cur["events"] or cur["theses"]),
        ):
            best[th["thread"]] = th
    rows = []
    for th in sorted(best.values(), key=lambda t: t["thread"]):
        picked = sorted(th["comments"], key=lambda c: _h(c["url"]))[:MAX_PER_THREAD]
        th["n_discussion"] = len(th["comments"])
        th["comments"] = sorted(picked, key=lambda c: c["published_at"])
        rows.append(th)
    # split by thread inside each kind, fixed by hash before any prompt exists
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for th in rows:
        by_kind[th["kind"]].append(th)
    for group in by_kind.values():
        group.sort(key=lambda t: _h(t["thread"]))
        for i, th in enumerate(group):
            th["split"] = "dev" if i % 3 == 1 else "test"
    keep = {c["id"] for th in rows for c in th["comments"]}
    _jsonl(OUT / "threads.jsonl", rows)
    _jsonl(OUT / "baseline.jsonl", [b for b in baseline if b["id"] in keep])
    counts = Counter((th["split"], th["kind"]) for th in rows)
    n = sum(len(th["comments"]) for th in rows)
    print(f"threads={len(rows)} comments={n} {dict(sorted(counts.items()))}")


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())[:80]


def label() -> None:
    """labels.jsonl from the preliminary labels; a test comment repeating a dev text is not scored."""
    from reaction_subject_labels import LABELS

    rows = _read(OUT / "threads.jsonl")
    dev_texts = {_norm(c["text"]) for th in rows if th["split"] == "dev" for c in th["comments"] if c["text"].strip()}
    out = []
    for i, th in enumerate(rows):
        for j, c in enumerate(th["comments"]):
            target, target_id, reason, disputed = LABELS[(i, j)]
            if th["split"] == "test" and target != "skip" and _norm(c["text"]) in dev_texts:
                target, reason = "skip", f"близкий дубль реплики из dev; {reason}"
            out.append(
                {
                    "id": c["id"],
                    "thread": th["thread"],
                    "channel": th["thread"].split("/")[3],
                    "published_at": c["published_at"],
                    "split": th["split"],
                    "kind": th["kind"],
                    "target": target,
                    "target_id": target_id,
                    "reason": reason,
                    "disputed": disputed,
                    "status": "preliminary",
                }
            )
    assert len(out) == len(LABELS), "every sampled comment needs a label"
    _jsonl(OUT / "labels.jsonl", out)
    print(Counter((r["split"], r["target"]) for r in out))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--db", default="astrafeed.db")
    sub.add_parser("label")
    args = ap.parse_args()
    t0 = time.time()
    if args.cmd == "sample":
        sample(args.db)
    elif args.cmd == "label":
        label()
    print(f"{args.cmd}: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
