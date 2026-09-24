"""Research Pulse, step 1: a checkable packet of source messages for one topic.

    python3 docs/research/pulse_topic.py astrafeed.db artifacts/entity-candidates \
        artifacts/pulse-eth ethereum eth

Reads detections.jsonl (from entity_candidates.py) and the database read-only.
Writes packet.json and packet.md. The packet does not summarise anything: it only sorts
messages into layers so that a summary written on top of it can cite every claim.

Layers (a comment sits in exactly one, the strongest that applies):
  direct     the comment itself has a confirmed mention of a topic candidate  -> main sample
  ambiguous  only ambiguous mentions ("эфир" without confirmation)             -> shown apart
  echo       the message itself repeats the channel: the same text under >=3 posts
             (a welcome template) or the post in another script at similar length
             (an auto-translation). Posting under every post is only a reason to check,
             not a reason to exclude: active participants do that too.
  undetermined  no mention; it is in the thread of a topic post, or replies to a
             direct/ambiguous comment. Relevance is not determined: it may or may not be
             about the topic until the reply is checked against its post / parent.
Stdlib only.
"""

import collections
import json
from pathlib import Path
import re
import sqlite3
import sys

REASONING = re.compile(r"\b(потому|поэтому|если|значит|т\.?\s?к\.?|так как|но|однако|скорее|думаю|"
                       r"считаю|жду|because|if|but)\b", re.I)
NUMBER = re.compile(r"\d")


def load(db_path):
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    posts = {}
    for r in db.execute("SELECT source_id, external_id, payload FROM raw_item"):
        p = json.loads(r["payload"])
        posts[(r["source_id"], str(r["external_id"]))] = {
            "link": p.get("link"), "channel": p.get("channel_ref"), "ts": p.get("timestamp"),
            "text": p.get("text") or ""}
    comments = {r["comment_id"]: dict(r) for r in db.execute("SELECT * FROM comment")}
    db.close()
    return posts, comments


LATIN = re.compile(r"[a-z]", re.I)
CYRILLIC = re.compile(r"[а-яё]", re.I)


def latin_share(text):
    lat, cyr = len(LATIN.findall(text)), len(CYRILLIC.findall(text))
    return lat / (lat + cyr) if lat + cyr else None


def echo_signal(text, post_text, author_texts):
    """Why this message repeats the channel rather than speaks for a reader, or None."""
    norm = " ".join(text.split()).casefold()
    if len(norm) >= 40 and author_texts[norm] >= 3:
        return "template: same text under >=3 posts"
    a, b = latin_share(text), latin_share(post_text)
    if (a is not None and b is not None and abs(a - b) >= 0.6
            and 0.5 <= len(text) / max(len(post_text), 1) <= 2):
        return "translation: post in another script at similar length"
    return None


def frequent_authors(comments, min_posts=5, share=0.5):
    """Authors with exactly one comment under at least half of a channel's commented posts.
    A reason to check for echo, never a reason to exclude on its own."""
    per = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    threads = collections.defaultdict(set)
    for c in comments.values():
        threads[c["source_id"]].add(c["post_id"])
        if c["author_key"]:
            per[c["source_id"]][c["author_key"]][c["post_id"]] += 1
    out = set()
    for sid, authors in per.items():
        for a, posts in authors.items():
            if (len(posts) >= min_posts and max(posts.values()) == 1
                    and len(posts) >= share * len(threads[sid])):
                out.add((sid, a))
    return out


def substance(text):
    """Rough ranking of how much a reply says. A sort key for reading order, not a quality score."""
    words = len(text.split())
    return (min(words, 60) + 10 * bool(REASONING.search(text)) + 5 * bool(NUMBER.search(text)))


def main(db_path, det_dir, out_dir, *topic):
    topic = set(topic)
    posts, comments = load(db_path)
    by_comment = collections.defaultdict(list)
    post_hits = collections.defaultdict(list)
    for line in open(Path(det_dir) / "detections.jsonl"):
        d = json.loads(line)
        if d["candidate"] not in topic or d["status"] not in ("confirmed", "ambiguous"):
            continue
        if d["status"] == "confirmed" and d["rules"] == ["phrase_head"]:
            continue
        if d["kind"] == "comment":
            by_comment[d["comment_id"]].append(d)
        else:
            post_hits[(d["source_id"], d["post_id"])].append(d)

    def status(hits):
        return "direct" if any(h["status"] == "confirmed" for h in hits) else "ambiguous"

    frequent = frequent_authors(comments)
    author_texts = collections.Counter(
        (c["source_id"], c["author_key"], " ".join((c["text"] or "").split()).casefold())
        for c in comments.values() if c["author_key"])
    echo_why = {}
    for cid, c in comments.items():
        if (c["source_id"], c["author_key"]) not in frequent:
            continue
        texts = collections.Counter({t: n for (sid, a, t), n in author_texts.items()
                                     if (sid, a) == (c["source_id"], c["author_key"])})
        post_text = posts.get((c["source_id"], str(c["post_id"])), {}).get("text", "")
        why = echo_signal(c["text"] or "", post_text, texts)
        if why:
            echo_why[cid] = why
    layer = {cid: "echo" if cid in echo_why else status(h) for cid, h in by_comment.items()}
    topic_threads = {k for k, hits in post_hits.items()
                     if any(h["status"] == "confirmed" for h in hits)}
    for cid, c in comments.items():
        if cid in layer or not (c["text"] or "").strip():
            continue
        parent = c["parent_comment_id"]
        if (c["source_id"], str(c["post_id"])) in topic_threads:
            layer[cid] = "echo" if cid in echo_why else "undetermined"
        elif parent and layer.get(parent) in ("direct", "ambiguous"):
            layer[cid] = "undetermined"

    items = []
    for cid, kind in layer.items():
        c = comments[cid]
        post = posts.get((c["source_id"], str(c["post_id"])), {})
        parent = comments.get(c["parent_comment_id"]) if c["parent_comment_id"] else None
        items.append({
            "layer": kind, "link": c["link"], "ts": str(c["ts"]), "author": c["author_key"],
            "source_id": c["source_id"], "channel": post.get("channel"),
            "thread": post.get("link"), "thread_post_mentions_topic":
                (c["source_id"], str(c["post_id"])) in topic_threads,
            "reply_to": parent["link"] if parent else None,
            "reply_to_layer": layer.get(c["parent_comment_id"]),
            "frequent_author": (c["source_id"], c["author_key"]) in frequent,
            "echo_signal": echo_why.get(cid),
            "text": c["text"], "substance": substance(c["text"] or ""),
            "hits": [{"surface": h["surface"], "candidate": h["candidate"], "status": h["status"],
                      "rules": h["rules"], "hint": h["hint"]} for h in by_comment.get(cid, [])]})
    items.sort(key=lambda x: (x["layer"], -x["substance"]))

    def stats(sel):
        threads = collections.Counter(x["thread"] for x in sel)
        top = threads.most_common(1)
        ts = sorted(x["ts"] for x in sel)
        return {"comments": len(sel), "authors": len({x["author"] for x in sel if x["author"]}),
                "author_unknown": sum(1 for x in sel if not x["author"]),
                "sources": len({x["source_id"] for x in sel}), "threads": len(threads),
                "largest_thread": top[0][0] if top else None,
                "largest_thread_share": round(top[0][1] / len(sel), 2) if top else None,
                "first_ts": ts[0] if ts else None, "last_ts": ts[-1] if ts else None}

    per_layer = {k: stats([x for x in items if x["layer"] == k]) for k in ("direct", "ambiguous", "echo", "undetermined")}
    post_rows = []
    for k, hits in post_hits.items():
        p = posts.get(k, {})
        n_comments = sum(1 for c in comments.values() if (c["source_id"], str(c["post_id"])) == k)
        post_rows.append({"link": p.get("link"), "channel": p.get("channel"), "ts": p.get("ts"),
                          "status": status(hits),
                          "only_in_template_lines": all(h["template_candidate"] for h in hits),
                          "comments_in_db": n_comments,
                          "fragments": sorted({h["fragment"][:140] for h in hits})[:3]})
    post_rows.sort(key=lambda x: (-x["comments_in_db"], x["ts"] or ""))
    post_ts = sorted(p["ts"] for p in post_rows if p["ts"])
    packet = {
        "topic": sorted(topic),
        "note": "Historical snapshot of astrafeed.db, not the last 24 hours. "
                "Undetermined-layer comments have no mention; whether they are about the topic "
                "is not determined yet.",
        "frequent_authors": sorted(f"{sid}:{a}" for sid, a in frequent),
        "posts": {"total": len(post_rows),
                  "confirmed": sum(p["status"] == "direct" for p in post_rows),
                  "ambiguous_only": sum(p["status"] == "ambiguous" for p in post_rows),
                  "only_in_template_lines": sum(p["only_in_template_lines"] for p in post_rows),
                  "channels": len({p["channel"] for p in post_rows}),
                  "first_ts": post_ts[0] if post_ts else None, "last_ts": post_ts[-1] if post_ts else None,
                  "with_comments": [p for p in post_rows if p["comments_in_db"]]},
        "comments": per_layer,
        "items": items,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1))
    (out / "packet.md").write_text(render(packet))
    print(json.dumps({"posts": {k: v for k, v in packet["posts"].items() if k != "with_comments"},
                      "comments": per_layer}, ensure_ascii=False, indent=1))


def render(packet):
    out = [f"# Пакет источников: {', '.join(packet['topic'])}", "", f"> {packet['note']}", ""]
    p = packet["posts"]
    out += [f"Посты с упоминанием: {p['total']} (подтверждённых {p['confirmed']}, только неоднозначных "
            f"{p['ambiguous_only']}; только в шаблонных строках {p['only_in_template_lines']}), каналов "
            f"{p['channels']}, {p['first_ts']} — {p['last_ts']}.", ""]
    out += ["| слой | комментариев | авторов (+без автора) | источников | тредов | крупнейший тред | доля | период |",
            "|---|---:|---:|---:|---:|---|---:|---|"]
    for k, s in packet["comments"].items():
        out.append(f"| {k} | {s['comments']} | {s['authors']} (+{s['author_unknown']}) | {s['sources']} | {s['threads']} | "
                   f"{s['largest_thread']} | {s['largest_thread_share']} | {s['first_ts']} — {s['last_ts']} |")
    out += ["", "## Посты с упоминанием и комментариями в базе", ""]
    for x in p["with_comments"]:
        out.append(f"- {x['link']} ({x['status']}, комм. {x['comments_in_db']}"
                   f"{', только шаблон' if x['only_in_template_lines'] else ''}): «{x['fragments'][0]}»")
    for kind, title in (("direct", "Прямые упоминания (основная выборка)"),
                        ("ambiguous", "Только неоднозначные упоминания (отдельно)"),
                        ("echo", "Эхо канала: шаблон или перевод поста (не аудитория)"),
                        ("undetermined", "Без упоминания, релевантность не определена")):
        sel = [x for x in packet["items"] if x["layer"] == kind]
        out += ["", f"## {title}: {len(sel)}", ""]
        for x in sel:
            hits = "; ".join(f"{h['surface']}→{h['candidate']} [{h['status']}"
                             f"{', ' + h['hint'] if h['hint'] else ''}]" for h in x["hits"])
            why = x["echo_signal"] or hits or ("ответ на " + x["reply_to"] if x["reply_to_layer"] else "в треде поста")
            text = " ".join(x["text"].split())
            out.append(f"- [{x['link'].replace('https://t.me/', '')}]({x['link']}) "
                       f"`{x['ts'][:16]}` a:{x['author']} — {why}\n  > {text[:400]}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main(*sys.argv[1:])
