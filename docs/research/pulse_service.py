"""Research Pulse, demo service: Pulse(topic, window) over the prepared slices as a JSON payload, and a small server.

python3 docs/research/pulse_service.py astrafeed.db [host] [port]      # serves /healthz, /pulse, /pulse/compare, /news-pulse
curl 'http://127.0.0.1:8000/pulse?topic=zec&window=2026-09-17..2026-09-19'
curl 'http://127.0.0.1:8000/pulse/compare?topic=zec&a=2026-09-17..2026-09-19&b=2026-09-20..2026-09-22&format=md'
curl 'http://127.0.0.1:8000/news-pulse?topic=zec&window=2026-09-17..2026-09-19'
# /news-pulse is cache-only (saved pulse.json or LLM cache). It does not call the network.

pulse(db, topic, window) wraps pulse_brief.build: same numbers, links and Markdown as brief.md, nothing written
to disk, no LLM call, database opened read-only. Unknown topic -> LookupError, bad window -> ValueError.
Needs the FastAPI app from src/ (run inside the project environment, e.g. `uv run python3 ...`).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from news_pulse_build import news_pulse as news_pulse_build  # noqa: E402
from pulse_brief import REGISTRY, build, limitation  # noqa: E402
from pulse_compare import compare, render  # noqa: E402


def pulse(db_path, topic, window=None):
    try:
        b = build(db_path, topic, window)
    except SystemExit as e:
        raise errors(e) from None
    s, res, d, threads = b["slice"], b["aggregate"], b["dir"], b["threads"]
    auto = not s["grouping"]
    return {
        "topic": s["key"], "title": s["title"],
        "status": "ok" if res["units"] else "no_data_in_window",
        "window": {"requested": window, "published_replies": res.get("window"), "slice_comments": b["span"],
                   "historical": True, "threads_outside": b["outside"]},
        "grouping": {"kind": "none" if auto else "agent_preliminary", "source": None if auto else str(d / s["grouping"]),
                     "human_reviewed": False},
        "short_answer": {"kind": "none" if auto else "agent_preliminary", "numbers_by": "code",
                         "observations": res.get("observations", [])},
        "counts": {"published": sum(x["published"] for x in threads.values()),
                   "held_for_review": sum(x["held"] for x in threads.values()),
                   "threads_with_published": sum(x["published"] > 0 for x in threads.values()),
                   "channels_with_published": len({x["channel"] for x in threads.values() if x["published"]}),
                   "units": len(res["units"]), "topics": len(res["topics"])},
        "coverage": threads,
        "topics": res["topics"],
        "units": res["units"],
        "unassigned_published": res["unassigned_published"],
        "limitations": [t for t, ts in map(limitation, s["limitations"]) if ts is None or set(ts) & set(threads)],
        "brief_markdown": b["brief"],
    }


def pulse_compare(db_path, topic, a, b):
    try:
        c = compare(db_path, topic, a, b)
    except SystemExit as e:
        raise errors(e) from None
    c.pop("dir")
    return dict(c, markdown=render(c))


def errors(e):
    msg = str(e)
    return (LookupError if msg.startswith("no prepared slice") else ValueError)(msg)


def fingerprint(db_path):
    """What the demo runs on: commit (+ dirty flag) and the database md5 against the registry."""
    run = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.strip()  # noqa: E731
    reg = json.loads(REGISTRY.read_text())
    md5 = hashlib.md5(Path(db_path).read_bytes()).hexdigest()
    return {"commit": run("git", "rev-parse", "--short", "HEAD") or None,
            "dirty": bool(run("git", "status", "--porcelain", "--", "docs/research", "artifacts", "src")),
            "db_md5": md5, "db_expected": reg.get("db_md5"), "db_ok": md5 == reg.get("db_md5")}


def main(db_path, host="127.0.0.1", port="8000"):
    import uvicorn
    from astrafeed.adapters.http.app import create_app

    info = fingerprint(db_path)
    if not info["db_ok"]:
        raise SystemExit(f"database md5 {info['db_md5']} differs from the registry {info['db_expected']}")
    pulse(db_path, json.loads(REGISTRY.read_text())["slices"][0]["key"])  # fail early
    uvicorn.run(create_app(pulse=lambda topic, window: pulse(db_path, topic, window),
                           compare=lambda topic, a, b: pulse_compare(db_path, topic, a, b),
                           news_pulse=lambda topic, window: news_pulse_build(db_path, topic, window),
                           info=info),
                host=host, port=int(port))


if __name__ == "__main__":
    main(*sys.argv[1:])
