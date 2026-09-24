"""Exploratory corpus probe, not a production entity resolver.

Run from repository root: python3 docs/research/entity_probe.py astrafeed.db
Reads SQLite in read-only mode. Writes a JSON report to stdout. No model calls.
"""

import collections
import difflib
import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def lexical_text(text):
    return re.sub(r"https?://\S+|@[\w]+", " ", text)


def words(text):
    return {normalize(w) for w in re.findall(r"\w+", lexical_text(text))}


def main(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")  # one consistent read snapshot
    posts = {
        (r["source_id"], r["external_id"]): json.loads(r["payload"])
        for r in db.execute("SELECT * FROM raw_item")
    }
    comments = [dict(r) for r in db.execute("SELECT * FROM comment")]
    db.close()
    patterns = {
        "cashtag": r"(?<!\w)\$([A-Za-z][A-Za-z0-9]{1,14})(?!\w)",
        "hashtag": r"(?<!\w)#([\w]{2,40})",
    }
    seeds = collections.defaultdict(set)
    variants = collections.defaultdict(collections.Counter)
    for doc in [*posts.values(), *comments]:
        text = lexical_text(doc["text"])
        for kind, pattern in patterns.items():
            for surface in re.findall(pattern, text):
                if re.search("[A-Za-zА-Яа-я]", surface):
                    seeds[normalize(surface)].add(kind)
        for surface in set(re.findall(r"(?<!\w)[A-Za-z][A-Za-z0-9]{2,24}(?!\w)", text)):
            variants[normalize(surface)][surface] += 1
    threads = collections.defaultdict(list)
    groups = collections.defaultdict(list)
    direct = collections.Counter()
    for comment in comments:
        threads[(comment["source_id"], comment["post_id"])].append(comment)
        if normalize(comment["text"]):
            groups[normalize(comment["text"])].append(comment)
        direct.update(words(comment["text"]) & seeds.keys())
    post_mentions = collections.Counter()
    for post in posts.values():
        post_mentions.update(words(post["text"]) & seeds.keys())
    context = collections.Counter()
    thread_mentions = collections.Counter()
    for key, replies in threads.items():
        for name in words(posts.get(key, {}).get("text", "")) & seeds.keys():
            context[name] += len(replies)
            thread_mentions[name] += 1
    # Parentheses/brackets suggest a relation, not necessarily identity.
    relations = collections.defaultdict(list)
    relation_pattern = re.compile(
        r"(?<!\w)([A-Za-z][A-Za-z0-9.-]{1,30})\s*[\[(]\s*\$?([A-Z][A-Z0-9]{1,12})\s*[\])]"
    )
    names = set()
    for post in posts.values():
        text = lexical_text(post["text"])
        for name, symbol in relation_pattern.findall(text):
            if not name.isupper():
                relations[(name, symbol)].append(post["link"])
        names.update(normalize(w) for w in re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b", text) if len(w) >= 5)
    name_pairs = []
    ordered_names = sorted(names)
    for i, left in enumerate(ordered_names):
        for right in ordered_names[i + 1:]:
            if left[0] != right[0] or abs(len(left) - len(right)) > 1:
                continue
            score = difflib.SequenceMatcher(None, left, right).ratio()
            if score >= 0.92:
                name_pairs.append({"left": left, "right": right, "score": score})
    repeats = []
    for text, members in groups.items():
        if len(members) < 2:
            continue
        thread_count = len({(x["source_id"], x["post_id"]) for x in members})
        repeats.append({
            "text": text, "count": len(members), "threads": thread_count,
            "known_authors": len({x["author_key"] for x in members if x["author_key"]}),
            "template_candidate": len(text) >= 100 and thread_count >= 5,
            "links": [x["link"] for x in members],
        })
    # Pair candidates, NEVER automatic merges. Character similarity is not meaning.
    long_texts = [(text, members[0]) for text, members in groups.items() if len(text) >= 60]
    similar = []
    for i, (left, a) in enumerate(long_texts):
        for right, b in long_texts[i + 1:]:
            if min(len(left), len(right)) / max(len(left), len(right)) < 0.8:
                continue
            matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
            if matcher.quick_ratio() < 0.88:
                continue
            score = matcher.ratio()
            if score >= 0.88:
                similar.append({"score": score, "left": left, "right": right,
                                "links": [a["link"], b["link"]]})
    report = {
        "scope": "all rows in local read-only snapshot; no time filter",
        "posts": len(posts), "comments": len(comments), "threads": len(threads),
        "comment_range": [min(x["ts"] for x in comments), max(x["ts"] for x in comments)] if comments else [],
        "nonempty_comments": sum(len(v) for v in groups.values()),
        "distinct_normalized_texts": len(groups),
        "candidate_count": len(seeds),
        "candidates": [{"surface_key": name, "signals": sorted(seeds[name]),
                        "post_mentions": post_mentions[name], "direct_comments": direct[name],
                        "parent_threads": thread_mentions[name],
                        "comments_in_parent_threads_NOT_entity_mentions": context[name]}
                       for name in sorted(seeds, key=lambda n: (-thread_mentions[n], -direct[n], n))],
        "case_variants_NOT_verified_entities": {k: dict(v) for k, v in sorted(variants.items()) if len(v) > 1},
        "bracket_relations_NOT_verified_aliases": [
            {"name": name, "symbol": symbol, "links": links}
            for (name, symbol), links in sorted(relations.items())
        ],
        "similar_name_candidates_NOT_merges": name_pairs,
        "repeated_texts": sorted(repeats, key=lambda r: -r["count"]),
        "similar_comment_candidates": similar,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "astrafeed.db")
