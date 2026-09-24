"""Compare entity detection runs on the hand-checked sample in entity_gold.tsv.

    python3 docs/research/entity_eval.py docs/research/entity_gold.tsv \
        before=<dir with eval_dump.json> after=artifacts/entity-candidates

A run is either an old dump ({"by_link": {link: [candidate]}, "aliases": {a: [b]}})
or a current output dir (detections.jsonl + candidates.json). Per gold row the
state is: confirmed / ambiguous / rejected / absent. Stdlib only.
"""

import collections
import csv
import json
from pathlib import Path
import sys


def load_run(path):
    path = Path(path)
    state = collections.defaultdict(dict)  # link -> candidate -> best status
    aliases = collections.defaultdict(set)
    if (path / "detections.jsonl").exists():
        order = {"confirmed": 4, "ambiguous": 3, "rejected": 2, "excluded": 1}
        for line in open(path / "detections.jsonl"):
            d = json.loads(line)
            if d["status"] == "confirmed" and d["rules"] == ["phrase_head"]:
                continue  # stored, but not a standalone mention
            cur = state[d["link"]].get(d["candidate"])
            if cur is None or order[d["status"]] > order[cur]:
                state[d["link"]][d["candidate"]] = d["status"]
        for r in json.loads((path / "candidates.json").read_text())["candidates"]:
            aliases[r["candidate"]].update(a["alias"] for a in r["aliases_proposed"])
            aliases[r["candidate"]].update(x["related"] for x in r["related"])
    else:
        dump = json.loads((path / "eval_dump.json").read_text())
        for link, cands in dump["by_link"].items():
            for c in cands:
                state[link][c] = "confirmed"
        for a, bs in dump["aliases"].items():
            aliases[a].update(bs)
    return state, aliases


def verdict(row, state, aliases):
    if row["expect"] in ("alias", "no_alias"):
        a, b = row["link"].split("|")
        linked = b in aliases.get(a, ()) or a in aliases.get(b, ())
        if row["expect"] == "alias":
            return "ok" if linked else "miss"
        return "false_alias" if linked else "ok"
    got = state.get(row["link"], {}).get(row["candidate"], "absent")
    if row["expect"] == "mention":
        return {"confirmed": "ok", "ambiguous": "ambiguous"}.get(got, "miss")
    return "false_positive" if got == "confirmed" else ("ok_" + got if got != "absent" else "ok")


def main(gold_path, *runs):
    lines = [l for l in Path(gold_path).read_text().splitlines() if l.strip() and not l.startswith("#")]
    gold = list(csv.DictReader(lines, delimiter="\t"))
    names, loaded = [], []
    for spec in runs:
        name, path = spec.split("=", 1)
        names.append(name)
        loaded.append(load_run(path))
    print("| expect | link | candidate | " + " | ".join(names) + " | note |")
    print("|---|---|---|" + "---|" * len(names) + "---|")
    summary = [collections.Counter() for _ in names]
    for row in gold:
        cells = []
        for i, (state, aliases) in enumerate(loaded):
            v = verdict(row, state, aliases)
            summary[i][(row["expect"], v.split("_")[0] if v.startswith("ok") else v)] += 1
            cells.append(v)
        link = row["link"].replace("https://t.me/", "")
        print(f"| {row['expect']} | {link} | {row['candidate']} | " + " | ".join(cells) + f" | {row['note']} |")
    print()
    for name, s in zip(names, summary):
        print(name, dict(sorted(s.items())))


if __name__ == "__main__":
    main(*sys.argv[1:])
