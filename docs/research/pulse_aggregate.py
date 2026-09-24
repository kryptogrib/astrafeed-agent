"""Research Pulse, step 4: count sources behind each argument across several threads.

python3 docs/research/pulse_aggregate.py astrafeed.db artifacts/pulse-zec [arguments-v2.json]

Reads <dir>/arguments.json (agent grouping: argument -> "thread/comment" ids) and the published sets
<dir>/thread-<id>/v3/demo/published.json. Every id must be in a published set (held and excluded replies
cannot be cited). For each argument counts comments, distinct authors, threads and channels from the
database (opened read-only). Published replies not assigned to any argument are listed, not dropped.
Writes <dir>/aggregate.json. No LLM call.

An optional grouping file in the v2 format (topics -> typed units, see arguments-v2.json) writes
aggregate-v2.json instead: the same counts per unit, plus per-type counts inside each topic. A unit type
says what the replies are (argument, question, experience...); repeating a topic is not repeating an
argument, and neither count says the sources are independent.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pulse_classify_thread import load_thread  # noqa: E402


def aggregate(db_path, pulse_dir, groups, keep=None):
    """Counts for a grouping dict (v1 or v2). keep(id, ts) narrows the published sets, e.g. to a time
    window; units left empty are dropped. Every reply carries its comment time, res["window"] is the
    time span of the published replies that were kept."""
    d = Path(pulse_dir)
    groups = dict(groups)
    v2 = "topics" in groups
    if v2:  # v2: topics -> typed units; mapped onto the v1 shape, the type is kept on each unit
        groups["subjects"] = [{"subject": t["topic"], "arguments": t["units"]} for t in groups["topics"]]
    pub, author, threads, ts_of = {}, {}, {}, {}
    for p in sorted(d.glob("thread-*/v3/demo/published.json")):
        t = p.parts[-4].removeprefix("thread-")
        data = json.loads(p.read_text())
        _, _, _, rows = load_thread(db_path, data["link"])
        author.update({f"{t}/{r['comment_id']}": r["author_key"] for r in rows})
        ts_of.update({f"{t}/{r['comment_id']}": r["ts"] for r in rows})
        held = [str(x["id"]) for x in data["held_for_review"]["labels"]]
        inside = [r for r in rows if keep is None or keep(f"{t}/{r['comment_id']}", r["ts"])]
        ids = {str(r["comment_id"]) for r in inside}
        threads[t] = {"link": data["link"], "channel": data["link"].split("/")[-2], "comments": len(inside),
                      "participants": len({r["author_key"] for r in inside if r["author_key"]}),
                      "published": sum(str(x["id"]) in ids for x in data["published"]),
                      "held": sum(i in ids for i in held),
                      "first": min((r["ts"] for r in rows), default=None),
                      "last": max((r["ts"] for r in rows), default=None),
                      "first_kept": min((r["ts"] for r in inside), default=None),
                      "last_kept": max((r["ts"] for r in inside), default=None)}
        pub.update({f"{t}/{x['id']}": dict(x, ts=ts_of[f"{t}/{x['id']}"]) for x in data["published"]
                    if str(x["id"]) in ids})
    every = {i for s in groups["subjects"] for a in s["arguments"] for i in a["ids"]}
    known = set(ts_of)
    if keep is None:
        missing = sorted(every - set(pub))
    else:  # an id outside the window is fine, an id that is not published anywhere is not
        missing = sorted(i for i in every if i not in pub and (i not in known or keep(i, ts_of[i])))
    if missing:
        raise SystemExit(f"not in any published set: {missing}")

    used, out = set(), []
    for s in groups["subjects"]:
        for a in s["arguments"]:
            ids = [i for i in a["ids"] if i in pub]
            if not ids:
                continue
            used.update(ids)
            ts = sorted({i.split("/")[0] for i in ids})
            out.append(dict(a, ids=ids, subject=s["subject"], comments=len(ids),
                            authors=len({author[i] for i in ids}),
                            threads=len(ts), channels=len({threads[t]["channel"] for t in ts}),
                            links=[pub[i]["link"] for i in ids], ts=[pub[i]["ts"] for i in ids]))
    unassigned = sorted(set(pub) - used)
    if len(used) != sum(a["comments"] for a in out):
        # a demo constraint, not a rule: each reply is counted under its main type only
        raise SystemExit("a reply is assigned to more than one unit (demo: one main type per reply)")
    res = {"grouping": groups["grouping"], "threads": threads, "arguments": out,
           "window": [min((x["ts"] for x in pub.values()), default=None),
                      max((x["ts"] for x in pub.values()), default=None)],
           "unassigned_published": [{"id": i, "summary": pub[i].get("summary"), "link": pub[i]["link"]}
                                    for i in unassigned]}
    if v2:
        res["units"] = res.pop("arguments")
        res["topics"] = []
        for s in groups["subjects"]:
            us = [a for a in out if a["subject"] == s["subject"]]
            if not us:
                continue
            ids = [i for a in us for i in a["ids"]]
            by_type = {}
            for a in us:
                by_type.setdefault(a["type"], []).extend(a["ids"])
            res["topics"].append({"topic": s["subject"], "comments": len(ids), "authors": len({author[i] for i in ids}),
                                  "threads": len({i.split("/")[0] for i in ids}),
                                  "by_type": {k: {"comments": len(v), "authors": len({author[i] for i in v})}
                                              for k, v in by_type.items()}})
    if groups.get("observations"):
        res["observations"] = observations(groups, out, author, threads)
    return res


def observations(groups, out, author, threads, max_links=5):
    """Short answer: agent statements over named units. The text must carry no digits, every number and
    link is counted here from the units that are left (e.g. inside a window); a statement with none left
    is dropped."""
    keys = {a["key"] for s in groups["subjects"] for a in s["arguments"]}
    by_key = {a["key"]: a for a in out}
    res = []
    for o in groups["observations"]["items"]:
        if any(c.isdigit() for c in o["text"]):
            raise SystemExit(f"observation {o['key']}: numbers come from the code, not the text")
        if bad := [k for k in o["units"] if k not in keys]:
            raise SystemExit(f"observation {o['key']}: unknown units {bad}")
        us = [by_key[k] for k in o["units"] if k in by_key]
        if not us:
            continue
        ids = [i for u in us for i in u["ids"]]
        links = [(i, u["links"][u["ids"].index(i)]) for u in us for i in u["ids"]]
        ts = sorted({i.split("/")[0] for i in ids})
        res.append({"key": o["key"], "text": o["text"], "units": [u["key"] for u in us],
                    "units_total": len(o["units"]), "comments": len(ids),
                    "authors": len({author[i] for i in ids}), "threads": len(ts),
                    "channels": len({threads[t]["channel"] for t in ts}),
                    "links": [{"id": i, "link": l} for i, l in links[:max_links]],
                    "more_links": max(0, len(links) - max_links)})
    return res


def main(db_path, pulse_dir, grouping="arguments.json"):
    d = Path(pulse_dir)
    res = aggregate(db_path, d, json.loads((d / grouping).read_text()))
    v2 = "topics" in res
    out, unassigned = res["units" if v2 else "arguments"], res["unassigned_published"]
    name = "aggregate-v2.json" if v2 else "aggregate.json"
    (d / name).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    for a in out:
        print(f"{a.get('type', ''):14} {a['key']:22} c={a['comments']} a={a['authors']} t={a['threads']} ch={a['channels']}")
    for t in res.get("topics", []):
        print(f"# {t['topic']}: c={t['comments']} a={t['authors']} t={t['threads']}",
              {k: (v["comments"], v["authors"]) for k, v in t["by_type"].items()})
    print("unassigned:", len(unassigned))
    for u in unassigned:
        print(" ", u["id"], u["summary"])


if __name__ == "__main__":
    main(*sys.argv[1:])
