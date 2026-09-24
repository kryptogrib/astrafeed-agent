"""First-pass entity candidates without LLM: posts first, comments second.

Run from repository root:
    python3 docs/research/entity_candidates.py astrafeed.db artifacts/entity-candidates \
        [docs/research/entity_aliases.tsv]

Reads SQLite read-only in one snapshot, stdlib only, no model calls. Writes
candidates.json (full), candidates.md (review table) and detections.jsonl (one
line per mention: document, exact fragment, candidate, rule, status).

Output is a list of CANDIDATES with evidence, not confirmed entities:
- every candidate is kept; MIN_DOCS only decides whether it enters the ranking;
- repeated lines are template CANDIDATES: mentions there are kept and counted
  separately, never dropped;
- the alias registry links spellings of already-found candidates; new candidates
  are discovered without it. Ambiguous registry rows ("эфир") are never merged;
- alias pairs are proposals; thread context is a review pool, not a mention.
"""

import collections
import csv
import difflib
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata

# Cyrillic letters that look like Latin ones ("Cryptо Headlines" with Cyrillic о).
HOMOGLYPHS = str.maketrans("аеорсухкмтвнАЕОРСУХКМТВН", "aeopcyxkmtbhAEOPCYXKMTBH")
LATIN = re.compile(r"[A-Za-z]")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

URL = re.compile(r"https?://\S+|\b(?:t\.me|x\.com)/\S+")
HANDLE = re.compile(r"@\w+")
# On-chain identifiers: EVM 0x…, base58 Solana-style (32-44 chars, has a digit and a lowercase letter).
ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b|\b(?=[1-9A-HJ-NP-Za-km-z]*\d)(?=[1-9A-HJ-NP-Za-km-z]*[a-z])[1-9A-HJ-NP-Za-km-z]{32,44}\b")

CASHTAG = re.compile(r"(?<!\w)\$([A-Za-z][A-Za-z0-9]{1,14})(?!\w)")
HASHTAG = re.compile(r"(?<!\w)#(\w{2,40})")
UPPER = re.compile(r"(?<![\w$#])([A-Z][A-Z0-9]{1,9})(?![\w])")
# Capitalised word not preceded by sentence boundary; Latin or Cyrillic, CamelCase allowed.
TITLE = re.compile(r"(?<=[\w,:;)\-–—»\"] )([A-ZА-ЯЁ][a-zа-яё]+(?:[A-Z][a-z]+)*)\b")
CAMEL = re.compile(r"(?<!\w)([A-Z][a-z]+[A-Z][A-Za-z]*|[a-z]+[A-Z][A-Za-z]+)(?!\w)")
BRACKET = re.compile(
    r"(?<![\w$])([A-Z][A-Za-z0-9.\-]{1,30}(?: [A-Z][A-Za-z0-9.\-]{1,30}){0,2})\s*[\[(]\s*\$?([A-Z][A-Z0-9]{1,12})\s*[\])]"
)
PHRASE = re.compile(r"(?<![\w$#])((?:[A-Z][A-Za-z0-9]+|[A-Z]{2,})(?: (?:[A-Z][A-Za-z0-9]+|[A-Z]{2,})){1,2})(?![\w])")
WORD = re.compile(r"\w+")

TEMPLATE_MIN_POSTS = 5    # same line in >= N posts of one channel -> template CANDIDATE line
TEMPLATE_MIN_THREADS = 5  # same long comment in >= N threads -> template CANDIDATE comment
MIN_DOCS = 2              # ranking threshold only: fewer docs -> kept, rank_eligible=false
WINDOW = 60               # chars around an ambiguous registry hit checked for reject/support
WEAK_RULES = {"phrase_head"}  # "Clarity" inside "Clarity Act": stored, not a standalone mention
STRONG_RULES = {"cashtag", "bracket_name", "bracket_symbol", "camel_name", "address", "after_role"}


def fix_homoglyphs(token):
    """Map Cyrillic look-alikes to Latin only inside mostly-Latin tokens."""
    if LATIN.search(token) and CYRILLIC.search(token):
        latin = len(LATIN.findall(token))
        if latin >= len(CYRILLIC.findall(token)):
            return token.translate(HOMOGLYPHS)
    return token


def norm(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def key(surface):
    return norm(fix_homoglyphs(unicodedata.normalize("NFKC", surface)))


def blank(text, pattern):
    """Replace matches with spaces of the same length so character offsets stay valid."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def strip_noise(text):
    return blank(blank(blank(text, URL), HANDLE), ADDRESS)


def snippet(line, start, end, width=70):
    return line[max(0, start - width):end + width]


def load(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")  # one consistent read snapshot
    posts = []
    for r in db.execute("SELECT source_id, external_id, payload FROM raw_item"):
        p = json.loads(r["payload"])
        posts.append({"kind": "post", "source_id": r["source_id"], "post_id": str(r["external_id"]),
                      "text": p.get("text") or "", "link": p.get("link"),
                      "channel": p.get("channel_ref"), "ts": p.get("timestamp")})
    comments = [dict(r, kind="comment", post_id=str(r["post_id"]))
                for r in db.execute("SELECT * FROM comment")]
    db.close()
    return posts, comments


def load_registry(path):
    """Alias registry rows keyed by normalised surface; a missing file means an empty registry."""
    rows = {}
    if not path or not Path(path).exists():
        return rows
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    for r in csv.DictReader(lines, delimiter="\t"):
        cond = dict(part.strip().split("=", 1)
                    for part in (r.get("condition") or "").split("; ") if "=" in part)
        rows[key(r["surface"])] = {
            "surface": r["surface"], "candidate": r["candidate"], "relation": r["relation"],
            "basis": r["basis"], "status": r["status"],
            "reject": re.compile(cond["reject"], re.I) if "reject" in cond else None,
            "support": re.compile(cond["support"], re.I) if "support" in cond else None,
        }
    return rows


def load_exclusions(path):
    """Context exclusions keyed by token: [{rules, context, reason}]. Separate from aliases."""
    rows = collections.defaultdict(list)
    if not path or not Path(path).exists():
        return rows
    lines = [l for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    for r in csv.DictReader(lines, delimiter="\t"):
        w = re.escape(key(r["surface"]))
        rows[key(r["surface"])].append({
            "rules": set(r["rules"].split(",")), "reason": r["reason"],
            "context": re.compile(r["context"].replace("{w}", w), re.I)})
    return rows


def apply_exclusions(d, line, exclusions):
    """Drop weak shape rules in a listed context; a mention left with no rule becomes excluded."""
    for row in exclusions.get(d["candidate"], ()):
        hit = set(d["rules"]) & row["rules"]
        window = line[max(0, d["start"] - WINDOW):d["start"] + len(d["surface"]) + WINDOW]
        if not hit or not row["context"].search(window):
            continue
        d["rules"] = set(d["rules"]) - hit
        d["excluded_rules"] = sorted(hit)
        d["exclusion"] = row["reason"]
        if not d["rules"]:
            d["rules"], d["status"], d["hint"] = hit, "excluded", "exclusion: " + row["reason"]
        return


def template_lines(posts):
    """Lines repeated in many posts of one channel: footers, rubrics, signatures, addresses."""
    per_channel = collections.defaultdict(collections.Counter)
    for p in posts:
        for line in {norm(fix_homoglyphs(x)) for x in p["text"].splitlines() if x.strip()}:
            per_channel[p["source_id"]][line] += 1
    return {sid: {line for line, n in c.items() if n >= TEMPLATE_MIN_POSTS}
            for sid, c in per_channel.items()}


def lowercase_usage(docs):
    """How often each word appears written fully in lowercase: corpus-derived stoplist.

    'THE'/'TO' or 'Деньги' at a line start are common words, 'ETH' is almost never 'eth'.
    """
    lower, total = collections.Counter(), collections.Counter()
    for d in docs:
        body = "\n".join(l for l in strip_noise(d["text"]).splitlines() if not headline_like(l))
        for w in WORD.findall(body):
            k = key(w)
            total[k] += 1
            if w == w.lower():
                lower[k] += 1
    return lower, total


def is_ticker_like(surface, lower, total):
    """A capitalised token is a name candidate unless the corpus uses it as a plain word."""
    k = key(surface)
    return total[k] > 0 and lower[k] / total[k] < 0.2


def headline_like(line):
    """CAPS or Title Case lines make every word look like a name: skip name rules there."""
    letters = [c for c in line if c.isalpha()]
    # Short caps lines are price rows ("💰BTC $76 000"), not headlines.
    if len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        return True
    latin = re.findall(r"[A-Za-z][A-Za-z']+", line)
    return len(latin) >= 5 and sum(w[0].isupper() for w in latin) / len(latin) > 0.6


def bracket_plausible(name, sym):
    """'Zcash (ZEC)', 'Arbitrum [$ARB]' share the first letter; 'Time (UTC)', 'Circle (WSJ)' don't."""
    return key(name)[0] == key(sym)[0]


def extract(line, lower, total, roles):
    """Yield (surface, rule, start) from one line. Offsets refer to the original line."""
    clean = strip_noise(line)
    for m in ADDRESS.finditer(line):
        yield m.group(0), "address", m.start()
    for m in CASHTAG.finditer(clean):
        yield m.group(1), "cashtag", m.start(1)
    for m in HASHTAG.finditer(clean):
        if not m.group(1).isdigit():
            yield m.group(1), "hashtag", m.start(1)
    for m in CAMEL.finditer(clean):
        yield m.group(1), "camel_name", m.start(1)
    for m in BRACKET.finditer(clean):
        if bracket_plausible(m.group(1), m.group(2)):
            yield m.group(1), "bracket_name", m.start(1)
            yield m.group(2), "bracket_symbol", m.start(2)
    if headline_like(clean):
        return
    # "Clarity Act", "DWF Labs": keep the phrase and its head; tail words
    # (Act, Labs, Capital) are not emitted as separate candidates.
    # "CEO Nvidia": a role word heads the phrase, so the entity is the tail.
    masked = clean
    for m in PHRASE.finditer(clean):
        phrase, start = m.group(1), m.start(1)
        words = phrase.split()
        offset = 0
        if words[0] in ("The", "THE", "A", "An"):
            offset = len(words[0]) + 1  # "The Hill" -> head "Hill"; the phrase keeps the article
            words = words[1:]
        if key(words[0]) in roles:
            if len(words) > 1:
                yield " ".join(words[1:]), "after_role", start + offset + len(words[0]) + 1
        elif words[0].isupper() or is_ticker_like(words[0], lower, total):
            yield phrase, "phrase_name", start
            yield words[0], "phrase_head", start + offset
        masked = masked[:start] + " " * len(phrase) + masked[m.end(1):]
    for m in UPPER.finditer(masked):
        if key(m.group(1)) not in roles and is_ticker_like(m.group(1), lower, total):
            yield m.group(1), "caps", m.start(1)
    for m in TITLE.finditer(masked):
        s = m.group(1)
        if len(s) >= 3 and key(s) not in roles and is_ticker_like(s, lower, total):
            yield s, "title_name", m.start(1)


def registry_hits(line, registry, pattern):
    """Whole-word registry hits: (surface, target, status, start, hint). No prefix matching."""
    if pattern is None:
        return
    for m in pattern.finditer(line):
        row = registry[key(m.group(0))]
        s, e = m.start(), m.end()
        window = line[max(0, s - WINDOW):e + WINDOW]
        if row["status"] == "confirmed":
            yield m.group(0), row["candidate"], "confirmed", s, None
            continue
        rej = row["reject"].search(window) if row["reject"] else None
        if rej:
            yield m.group(0), row["candidate"], "rejected", s, "reject: " + rej.group(0)
            continue
        sup = row["support"].search(window) if row["support"] else None
        yield m.group(0), row["candidate"], "ambiguous", s, ("support: " + sup.group(0)) if sup else "no support"


def detect(doc, ctx, template_set, known=None):
    """All mentions in one document, one record per (line, start, candidate) with merged rules."""
    spans = {}
    registry = ctx["registry"]
    for no, line in enumerate(doc["text"].splitlines()):
        in_template = norm(fix_homoglyphs(line)) in template_set
        hits = []
        for s, rule, start in extract(line, ctx["lower"], ctx["total"], ctx["roles"]):
            reg = registry.get(key(s))
            if reg and reg["relation"] == "ru_form" and reg["status"] == "ambiguous":
                continue  # "Эфир" at a line middle: the registry hit below decides its status
            hits.append((s, key(s), rule, "confirmed", start, None))
        hits += [(s, target, "alias_registry", status, start, hint)
                 for s, target, status, start, hint in registry_hits(line, registry, ctx["pattern"])]
        if known:
            clean = strip_noise(line)
            hits += [(m.group(0), key(m.group(0)), "post_dictionary", "confirmed", m.start(), None)
                     for m in WORD.finditer(clean) if key(m.group(0)) in known]
        for s, cand, rule, status, start, hint in hits:
            reg = registry.get(cand)
            if reg and reg["relation"] == "ru_form" and reg["status"] == "confirmed":
                cand = reg["candidate"]  # "Биткоина" found as a title word -> bitcoin
            if len(cand) < 2:
                continue
            if in_template and rule == "hashtag":
                rule = "rubric_hashtag"  # channel rubric "#иран #геополитика": editor's topic label
            span = (no, start, cand)
            if span in spans:
                spans[span]["rules"].add(rule)
                if status == "confirmed":
                    spans[span]["status"], spans[span]["hint"] = status, None
                continue
            spans[span] = {"kind": doc["kind"], "source_id": doc["source_id"], "post_id": doc["post_id"],
                           "comment_id": doc.get("comment_id"), "link": doc["link"],
                           "line": no, "start": start, "surface": s, "candidate": cand,
                           "rules": {rule}, "status": status, "hint": hint,
                           "template_candidate": in_template,
                           "fragment": snippet(line, start, start + len(s))}
    lines = doc["text"].splitlines()
    for d in spans.values():
        if d["status"] == "confirmed":
            apply_exclusions(d, lines[d["line"]], ctx.get("exclusions", {}))
        d["rules"] = sorted(d["rules"])
    return list(spans.values())


def is_mention(d):
    """Confirmed and not only a phrase head. Template-candidate mentions count, flagged apart."""
    return d["status"] == "confirmed" and not set(d["rules"]) <= WEAK_RULES


def main(db_path, out_dir, registry_path="docs/research/entity_aliases.tsv",
         exclusions_path="docs/research/entity_exclusions.tsv"):
    posts, comments = load(db_path)
    registry = load_registry(registry_path)
    forms = sorted((r["surface"] for r in registry.values() if r["relation"] == "ru_form"),
                   key=len, reverse=True)
    lower, total = lowercase_usage(posts + comments)
    ctx = {"registry": registry, "lower": lower, "total": total,
           "exclusions": load_exclusions(exclusions_path),
           "roles": {k for k, r in registry.items() if r["relation"] == "not_entity_head"},
           "pattern": re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, forms)) + r")(?!\w)", re.I)
           if forms else None}
    templates = template_lines(posts)

    detections = []
    for p in posts:
        detections += detect(p, ctx, templates.get(p["source_id"], set()))

    # Repeated long comments: template CANDIDATES. Still scanned; mentions flagged.
    exact = collections.defaultdict(list)
    for c in comments:
        if norm(c["text"]):
            exact[norm(c["text"])].append(c)
    template_comments = set()
    for text, members in exact.items():
        if len(text) >= 100 and len({(m["source_id"], m["post_id"]) for m in members}) >= TEMPLATE_MIN_THREADS:
            template_comments.update(m["comment_key"] for m in members)

    # Posts-first dictionary: comments often write known names in lowercase ("eth", "zec").
    # Only words the corpus rarely uses as plain lowercase words are matched this way.
    post_docs = collections.defaultdict(set)
    for d in detections:
        if is_mention(d):
            post_docs[d["candidate"]].add(d["link"])
    known = {k for k, links in post_docs.items() if len(links) >= MIN_DOCS and " " not in k
             and len(k) >= 3 and total[k] and lower[k] / total[k] < 0.5}
    for cm in comments:
        for d in detect(cm, ctx, set(), known):
            d["template_candidate"] = cm["comment_key"] in template_comments
            detections.append(d)

    rows = aggregate(detections, posts, comments, registry)
    report = {
        "scope": "all rows of a read-only snapshot, posts first; candidates NOT confirmed entities",
        "posts": len(posts), "comments": len(comments),
        "template_candidate_comments": len(template_comments),
        "totals": totals(detections, comments),
        "candidate_count": len(rows),
        "rank_eligible_count": sum(r["rank_eligible"] for r in rows),
        "candidates": rows,
        "template_candidate_lines_by_source": [{"source_id": sid, "lines": sorted(lines)}
                                               for sid, lines in templates.items() if lines],
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidates.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (out / "candidates.md").write_text(render_md(report))
    with open(out / "detections.jsonl", "w") as f:
        for d in detections:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    t = report["totals"]
    print(f"posts={len(posts)} comments={len(comments)} candidates={len(rows)} "
          f"ranked={report['rank_eligible_count']} detections={len(detections)} "
          f"comment_mentions={t['comment_mentions']} comment_candidate_pairs={t['comment_candidate_pairs']} "
          f"comments_with_mention={t['comments_with_mention']} -> {out}")


def totals(detections, comments):
    com = [d for d in detections if d["kind"] == "comment"]
    ok = [d for d in com if is_mention(d)]
    with_mention = {d["link"] for d in ok}
    return {
        "detections": len(detections),
        "by_status": dict(collections.Counter(d["status"] for d in detections)),
        "comment_mentions": len(ok),
        "comment_candidate_pairs": len({(d["link"], d["candidate"]) for d in ok}),
        "comments_with_mention": len(with_mention),
        "comments_with_ambiguous_only": len({d["link"] for d in com if d["status"] == "ambiguous"} - with_mention),
        "comments_nonempty": sum(1 for c in comments if c["text"].strip()),
    }


def aggregate(detections, posts, comments, registry):
    cands = collections.defaultdict(lambda: {
        "surfaces": collections.Counter(), "rules": collections.Counter(),
        "mentions": 0, "mentions_outside_templates": 0, "mentions_ambiguous": 0, "mentions_rejected": 0,
        "mentions_excluded": 0, "excluded_examples": [],
        "posts": {}, "posts_outside_templates": set(), "post_channels": set(),
        "comments": {}, "comment_threads": set(), "ambiguous_examples": [], "rejected_examples": [],
        "first_ts": None})
    post_meta = {p["link"]: p for p in posts}
    for d in detections:
        c = cands[d["candidate"]]
        if d["status"] != "confirmed":
            c["mentions_" + d["status"]] += 1
            ex = c[d["status"] + "_examples"]
            if len(ex) < 3:
                ex.append({"link": d["link"], "fragment": d["fragment"], "hint": d["hint"]})
            continue
        c["surfaces"][d["surface"]] += 1
        c["rules"].update(d["rules"])
        if not is_mention(d):
            continue
        c["mentions"] += 1
        outside = not d["template_candidate"] or "rubric_hashtag" in d["rules"]
        c["mentions_outside_templates"] += outside
        if d["kind"] == "post":
            c["posts"].setdefault(d["link"], d["fragment"])
            c["post_channels"].add(post_meta[d["link"]]["channel"])
            if outside:
                c["posts_outside_templates"].add(d["link"])
            ts = post_meta[d["link"]]["ts"]
            if ts and (c["first_ts"] is None or ts < c["first_ts"]):
                c["first_ts"] = ts
        else:
            c["comments"].setdefault(d["link"], d["fragment"])
            c["comment_threads"].add((d["source_id"], d["post_id"]))

    # Thread context: the POST mentions the candidate; replies are a review pool only.
    by_key = {(p["source_id"], p["post_id"]): p["link"] for p in posts}
    thread_size = collections.Counter(by_key.get((c["source_id"], c["post_id"])) for c in comments)

    related = collections.defaultdict(list)
    for k, r in registry.items():
        if r["relation"] == "asset_symbol":
            related[k].append({"related": r["candidate"], "relation": "asset_symbol"})
            related[r["candidate"]].append({"related": k, "relation": "asset_symbol"})

    live = {k: c for k, c in cands.items() if c["mentions"] or c["mentions_ambiguous"]}
    aliases, rejected_pairs = propose_aliases(live, posts)
    rows = []
    for k, c in live.items():
        ctx = {l: thread_size[l] for l in c["posts"] if thread_size[l]}
        docs_ranked = len(c["posts_outside_templates"]) + len(c["comments"])
        rows.append({
            "candidate": k,
            "rank_eligible": docs_ranked >= MIN_DOCS,
            "surfaces": dict(c["surfaces"].most_common(8)),
            "aliases_proposed": aliases.get(k, []),
            "alias_pairs_filtered": rejected_pairs.get(k, []),
            "related": related.get(k, []),
            "rules": dict(c["rules"]),
            "mentions": c["mentions"], "mentions_outside_templates": c["mentions_outside_templates"],
            "mentions_ambiguous": c["mentions_ambiguous"], "mentions_rejected": c["mentions_rejected"],
            "mentions_excluded": c["mentions_excluded"],
            "docs": len(c["posts"]) + len(c["comments"]), "docs_outside_templates": docs_ranked,
            "posts": len(c["posts"]), "posts_outside_templates": len(c["posts_outside_templates"]),
            "post_channels": len(c["post_channels"]), "first_post_ts": c["first_ts"],
            "comments_direct": len(c["comments"]), "comment_threads_direct": len(c["comment_threads"]),
            "context_threads_NOT_mentions": len(ctx), "context_comments_NOT_mentions": sum(ctx.values()),
            "post_examples": [{"link": l, "text": t} for l, t in list(c["posts"].items())[:3]],
            "comment_examples": [{"link": l, "text": t} for l, t in list(c["comments"].items())[:3]],
            "ambiguous_examples": c["ambiguous_examples"], "rejected_examples": c["rejected_examples"],
            "excluded_examples": c["excluded_examples"],
            "context_thread_links": sorted(ctx, key=lambda l: -ctx[l])[:3],
        })
    # Channel count is prevalence, not correctness: it only orders the ranked view.
    rows.sort(key=lambda r: (not r["rank_eligible"], -r["post_channels"], -r["docs"], -r["mentions"]))
    return rows


def propose_aliases(cands, posts):
    """Merge PROPOSALS with a reason; nothing is merged automatically."""
    props = collections.defaultdict(list)
    rejected = collections.defaultdict(list)

    def add(a, b, reason):
        if a != b and a in cands and b in cands and all(p["alias"] != b for p in props[a]):
            props[a].append({"alias": b, "reason": reason})
            props[b].append({"alias": a, "reason": reason})

    # Bracket pairs from raw post text. Every pair stays an unconfirmed proposal with its source;
    # matching first letters is only a filter, and a filtered pair is reported, not treated as evidence.
    for p in posts:
        for m in BRACKET.finditer(strip_noise(p["text"])):
            a, b = key(m.group(1)), key(m.group(2))
            if bracket_plausible(m.group(1), m.group(2)):
                add(a, b, f"bracket pair (unconfirmed): {p['link']}")
            elif a in cands and all(r["alias"] != b for r in rejected[a]):
                rejected[a].append({"alias": b, "reason": f"bracket, filtered (first letters differ): {p['link']}"})
    for k in cands:
        if " " in k:
            add(k, k.replace(" ", ""), "same letters without space")
            add(k, k.split()[0], "phrase starts with it; may be another entity")
    # Long near-identical spellings: typos, variant names. Proposal only.
    words = sorted(k for k in cands if len(k) >= 5 and k.isalpha())
    for i, a in enumerate(words):
        for b in words[i + 1:]:
            if a[0] != b[0] or abs(len(a) - len(b)) > 1:
                continue
            score = difflib.SequenceMatcher(None, a, b).ratio()
            if score >= 0.9:
                add(a, b, f"spelling similarity {score:.2f}")
    return props, rejected


def render_md(report):
    head = ("| написание | кандидат | возможные алиасы / связи | основания | посты (вне шабл.; каналы) | "
            "комм. прямо | неоднозн. | треды-контекст* | ссылки |\n|---|---|---|---|---:|---:|---:|---:|---|\n")

    def row(r):
        surf = ", ".join(r["surfaces"]) or "—"
        al = [f'? {a["alias"]} ({a["reason"].split(":")[0]})' for a in r["aliases_proposed"][:3]]
        al += [f'↔ {x["related"]} ({x["relation"]})' for x in r["related"]]
        al += [f'– {x["alias"]} (filtered: first letters differ)' for x in r["alias_pairs_filtered"][:1]]
        sig = ", ".join(f"{k}:{v}" for k, v in sorted(r["rules"].items(), key=lambda x: -x[1]))
        links = [f"[p]({e['link']})" for e in r["post_examples"][:2]]
        links += [f"[c]({e['link']})" for e in r["comment_examples"][:1]]
        links += [f"[?]({e['link']})" for e in r["ambiguous_examples"][:1]]
        return (f"| {surf} | **{r['candidate']}** | {'; '.join(al)} | {sig} | "
                f"{r['posts']} ({r['posts_outside_templates']}; {r['post_channels']}) | {r['comments_direct']} | "
                f"{r['mentions_ambiguous']} | {r['context_threads_NOT_mentions']} | {' '.join(links)} |")

    ranked = [r for r in report["candidates"] if r["rank_eligible"]]
    single = [r for r in report["candidates"] if not r["rank_eligible"]]
    single = sorted(single, key=lambda r: r["first_post_ts"] or "", reverse=True)
    single = sorted(single, key=lambda r: not STRONG_RULES & set(r["rules"]))[:40]
    t = report["totals"]
    return (f"# Кандидаты сущностей (без LLM)\n\nПостов {report['posts']}, комментариев {report['comments']}. "
            f"Кандидатов {report['candidate_count']}, в рейтинге (≥{MIN_DOCS} документов вне шаблонов) "
            f"{report['rank_eligible_count']}; остальные сохранены как одиночные.\n\n"
            f"Комментарии: упоминаний {t['comment_mentions']}, пар комментарий–кандидат "
            f"{t['comment_candidate_pairs']}, уникальных комментариев с упоминанием {t['comments_with_mention']} "
            f"из {t['comments_nonempty']} непустых; только с неоднозначным упоминанием — "
            f"{t['comments_with_ambiguous_only']}.\n\n"
            "\\* треды, где пост упоминает кандидата — пул для проверки, НЕ упоминания в ответах. "
            "Число каналов — распространённость, не правильность.\n\n"
            "## Рейтинг (первые 150)\n\n" + head + "\n".join(row(r) for r in ranked[:150])
            + "\n\n## Одиночные кандидаты (40: сильные сигналы и новые сначала)\n\n" + head
            + "\n".join(row(r) for r in single) + "\n")


if __name__ == "__main__":
    main(*(sys.argv[1:5] or ["astrafeed.db", "artifacts/entity-candidates"]))
