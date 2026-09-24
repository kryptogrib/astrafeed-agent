"""Research Pulse, demo check: is what is on disk exactly what the code builds now?

python3 docs/research/pulse_check.py astrafeed.db          # exit 1 on any mismatch

Checks the database md5 against artifacts/pulse-slices.json, then rebuilds every example of every slice
(brief + aggregate) and the registry comparison in memory and compares them byte for byte with the saved
files. Nothing is written. A mismatch means a script, the grouping or the data changed after the files
were built: rerun the command printed next to it.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pulse_brief import REGISTRY, build  # noqa: E402
from pulse_compare import compare, render  # noqa: E402


def dump(x):
    return json.dumps(x, ensure_ascii=False, indent=1) + "\n"


def main(db_path):
    reg = json.loads(REGISTRY.read_text())
    md5 = hashlib.md5(Path(db_path).read_bytes()).hexdigest()
    bad = [] if md5 == reg["db_md5"] else [f"database md5 {md5}, registry {reg['db_md5']}"]
    for s in reg["slices"]:
        for w in s.get("examples", [None]):
            b = build(db_path, s["key"], w)
            cmd = f"python3 docs/research/pulse_brief.py {db_path} {s['key']}" + (f" {w}" if w else "")
            for name, text in ((b["brief_name"], b["brief"]), (b["aggregate_name"], dump(b["aggregate"]))):
                p = b["dir"] / name
                ok = p.exists() and p.read_text() == text
                print(f"{'ok ' if ok else 'BAD'} {p}")
                bad += [] if ok else [f"{p}: {cmd}"]
    if c := reg.get("compare"):
        r = compare(db_path, c["topic"], c["a"], c["b"])
        d = r.pop("dir")
        name = f"compare-{c['a'].replace('..', '_')}-vs-{c['b'].replace('..', '_')}"
        for p, text in ((d / f"{name}.md", render(r)), (d / f"{name}.json", dump(r))):
            ok = p.exists() and p.read_text() == text
            print(f"{'ok ' if ok else 'BAD'} {p}")
            bad += [] if ok else [f"{p}: {r['cmd']}"]
    if bad:
        raise SystemExit("mismatch:\n" + "\n".join(bad))
    print(f"all match, database md5 {md5}")


if __name__ == "__main__":
    main(*sys.argv[1:])
