"""Transfer check for reaction_subject v2 on channels that were never used for dev or prompts.

The snapshot is described by artifacts/reaction-subject/transfer/snapshot.json (gitignored DB, md5,
window, cutoff, coverage). Every thread here is test: nothing from these channels tunes anything.

    python3 docs/research/reaction_subject_transfer.py sample --db astrafeed-transfer.db
    python3 docs/research/reaction_subject_transfer.py estimate
    python3 docs/research/reaction_subject_transfer.py llm --db astrafeed-transfer.db [--pay --max-usd X]
    python3 docs/research/reaction_subject_transfer.py eval

llm and eval run reaction_subject_v2 unchanged (prompt, id contract, verifier) on this sample and
write to artifacts/reaction-subject/transfer/v2. Labels are preliminary: disputed ones and cut chains
are reported as separate slices.

The sample reuses v1's selection unchanged (MAX_PER_THREAD comments by url hash, one topic per post).
Per example it records `missing_parent` (a reply whose parent is not in the thread, so its chain is
cut) and `nontext_parent` (an ancestor without text); such examples are kept and scored separately.
Posts and comments that nearly repeat v1 threads or the frozen gold are dropped before labelling.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reaction_subject import (  # noqa: E402
    BASELINE_TARGET,
    GOLD,
    MAX_PER_THREAD,
    OUT,
    TOPICS,
    _chain,
    _h,
    _jsonl,
    _read,
    thread_kind,
)

OUT_T = OUT / "transfer"
OUT_TV2 = OUT_T / "v2"
MANIFEST = OUT_T / "snapshot.json"
MIN_DUP_CHARS = 30
DUP_JACCARD = 0.8


def manifest(db: str) -> dict:
    from news_pulse_load import db_md5

    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if db_md5(db) != m["db_md5"]:
        raise SystemExit(f"{db} md5 differs from {MANIFEST}: results would not match the snapshot")
    return m


def process(db: str, topic: str, window: str):
    """Cache-only pass of the production window pipeline on the transfer snapshot."""
    from news_pulse_build import ALIAS_PATH, _process_window
    from news_pulse_llm import DEFAULT_MODEL, LLMClient
    from news_pulse_load import load_aliases, load_snapshot, parse_window, resolve_topic

    spec = resolve_topic(topic, load_aliases(ALIAS_PATH))
    snap = load_snapshot(db, parse_window(window))
    client = LLMClient(
        model=DEFAULT_MODEL,
        reuse=True,
        cache_root=OUT_T / "cache",
        cutoff=snap.cutoff.isoformat(),
        db_md5=snap.db_md5,
        topic=spec.topic,
    )
    obs, _groups, events, discussion, _links = _process_window(snap, spec, client)
    if client.errors:
        raise SystemExit(f"{topic}: {len(client.errors)} cache misses/errors, e.g. {client.errors[:2]}")
    return snap, obs, events, discussion


def _norm(text: str) -> str:
    text = re.sub(r"https?://\S+|@\w+", " ", text.casefold())
    return " ".join(re.findall(r"\w+", text))


def _grams(text: str) -> set[str]:
    return {text[i : i + 5] for i in range(max(1, len(text) - 4))}


class Seen:
    """Near-duplicate lookup: exact normalized text, or 5-gram Jaccard for texts long enough to mean it."""

    def __init__(self, texts: list[str]) -> None:
        self.exact = {_norm(t) for t in texts if len(_norm(t)) >= MIN_DUP_CHARS}
        self.grams = [_grams(t) for t in self.exact]

    def hit(self, text: str) -> bool:
        n = _norm(text)
        if len(n) < MIN_DUP_CHARS:
            return False
        if n in self.exact:
            return True
        g = _grams(n)
        return any(len(g & o) / len(g | o) >= DUP_JACCARD for o in self.grams)


def reference_texts() -> tuple[list[str], list[str], set[str]]:
    """Posts, comments and urls of v1 threads (dev and test) and of the frozen gold."""
    posts, comments, urls = [], [], set()
    for th in _read(OUT / "threads.jsonl"):
        posts.append(th["post"]["text"])
        urls.add(th["thread"])
        for c in th["comments"]:
            comments.append(c["text"])
            comments.extend(m["text"] for m in c["chain"])
            urls.add(c["url"])
    for name in GOLD:
        for row in _read(Path(name)):
            (comments if "comments" in name else posts).append(row.get("text") or "")
            for key in ("link", "url"):
                if row.get(key):
                    urls.add(str(row[key]).split("?")[0] if "posts" in name else str(row[key]))
    return posts, comments, urls


def _flags(c, by_id: dict) -> dict:
    """Walks the real ancestry by (source, post, comment) ids, so ids of other threads never match."""
    missing, nontext, cur = False, False, c
    for _ in range(8):
        pid = cur.parent_id
        if not pid or pid == c.thread_id:
            break
        if pid not in by_id:
            missing = True
            break
        cur = by_id[pid]
        if not (cur.text or "").strip():
            nontext = True
        if cur.published_at > c.published_at:
            raise SystemExit(f"{c.url}: ancestor {cur.url} is later than the reply")
    return {"missing_parent": missing, "nontext_parent": nontext}


def sample(db: str) -> None:
    m = manifest(db)
    window = f"{m['window_utc']['start']}..{m['window_utc']['end']}"
    ref_posts, ref_comments, ref_urls = reference_texts()
    seen_posts, seen_comments = Seen(ref_posts), Seen(ref_comments)
    threads: dict[str, dict] = {}
    baseline: list[dict] = []
    dropped: Counter = Counter()
    for topic in TOPICS:
        snap, obs, events, discussion = process(db, topic, window)
        pubs = {p.pub_id: p for p in snap.publications}
        comments = {c.pub_id: c for c in snap.comments}
        by_url = {c.url: c for c in snap.comments}
        for row in discussion:
            c = by_url.get(row["url"])
            post = pubs.get(c.thread_id or "") if c else None
            if c is None or post is None:
                dropped["no_post"] += 1
                continue
            if post.url in ref_urls or c.url in ref_urls:
                dropped["same_url_as_v1_or_gold"] += 1
                continue
            if seen_posts.hit(post.text or ""):
                dropped["post_near_dup"] += 1
                continue
            chain = _chain(c, comments)
            if seen_comments.hit(c.text or "") or any(seen_comments.hit(x["text"]) for x in chain):
                dropped["comment_or_chain_near_dup"] += 1
                continue
            post_events = [
                {
                    "event_id": e["event_id"],
                    "headline": e.get("headline"),
                    "quotes": [
                        x.get("quote") for x in e.get("members") or [] if x.get("publication_id") == post.pub_id
                    ],
                }
                for e in events
                if any(x.get("publication_id") == post.pub_id for x in e.get("members") or [])
            ]
            theses = [
                {"thesis_id": o.obs_id, "quote": o.quote}
                for o in obs
                if o.publication_id == post.pub_id and o.kind == "author_position" and o.status == "ok"
            ]
            th = threads.setdefault(
                f"{topic}|{post.url}",
                {
                    "thread": post.url,
                    "topic": topic,
                    "channel": (post.metadata or {}).get("channel"),
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
                    "chain": chain,
                    **_flags(c, comments),
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
    # same rule as v1: a post discussed under several topics is kept once
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
        th["comments"] = [c for c in th["comments"] if c["text"].strip()]
        if not th["comments"]:
            continue
        picked = sorted(th["comments"], key=lambda c: _h(c["url"]))[:MAX_PER_THREAD]
        th["n_discussion"] = len(th["comments"])
        th["comments"] = sorted(picked, key=lambda c: c["published_at"])
        th["split"] = "test"
        rows.append(th)
    keep = {c["id"] for th in rows for c in th["comments"]}
    _jsonl(OUT_T / "threads.jsonl", rows)
    _jsonl(OUT_T / "baseline.jsonl", [b for b in baseline if b["id"] in keep])
    cs = [c for th in rows for c in th["comments"]]
    summary = {
        "db_md5": m["db_md5"],
        "window": window,
        "threads": len(rows),
        "comments": len(cs),
        "by_kind": dict(Counter(th["kind"] for th in rows)),
        "comments_by_kind": dict(Counter(th["kind"] for th in rows for _ in th["comments"])),
        "by_topic": dict(Counter(th["topic"] for th in rows)),
        "by_channel": dict(Counter(th["channel"] for th in rows)),
        "missing_parent": sum(c["missing_parent"] for c in cs),
        "nontext_parent": sum(c["nontext_parent"] for c in cs),
        "dropped_before_sampling": dict(dropped),
        "dedup": {"min_chars": MIN_DUP_CHARS, "jaccard_5gram": DUP_JACCARD},
    }
    (OUT_T / "sample.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


SLICES = {
    "all": lambda g: True,
    "undisputed": lambda g: not g["disputed"],
    "disputed": lambda g: g["disputed"],
    "chain_complete": lambda g: not g["missing_parent"] and not g["nontext_parent"],
    "missing_parent": lambda g: g["missing_parent"],
    "nontext_parent": lambda g: g["nontext_parent"],
    "news": lambda g: g["kind"] == "news",
    "topic_shift": lambda g: g["kind"] == "topic_shift",
}
COLS = [
    "n",
    "answered",
    "cache_miss",
    "unprocessed",
    "claimed",
    "claim_correct",
    "claim_wrong",
    "false_event",
    "abstained",
    "status_no_id",
    "status_rejected",
    "coverage",
    "recall",
]


def evaluate() -> None:
    from reaction_subject_v2 import score, v2_arms

    labels = [r for r in _read(OUT_T / "labels.jsonl") if r["target"] != "skip"]
    arms = {"baseline": {r["id"]: {**r, "status": "ok"} for r in _read(OUT_T / "baseline.jsonl")}, **v2_arms(OUT_TV2)}
    result = {
        part: {name: {"n": len(gold), **score(p, gold)} for name, p in arms.items()}
        for part, keep in SLICES.items()
        for gold in [[g for g in labels if keep(g)]]
    }
    gold_n = Counter(g["target"] for g in labels)
    lines = [
        "# Reaction subject v2 on transfer channels — generated tables",
        "",
        "New channels, never used for dev or prompts. Labels are preliminary and not human-checked;",
        f"{sum(g['disputed'] for g in labels)} of {len(labels)} are disputed. Gold targets: {dict(gold_n)}.",
        "",
    ]
    for part in SLICES:
        lines += [f"## {part}", "", "| arm | " + " | ".join(COLS) + " |", "|---" * (len(COLS) + 1) + "|"]
        lines += [f"| {a} | " + " | ".join(str(sc.get(c, 0)) for c in COLS) + " |" for a, sc in result[part].items()]
        lines.append("")
    # event and thesis apart: an event link needs an id of this post, a thesis here has no id (none extracted)
    lines += [
        "## event и thesis отдельно (all)",
        "",
        "| arm | event: верно / заявлено | event: найдено / в эталоне | ложных event | thesis: класс заявлен / в эталоне |",
        "|---|---|---|---|---|",
    ]
    for a, sc in result["all"].items():
        lines.append(
            f"| {a} | {sc.get('pred_event_ok', 0)}/{sc.get('pred_event', 0)} | "
            f"{sc.get('gold_event_found', 0)}/{sc.get('gold_event', 0)} | {sc.get('false_event', 0)} | "
            f"{sc.get('thesis_class_found', 0)}/{sc.get('gold_author_thesis', 0)} |"
        )
    lines.append("")
    lines += _availability(arms, labels)
    run = json.loads((OUT_TV2 / "run.json").read_text()) if (OUT_TV2 / "run.json").exists() else {}
    lines += [f"Run: {run}", ""]
    (OUT_TV2 / "eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT_TV2 / "eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def _availability(arms: dict[str, dict[str, dict]], labels: list[dict]) -> list[str]:
    """Separates a missing candidate (extraction) from a wrong link (linker) and gives end-to-end recall."""
    groups = {
        "event, id есть в посте": lambda g: g["target"] == "event" and g["target_id"],
        "event, событие не извлечено": lambda g: g["target"] == "event" and not g["target_id"],
        "thesis, тезис не извлечён": lambda g: g["target"] == "author_thesis" and not g["target_id"],
    }
    lines = [
        "## Доступность цели и качество связи",
        "",
        "Без извлечённого id связь по контракту невозможна: для таких меток верный ответ системы — "
        "воздержание (unclear/no_id), а промах — это пробел извлечения, не связывателя.",
        "",
        "| arm | группа | в эталоне | связано верно | связано с другой целью | воздержание | прочие статусы |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, preds in arms.items():
        for label, keep in groups.items():
            gold = [g for g in labels if keep(g)]
            c: Counter = Counter()
            for g in gold:
                pr = preds.get(g["id"]) or {"target": None, "status": "cache_miss"}
                if pr.get("status", "ok") not in ("ok", "no_id", "rejected"):
                    c["other"] += 1
                elif pr["target"] in (None, "unclear"):
                    c["abstain"] += 1
                elif pr["target"] == g["target"] and pr.get("target_id") == g["target_id"]:
                    c["ok"] += 1
                else:
                    c["wrong"] += 1
            lines.append(
                f"| {name} | {label} | {len(gold)} | {c['ok']} | {c['wrong']} | {c['abstain']} | {c['other']} |"
            )
    lines.append("")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--db", default="astrafeed-transfer.db")
    sub.add_parser("estimate")
    r = sub.add_parser("llm")
    r.add_argument("--db", default="astrafeed-transfer.db")
    r.add_argument("--pay", action="store_true", help="allow paid calls on cache miss (needs user approval)")
    r.add_argument("--max-usd", type=float, default=0.10)
    sub.add_parser("eval")
    args = ap.parse_args()
    if args.cmd == "sample":
        sample(args.db)
    elif args.cmd == "estimate":
        from reaction_subject_v2 import estimate

        estimate(OUT_T)
    elif args.cmd == "llm":
        from reaction_subject_v2 import run_llm

        manifest(args.db)
        run_llm(args.db, pay=args.pay, max_usd=args.max_usd, src=OUT_T, dst=OUT_TV2)
    elif args.cmd == "eval":
        evaluate()


if __name__ == "__main__":
    main()
