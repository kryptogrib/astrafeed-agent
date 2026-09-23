"""FROZEN copy for contract v2 (artifacts/pulse-eth/thread-*/v2); the current script is
pulse_classify_thread.py (v3). Kept only to re-render v2 reports from saved responses.

Research Pulse, step 2: classify every reply of ONE thread in context, in one LLM call.

    python3 docs/research/pulse_classify_thread.py astrafeed.db artifacts/entity-candidates \
        https://t.me/rawa_imagination/21055 ethereum artifacts/pulse-eth/thread-21055 \
        [model] [labels.tsv]
    python3 docs/research/pulse_classify_thread.py sheet astrafeed.db https://t.me/don_invest/5296 out.tsv

The post and all its comments (ids, reply links, anonymised authors) go into a single request,
so the post is paid for once, not once per reply. The model may only name entities that
entity_candidates.py found in this thread (plus other/unknown), and a contextual link must cite
the post or a parent comment. Both rules are checked after the call, not trusted: a failed check is
a flag for review, never a silent exclusion.

`sheet` writes a blank labelling sheet for a person (thread text only, no model output).

Writes meta.json, request.json, response.json, labels.json, report.md. meta.json holds the prompt
version and hashes of the prompt and of the input; PULSE_REUSE=1 re-checks a saved response and
refuses when either hash differs (a changed prompt needs a new call). Database is opened read-only.
The API key is read from OPENROUTER_API_KEY or .env. Stdlib only.
"""

import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import urllib.request

RELATIONS = ("direct", "contextual", "unrelated", "unclear")
ASPECTS = ("market", "payment", "technology", "other")
STANCES = ("support", "oppose", "mixed", "unclear")
SKIP_RULES = {"hashtag"}  # labels of the post, not things people talk about

PROMPT_VERSION = "v2-mention-subject-claim"
PROMPT = """You label replies in one Telegram discussion thread. Topic of interest: {topic}.

For EVERY message id in `comments` return one object:
  id             the comment id
  entity         what the reply is about: one of {entities}, or "other", or "unknown"
  topic_relation relation to the topic {topic}:
                   direct      the reply's OWN text names {topic} (name, ticker or alias, slang included)
                   contextual  the reply is about {topic} or the post's claim about {topic}, but that is
                               clear only from the post or a message it answers (e.g. "2500 must hold?"
                               under a post that sets 2500 for {topic})
                   unrelated   another subject
                   unclear     not enough data to tell
  mention        for direct only: the exact fragment of the reply's text that names {topic}, copied
                 character for character (e.g. "эфира"); null otherwise
  subject        what the reply discusses, a few words (e.g. "altseason timing", "mint price");
                 null for greetings and banter with no subject
  aspect         for direct / contextual only: market (price, trading, cycle, liquidations),
                 payment ({topic} spent to buy something, as gas, wallet balance), technology, other;
                 null for unrelated / unclear
  claim          the concrete thesis the reply takes a position on, as one statement in <=15 words of
                 English (e.g. "the current move is a false breakout"). It may be a thesis from the post
                 or the parent that the reply answers. null if there is no definite thesis (jokes, bare
                 questions, facts with no position)
  stance         the reply's position toward `claim`: support / oppose / mixed / unclear. unclear when
                 claim is null or the sarcasm is ambiguous. This is NOT a mood about {topic}.
  evidence_ids   direct: its own id. contextual: "post" and/or the parent / ancestor ids that carry the
                 link to {topic}. unrelated: the post or ancestor ids whose subject this reply continues
                 (e.g. a reply about altseason timing under a post about altseason); [] if the reply
                 starts a new subject. Being in the same thread is NOT evidence.

Rules: judge each reply with its reply chain; do not assume a reply is about {topic} because the post is.
A reply to an off-topic message may return to {topic}: judge its own text too.
A price in a currency is not payment. "[media]" marks an image you cannot see: use unclear only when
the meaning cannot be understood without it; a short text with an image is otherwise judged by its text.
reply_to "missing:<id>" means the parent message is not available.
Answer with JSON only: {{"labels": [ ... ]}}"""


def sha(obj):
    data = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for line in Path(".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENROUTER_API_KEY not set")


def load_thread(db_path, link):
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    for r in db.execute("SELECT source_id, external_id, payload FROM raw_item"):
        p = json.loads(r["payload"])
        if p.get("link") == link:
            sid, pid, post = r["source_id"], str(r["external_id"]), p.get("text") or ""
            break
    else:
        raise SystemExit(f"post not found: {link}")
    rows = [dict(r) for r in db.execute(
        "SELECT comment_id, parent_comment_id, author_key, ts, text, has_media, link FROM comment "
        "WHERE source_id=? AND post_id=? ORDER BY comment_id", (sid, pid))]
    db.close()
    return sid, pid, post, rows


def thread_entities(det_dir, sid, pid):
    found = collections.Counter()
    for line in open(Path(det_dir) / "detections.jsonl"):
        d = json.loads(line)
        if (d["source_id"], d["post_id"]) != (sid, pid) or d["status"] not in ("confirmed", "ambiguous"):
            continue
        if set(d["rules"]) <= SKIP_RULES or d["rules"] == ["phrase_head"]:
            continue
        found[d["candidate"]] += 1
    return sorted(found)


def call(model, prompt, payload):
    body = {"model": model, "temperature": 0,
            "response_format": {"type": "json_object"},
            "usage": {"include": True}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    return body, resp, round(time.time() - t0, 1)


def check(labels, rows, entities):
    """Structural checks that do not need a gold file."""
    parent = {str(r["comment_id"]): str(r["parent_comment_id"] or "post") for r in rows}
    ids = set(parent)
    text = {str(r["comment_id"]): (r["text"] or "").casefold() for r in rows}

    def ancestors(cid):
        out, cur = set(), cid
        while cur in parent:
            cur = parent[cur]
            out.add(cur)
        return out

    on_topic = {str(x.get("id")) for x in labels if x.get("topic_relation") in ("direct", "contextual")}
    problems = collections.defaultdict(list)
    seen = set()
    for x in labels:
        cid = str(x.get("id"))
        seen.add(cid)
        if cid not in ids:
            problems["unknown_id"].append(cid)
            continue
        rel = x.get("topic_relation")
        for f, allowed in (("topic_relation", RELATIONS), ("stance", STANCES),
                           ("aspect", ASPECTS if rel in ("direct", "contextual") else (None,))):
            if x.get(f) not in allowed:
                problems[f"bad_{f}"].append(cid)
        mention = (x.get("mention") or "").casefold()
        if rel == "direct" and not mention:
            problems["direct_without_mention"].append(cid)
        elif rel == "direct" and mention not in text[cid]:
            problems["mention_not_in_text"].append(f"{cid}:{x.get('mention')}")
        if x.get("entity") not in (*entities, "other", "unknown"):
            problems["entity_outside_thread"].append(f"{cid}:{x.get('entity')}")
        ev = {str(e) for e in x.get("evidence_ids") or []}
        if ev - ids - {"post"}:
            problems["evidence_not_in_thread"].append(cid)
        if x.get("topic_relation") == "contextual":
            if not (ev & (ancestors(cid) | {"post"})):
                problems["contextual_without_post_or_parent"].append(cid)
            # the cited message must itself carry the topic, otherwise the link is only "same thread"
            elif not ((ev - {cid}) & ({"post"} | on_topic)):
                problems["contextual_evidence_off_topic"].append(cid)
        if rel == "unrelated" and ev and not (ev & (ancestors(cid) | {"post"})):
            problems["related_without_post_or_parent"].append(cid)
    problems["missing_label"] = sorted(ids - seen)
    return {k: v for k, v in problems.items() if v}


def relation(x):
    """topic_relation, with unrelated split: 'related' continues the subject of the post / an ancestor."""
    rel = x.get("topic_relation", "missing")
    return "related" if rel == "unrelated" and x.get("evidence_ids") else rel


def read_labels(path):
    lines = [l for l in Path(path).read_text().splitlines() if l and not l.startswith("#")]
    rows = {}
    for r in csv.DictReader(lines, delimiter="\t"):
        r["evidence_ids"] = [e for e in r.get("evidence_ids", "").split(",") if e]
        rows[r["comment_id"]] = r
    return rows


def compare(labels, gold_path):
    gold = read_labels(gold_path)
    got = {str(x["id"]): x for x in labels}
    confusion = collections.Counter()
    diffs = []
    aspect_ok = aspect_n = 0
    for cid, g in gold.items():
        m = got.get(cid, {})
        confusion[(relation(g), relation(m))] += 1
        on = ("direct", "contextual")
        if g["topic_relation"] in on and m.get("topic_relation") in on:
            aspect_n += 1
            aspect_ok += g["aspect"] == m.get("aspect")
        if relation(g) != relation(m) or (g["topic_relation"] in on and g["aspect"] != m.get("aspect")):
            diffs.append((cid, g, m))
    return gold, confusion, (aspect_ok, aspect_n), diffs


def thread_comments(rows):
    """Comments as the model and the labelling sheet see them: anonymised, parent marked if missing."""
    ids = {r["comment_id"] for r in rows}
    alias = {}
    comments = []
    for r in rows:
        a, p = r["author_key"], r["parent_comment_id"]
        name = alias.setdefault(a, f"u{len(alias) + 1}") if a else "anon"
        comments.append({"id": str(r["comment_id"]),
                         "reply_to": "post" if not p else str(p) if p in ids else f"missing:{p}",
                         "author": name, "time": str(r["ts"])[11:16],
                         "text": " ".join((r["text"] or "").split()) + (" [media]" if r["has_media"] else "")})
    return comments


SHEET_FIELDS = ("topic_relation", "mention", "subject", "evidence_ids", "aspect", "claim", "stance",
                "borderline", "note")


def sheet(db_path, link, out_path):
    """Blank sheet for a human annotator: thread text only, nothing predicted."""
    _, _, post, rows = load_thread(db_path, link)
    link_of = {str(r["comment_id"]): r["link"] for r in rows}
    with open(out_path, "w", newline="") as f:
        f.write(f"# Labelling sheet for {link}. Rules: pulse_label_instructions.md. No model output here.\n")
        f.write("# post: " + " ".join(post.split()) + "\n")
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(("comment_id", "link", "reply_to", "author", "text") + SHEET_FIELDS)
        for c in thread_comments(rows):
            w.writerow((c["id"], link_of[c["id"]], c["reply_to"], c["author"], c["text"]) + ("",) * len(SHEET_FIELDS))
    print(f"{out_path}: {len(rows)} rows")


def main(db_path, det_dir, link, topic, out_dir, model="deepseek/deepseek-v4-flash", gold_path=None):
    sid, pid, post, rows = load_thread(db_path, link)
    entities = thread_entities(det_dir, sid, pid)
    comments = thread_comments(rows)
    prompt = PROMPT.format(topic=topic, entities=json.dumps(entities, ensure_ascii=False))
    payload = {"post": {"id": "post", "text": post}, "comments": comments}
    meta = {"prompt_version": PROMPT_VERSION, "prompt_sha256": sha(prompt), "input_sha256": sha(payload),
            "model": model}
    out = Path(out_dir)
    if os.environ.get("PULSE_REUSE"):  # re-check a saved response without paying again
        saved = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
        if {k: saved.get(k) for k in meta} != meta:  # the four identity fields only
            raise SystemExit(f"PULSE_REUSE refused: saved {saved or 'no meta.json'} != current {meta}; "
                             "a changed prompt or input needs a new call")
        body = json.loads((out / "request.json").read_text())
        resp = json.loads((out / "response.json").read_text())
        seconds = f"повтор без вызова; исходный вызов {saved.get('seconds')}"
        meta["seconds"] = saved.get("seconds")
    else:
        body, resp, seconds = call(model, prompt, payload)
        meta["seconds"] = seconds
    content = resp["choices"][0]["message"]["content"]
    labels = json.loads(content[content.find("{"):content.rfind("}") + 1])["labels"]
    usage = resp.get("usage", {})
    problems = check(labels, rows, entities)

    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    (out / "request.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
    (out / "response.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1))
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1))

    link_of = {str(r["comment_id"]): r["link"] for r in rows}
    text_of = {c["id"]: c["text"] for c in comments}
    rep = [f"# Контекстная классификация треда {link}", "",
           f"Промпт `{PROMPT_VERSION}` (sha {meta['prompt_sha256']}), вход sha {meta['input_sha256']}.",
           f"Модель `{resp.get('model', model)}`, один вызов, {seconds} с. Токены: вход "
           f"{usage.get('prompt_tokens')}, выход {usage.get('completion_tokens')}. Стоимость: "
           f"${usage.get('cost')} ({len(rows)} реплик, ${(usage.get('cost') or 0) / max(len(rows), 1):.6f} за реплику).",
           "", f"Сущности треда, из которых выбирала модель: {', '.join(entities)} + other/unknown.", "",
           "## Структурные проверки", ""]
    rep += [f"- {k}: {v}" for k, v in problems.items()] or ["- нарушений нет"]
    if gold_path:
        gold, confusion, (aok, an), diffs = compare(labels, gold_path)
        agree = sum(n for (g, m), n in confusion.items() if g == m)
        cols = (*RELATIONS[:2], "related", *RELATIONS[2:])
        rep += ["", f"## Сравнение с разметкой `{gold_path}`", "",
                "related = unrelated, продолжающий тему поста или предка (evidence_ids не пусто).", "",
                f"Отношение к теме совпало: {agree}/{len(gold)}. aspect совпал на {aok}/{an} репликах, "
                f"которые обе стороны считают относящимися к теме.", "",
                "| разметка \\ модель | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
        for g in cols:
            rep.append(f"| {g} | " + " | ".join(str(confusion[(g, m)]) for m in cols) + " |")
        rep += ["", "### Расхождения", ""]
        for cid, g, m in diffs:
            rep.append(f"- [{cid}]({link_of[cid]}) разметка {relation(g)}/{g['aspect'] or '-'}"
                       f"{' (спорная)' if g['borderline'] == '1' else ''} — модель "
                       f"{relation(m)}/{m.get('aspect')}, evidence {m.get('evidence_ids')}\n"
                       f"  > {text_of[cid][:200]}\n  модель: {m.get('subject')} · {m.get('claim')}"
                       f" · разметка: {g['subject']} · {g['note']}")
    rep += ["", "## Все метки модели", "",
            "| id | relation | mention | subject | aspect | claim | stance | evidence | текст |",
            "|---|---|---|---|---|---|---|---|---|"]
    for x in labels:
        cid = str(x.get("id"))
        rep.append(f"| [{cid}]({link_of.get(cid, '')}) | {relation(x)} | {x.get('mention') or ''} | "
                   f"{x.get('subject') or ''} | {x.get('aspect') or ''} | {x.get('claim') or ''} | "
                   f"{x.get('stance')} | {','.join(map(str, x.get('evidence_ids') or []))} | "
                   f"{text_of.get(cid, '')[:120].replace('|', '/')} |")
    (out / "report.md").write_text("\n".join(rep) + "\n")
    print("\n".join(rep[:8]))


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet(*sys.argv[2:])
    else:
        main(*sys.argv[1:])
