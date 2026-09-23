"""Research Pulse, step 2: relevance and a faithful retelling of every reply of ONE thread, one LLM call.

    python3 docs/research/pulse_classify_thread.py astrafeed.db artifacts/entity-candidates \
        https://t.me/rawa_imagination/21055 ethereum,eth,ether artifacts/pulse-eth/thread-21055/v3 \
        [model] [labels.tsv]
    python3 docs/research/pulse_classify_thread.py sheet astrafeed.db artifacts/entity-candidates \
        ethereum,eth,ether out.tsv <post link> <id,id,...> [<post link> <id,id,...>]

Contract v3 (docs/research/pulse_label_instructions.md). The model does not decide which words name
the topic: mentions come from entity_candidates.py (detections.jsonl) and are passed in with their
status. The model returns relevance, aspect, kind, a short retelling, an exact quote and the messages
needed to understand the reply. Checks run after the call and only flag, never exclude.

`sheet` writes a blank sheet for a person: the replies, their reply chain and detected mentions,
no model output.

Writes meta.json, request.json, response.json, labels.json, report.md. meta.json holds the prompt
version, hashes of the prompt and the input, the model and the pinned provider; PULSE_REUSE=1
re-checks a saved response and refuses when any of them differs. PULSE_PROVIDER pins one OpenRouter
provider without fallbacks, so that two threads are priced by the same provider.
Contract v2 lives in pulse_classify_thread_v2.py.
Database is opened read-only. The API key is read from OPENROUTER_API_KEY or .env. Stdlib only.
"""

import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request

RELEVANCE = ("relevant", "unrelated", "unclear")
ASPECTS = ("market", "usage", "technology", "other")
KINDS = ("opinion", "question", "experience", "other")
SKIP_RULES = {"hashtag"}  # labels of the post, not things people talk about
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

PROMPT_VERSION = "v3-relevance-summary"
PROMPT = """You read one Telegram discussion thread. Topic: {topic}.

`mentions` on the post or on a comment lists words that a separate detector found as names of the
topic, with status confirmed or ambiguous ("эфир" may also mean a broadcast). Do not decide yourself
which words name the topic; judge whether each reply is about it.

For EVERY comment return one object:
  id           the comment id
  relevance    relevant   the reply is about {topic}: it names it (see mentions) or continues, through
                          its reply chain or the post, a message about {topic}
               unrelated  another subject, including other coins and the market in general
               unclear    cannot tell: the only link is a nearby message outside the reply chain,
                          the parent is missing, or the meaning is in an image you cannot see
  aspect       only if relevant, else null:
               market      the price, trading and outlook of {topic} itself
               usage       {topic} used as a currency, means of payment or balance: a price of
                           something named in {topic}, mint cost, gas, {topic} on a wallet
               technology  the network, upgrades, L2
               other
  kind         opinion / question / experience (the author's own fact or action) / other
  summary      only if relevant, else null: one short sentence in Russian retelling THIS reply.
               Keep its kind: a question stays a question ("Спрашивает, …"), an experience stays a fact.
               The parent may be used to resolve "это" / "он", but add no numbers, levels or arguments
               the reply itself does not state. Sarcasm: say it is ironic, do not retell it literally.
               If a retelling needs a guess, null.
  quote        only if relevant, else null: an exact fragment of the reply's own text, copied
               character for character, on which the summary rests
  context_ids  "post" and/or ids from the reply chain (parent, grandparent, ...) needed to understand
               the reply; [] if it is clear alone. Never a message that is only nearby in time.
  name_candidate  a word in the reply that you think names {topic} but is not in its mentions;
               null otherwise. It is stored only as a candidate for review.

Do not assume a reply is about {topic} because the post is; follow the reply chain. A reply to an
off-topic message may return to {topic}: judge its own text too.
"[media]" marks an image you cannot see: unclear only when the meaning cannot be understood without it.
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


def topic_mentions(det_dir, sid, pid, names):
    """Mentions of the topic found by entity_candidates.py: {"post" | comment id: [{text, status}]}.
    A surface seen both confirmed and ambiguous keeps confirmed."""
    found = collections.defaultdict(dict)
    for line in open(Path(det_dir) / "detections.jsonl"):
        d = json.loads(line)
        if ((d["source_id"], str(d["post_id"])) != (sid, pid) or d["candidate"] not in names
                or d["status"] not in ("confirmed", "ambiguous")):
            continue
        if set(d["rules"]) <= SKIP_RULES or d["rules"] == ["phrase_head"]:
            continue
        key = "post" if d["kind"] == "post" else str(d["comment_id"])
        if found[key].get(d["surface"]) != "confirmed":
            found[key][d["surface"]] = d["status"]
    return {k: [{"text": s, "status": st} for s, st in sorted(v.items())] for k, v in found.items()}


def call(model, prompt, payload, provider=None):
    body = {"model": model, "temperature": 0,
            "response_format": {"type": "json_object"},
            "usage": {"include": True}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": False}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    return body, resp, round(time.time() - t0, 1)


def numbers(text):
    return {n.replace(",", ".") for n in NUMBER.findall(text or "")}


def check(labels, comments, mentions, post):
    """Structural checks that do not need a gold file. Each one is a flag for review."""
    by_id = {c["id"]: c for c in comments}
    parent = {c["id"]: c["reply_to"] for c in comments}

    def ancestors(cid):
        out, cur = {"post"}, parent.get(cid)
        while cur in parent:
            out.add(cur)
            cur = parent[cur]
        return out

    relevant = {str(x.get("id")) for x in labels if x.get("relevance") == "relevant"}
    problems = collections.defaultdict(list)
    seen = set()
    for x in labels:
        cid = str(x.get("id"))
        seen.add(cid)
        if cid not in by_id:
            problems["unknown_id"].append(cid)
            continue
        rel, text = x.get("relevance"), by_id[cid]["text"]
        for f, allowed in (("relevance", RELEVANCE), ("kind", KINDS),
                           ("aspect", ASPECTS if rel == "relevant" else (None,))):
            if x.get(f) not in allowed:
                problems[f"bad_{f}"].append(f"{cid}:{x.get(f)}")
        if rel != "relevant" and (x.get("summary") or x.get("quote")):
            problems["summary_on_not_relevant"].append(cid)
        ctx = {str(e) for e in x.get("context_ids") or []}
        if ctx - ancestors(cid):
            problems["context_not_in_chain"].append(f"{cid}:{','.join(sorted(ctx - ancestors(cid)))}")
        quote = x.get("quote")
        if rel == "relevant" and not quote:
            problems["relevant_without_quote"].append(cid)
        if quote and " ".join(quote.split()) not in text:
            problems["quote_not_in_text"].append(cid)
        if x.get("summary"):
            source = text + " " + " ".join(post if c == "post" else by_id[c]["text"]
                                           for c in ctx if c == "post" or c in by_id)
            extra = numbers(x["summary"]) - numbers(source)
            if extra:
                problems["summary_number_not_in_source"].append(f"{cid}:{','.join(sorted(extra))}")
        if rel == "relevant" and cid not in mentions and not ctx:
            problems["relevant_without_mention_or_context"].append(cid)
        cand = x.get("name_candidate")
        if cand and cand.casefold() not in text.casefold():
            problems["name_candidate_not_in_text"].append(f"{cid}:{cand}")
    # relevant only through context: following context_ids must reach a message where the detector
    # found the topic. A context that is relevant only in the model's own opinion does not count,
    # otherwise one ungrounded reply makes its whole branch relevant.
    ctx_of = {str(x.get("id")): {str(e) for e in x.get("context_ids") or []} for x in labels}
    grounded = set(mentions)
    changed = True
    while changed:
        changed = False
        for cid in relevant - grounded:
            if ctx_of.get(cid, set()) & grounded:
                grounded.add(cid)
                changed = True
    problems["relevant_not_grounded"] = sorted(relevant - grounded, key=int)
    problems["missing_label"] = sorted(set(by_id) - seen)
    return {k: v for k, v in problems.items() if v}


def read_labels(path):
    lines = [l for l in Path(path).read_text().splitlines() if l and not l.startswith("#")]
    return {r["comment_id"]: r for r in csv.DictReader(lines, delimiter="\t")}


def compare(labels, gold_path):
    gold = read_labels(gold_path)
    got = {str(x["id"]): x for x in labels}
    confusion = collections.Counter()
    diffs = []
    aspect_ok = aspect_n = 0
    for cid, g in gold.items():
        m = got.get(cid, {})
        confusion[(g["relevance"], m.get("relevance", "missing"))] += 1
        both = g["relevance"] == m.get("relevance") == "relevant"
        if both:
            aspect_n += 1
            aspect_ok += g["aspect"] == m.get("aspect")
        if g["relevance"] != m.get("relevance") or (both and g["aspect"] != m.get("aspect")):
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


def show_mentions(ms):
    return ", ".join(f"{m['text']} ({m['status']})" for m in ms or [])


SHEET_FIELDS = ("relevance", "aspect", "kind", "summary", "quote", "context_ids", "borderline", "note")


def sheet(db_path, det_dir, topic, out_path, *pairs):
    """Blank sheet for a person: selected replies with their reply chain, nothing predicted."""
    names = tuple(topic.split(","))
    head, rows_out = [], []
    for link, ids in zip(pairs[::2], pairs[1::2]):
        sid, pid, post, rows = load_thread(db_path, link)
        mentions = topic_mentions(det_dir, sid, pid, names)
        head.append(f"# post {link} [mentions: {show_mentions(mentions.get('post')) or 'none'}]: "
                    + " ".join(post.split()))
        comments = {c["id"]: c for c in thread_comments(rows)}
        link_of = {str(r["comment_id"]): r["link"] for r in rows}
        for cid in ids.split(","):
            c, chain, cur = comments[cid], [], comments[cid]["reply_to"]
            while cur in comments and len(chain) < 2:  # parent and grandparent
                chain.append(f"[{cur}] {comments[cur]['text'][:200]}")
                cur = comments[cur]["reply_to"]
            if cur == "post" or cur.startswith("missing:"):
                chain.append(f"[{cur}]")
            rows_out.append((link.rsplit("/", 1)[1], cid, link_of[cid], c["reply_to"], " ← ".join(chain),
                             c["author"], c["text"], show_mentions(mentions.get(cid))))
    with open(out_path, "w", newline="") as f:
        f.write("# Labelling sheet, contract v3. Rules: docs/research/pulse_label_instructions.md."
                " No model output here; `mentions` comes from the entity detector and may be wrong.\n")
        f.write("\n".join(head) + "\n")
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(("thread", "comment_id", "link", "reply_to", "chain", "author", "text", "mentions")
                   + SHEET_FIELDS)
        for r in rows_out:
            w.writerow(r + ("",) * len(SHEET_FIELDS))
    print(f"{out_path}: {len(rows_out)} rows")


def main(db_path, det_dir, link, topic, out_dir, model="deepseek/deepseek-v4-flash", gold_path=None):
    names = tuple(topic.split(","))
    sid, pid, post, rows = load_thread(db_path, link)
    mentions = topic_mentions(det_dir, sid, pid, names)
    comments = thread_comments(rows)
    prompt = PROMPT.format(topic=names[0])
    payload = {"post": {"id": "post", "text": post, **({"mentions": mentions["post"]} if "post" in mentions else {})},
               "comments": [dict(c, mentions=mentions[c["id"]]) if c["id"] in mentions else c
                            for c in comments]}
    provider = os.environ.get("PULSE_PROVIDER")
    meta = {"prompt_version": PROMPT_VERSION, "prompt_sha256": sha(prompt), "input_sha256": sha(payload),
            "model": model, "provider_pinned": provider}
    out = Path(out_dir)
    if os.environ.get("PULSE_REUSE"):  # re-check a saved response without paying again
        saved = json.loads((out / "meta.json").read_text()) if (out / "meta.json").exists() else {}
        if {k: saved.get(k) for k in meta} != meta:  # identity fields only
            raise SystemExit(f"PULSE_REUSE refused: saved {saved or 'no meta.json'} != current {meta}; "
                             "a changed prompt, input, model or provider needs a new call")
        body = json.loads((out / "request.json").read_text())
        resp = json.loads((out / "response.json").read_text())
        seconds = f"повтор без вызова; исходный вызов {saved.get('seconds')}"
        meta["seconds"] = saved.get("seconds")
    else:
        body, resp, seconds = call(model, prompt, payload, provider)
        meta["seconds"] = seconds
    meta["provider_actual"] = resp.get("provider")
    choice = resp["choices"][0]
    content = choice["message"]["content"]
    labels = json.loads(content[content.find("{"):content.rfind("}") + 1])["labels"]
    usage = resp.get("usage", {})
    problems = check(labels, comments, mentions, post)

    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    (out / "request.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
    (out / "response.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1))
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=1))

    link_of = {str(r["comment_id"]): r["link"] for r in rows}
    text_of = {c["id"]: c["text"] for c in comments}
    rel_count = collections.Counter(x.get("relevance") for x in labels)
    aspect_count = collections.Counter(x.get("aspect") for x in labels if x.get("relevance") == "relevant")
    kind_count = collections.Counter(x.get("kind") for x in labels if x.get("relevance") == "relevant")
    cost, pt, ct = usage.get("cost") or 0, usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
    candidates = [(str(x["id"]), x["name_candidate"]) for x in labels if x.get("name_candidate")]
    rep = [f"# Релевантность и пересказ: тред {link}", "",
           f"Контракт `{PROMPT_VERSION}` (sha промпта {meta['prompt_sha256']}), вход sha {meta['input_sha256']}.",
           f"Модель `{resp.get('model', model)}`, провайдер {resp.get('provider')} (закреплён: {provider or 'нет'}), "
           f"finish_reason {choice.get('finish_reason')}, один вызов, {seconds} с.",
           f"Токены: вход {pt}, выход {ct}. Стоимость ${cost} ({len(rows)} реплик, "
           f"${cost / max(len(rows), 1):.6f} за реплику; ${cost / max(pt + ct, 1) * 1e6:.3f} за 1M токенов).", "",
           f"Упоминания темы от детектора: пост — {show_mentions(mentions.get('post')) or 'нет'}; "
           f"комментариев с упоминанием {sum(k != 'post' for k in mentions)}.", "",
           f"relevance: {dict(rel_count)}. У relevant aspect: {dict(aspect_count)}, kind: {dict(kind_count)}.", "",
           "## Структурные проверки (флаги, не исключения)", ""]
    rep += [f"- {k}: {v}" for k, v in problems.items()] or ["- нарушений нет"]
    rep += ["", "## Кандидаты в названия темы от модели (не подтверждены)", ""]
    rep += [f"- [{cid}]({link_of.get(cid, '')}) «{c}»: {text_of.get(cid, '')[:120]}"
            for cid, c in candidates] or ["- нет"]
    if gold_path:
        gold, confusion, (aok, an), diffs = compare(labels, gold_path)
        agree = sum(n for (g, m), n in confusion.items() if g == m)
        off_topic = [cid for cid, g in gold.items() if g["relevance"] == "unrelated"
                     and cid in {str(x["id"]) for x in labels if x.get("relevance") == "relevant"}]
        rep += ["", f"## Сравнение с разметкой `{gold_path}`", "",
                f"relevance совпала: {agree}/{len(gold)}. aspect совпал на {aok}/{an} репликах, "
                f"которые обе стороны считают relevant. Офтоп в выборке модели (relevant у модели, "
                f"unrelated в разметке): {len(off_topic)} {off_topic}.", "",
                "| разметка \\ модель | " + " | ".join(RELEVANCE) + " |", "|---|" + "---:|" * len(RELEVANCE)]
        for g in RELEVANCE:
            rep.append(f"| {g} | " + " | ".join(str(confusion[(g, m)]) for m in RELEVANCE) + " |")
        rep += ["", "### Расхождения", ""]
        for cid, g, m in diffs:
            rep.append(f"- [{cid}]({link_of[cid]}) разметка {g['relevance']}/{g.get('aspect') or '-'}"
                       f"{' (спорная)' if g.get('borderline') == '1' else ''} — модель "
                       f"{m.get('relevance')}/{m.get('aspect') or '-'}, context {m.get('context_ids')}\n"
                       f"  > {text_of[cid][:200]}\n"
                       f"  модель: {m.get('summary') or '—'} · разметка: {g.get('note') or '—'}")
    rep += ["", "## Все метки модели", "",
            "| id | relevance | aspect | kind | упоминания | summary | quote | context | текст |",
            "|---|---|---|---|---|---|---|---|---|"]
    for x in labels:
        cid = str(x.get("id"))
        cell = lambda s: (s or "").replace("|", "/")
        rep.append(f"| [{cid}]({link_of.get(cid, '')}) | {x.get('relevance')} | {x.get('aspect') or ''} | "
                   f"{x.get('kind')} | {show_mentions(mentions.get(cid))} | {cell(x.get('summary'))} | "
                   f"{cell(x.get('quote'))} | {','.join(map(str, x.get('context_ids') or []))} | "
                   f"{cell(text_of.get(cid, '')[:120])} |")
    (out / "report.md").write_text("\n".join(rep) + "\n")
    print("\n".join(rep[:16]))


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet(*sys.argv[2:])
    else:
        main(*sys.argv[1:])
