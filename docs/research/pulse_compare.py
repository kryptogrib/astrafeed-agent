"""Research Pulse, comparison of two periods of one prepared slice.

python3 docs/research/pulse_compare.py astrafeed.db zec 2026-09-17..2026-09-19 2026-09-20..2026-09-22

Runs pulse_brief.build for each period (same aggregate, same agent grouping) and puts the counts side by
side: published replies, threads, channels, topics, and which threads carry the discussion in each period.
Then recounts the same numbers a second, independent way (published.json + comment time straight from the
database, no aggregate) and stops if anything differs. The periods must not overlap, A before B.
Writes <dir>/compare-<A>_<B>.md and .json. No LLM call; the verdict is a template filled by the code.
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pulse_brief import build, parse_window  # noqa: E402


def recount(db_path, d, groups, lo, hi):
    """Second count, without pulse_aggregate: published ids by thread and topic whose comment date is in
    [lo, hi]. Comment time is read by link, so a join mistake in the aggregate would show up here."""
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    by_thread, kept = {}, set()
    for p in sorted(d.glob("thread-*/v3/demo/published.json")):
        t = p.parts[-4].removeprefix("thread-")
        for x in json.loads(p.read_text())["published"]:
            (ts,) = db.execute("SELECT ts FROM comment WHERE link = ?", (x["link"],)).fetchone()
            if lo <= ts[:10] <= hi:
                by_thread[t] = by_thread.get(t, 0) + 1
                kept.add(f"{t}/{x['id']}")
    db.close()
    by_topic = {}
    for tp in groups.get("topics", []):
        n = sum(i in kept for u in tp["units"] for i in u["ids"])
        if n:
            by_topic[tp["topic"]] = n
    return {"published": len(kept), "by_thread": by_thread, "by_topic": by_topic}


def period(b):
    res, threads = b["aggregate"], b["threads"]
    pub = {t: x["published"] for t, x in threads.items() if x["published"]}
    return {"window": b["window"], "published": sum(pub.values()),
            "held_for_review": sum(x["held"] for x in threads.values()),
            "threads_with_published": sorted(pub), "by_thread": pub,
            "channels_with_published": sorted({threads[t]["channel"] for t in pub}),
            "published_span": res["window"],
            "topics": {t["topic"]: {k: t[k] for k in ("comments", "authors", "threads")} for t in res["topics"]},
            "observations": [o["key"] for o in res.get("observations", [])]}


def compare(db_path, topic, a, b):
    (alo, ahi), (blo, bhi) = parse_window(a), parse_window(b)
    if not ahi < blo:
        raise SystemExit(f"periods must not overlap and A must come before B: {a} vs {b}")
    ba, bb = build(db_path, topic, a), build(db_path, topic, b)
    s, d = ba["slice"], ba["dir"]
    groups = json.loads((d / s["grouping"]).read_text()) if s["grouping"] else {}
    pa, pb = period(ba), period(bb)
    for p, lo, hi in ((pa, alo, ahi), (pb, blo, bhi)):  # independent recount
        r = recount(db_path, d, groups, lo, hi)
        mine = {"published": p["published"], "by_thread": p["by_thread"],
                "by_topic": {k: v["comments"] for k, v in p["topics"].items()}}
        if groups and r != mine or not groups and r["published"] != p["published"]:
            raise SystemExit(f"recount differs for {p['window']}: {r} vs {mine}")
        p["verified"] = True
    shared = sorted(set(pa["threads_with_published"]) & set(pb["threads_with_published"]))
    topics = sorted(set(pa["topics"]) | set(pb["topics"]),
                    key=lambda t: -(pa["topics"].get(t, {}).get("comments", 0) + pb["topics"].get(t, {}).get("comments", 0)))
    days = [(date.fromisoformat(hi) - date.fromisoformat(lo)).days + 1 for lo, hi in ((alo, ahi), (blo, bhi))]
    return {"topic": s["key"], "title": s["title"], "a": pa, "b": pb, "days": days, "shared_threads": shared,
            "topics_order": topics,
            "threads": {t: {k: x[k] for k in ("link", "channel")} for t, x in ba["aggregate"]["threads"].items()}, "grouping": s["grouping"],
            "cmd": f"python3 docs/research/pulse_compare.py {Path(db_path).name} {s['key']} {a} {b}", "dir": d}


def render(c):
    a, b, th = c["a"], c["b"], c["threads"]
    ta, tb = set(a["threads_with_published"]), set(b["threads_with_published"])

    def row(name, fa, fb):
        return f"| {name} | {fa} | {fb} |"

    def tl(ts):
        return ", ".join(f"[{t}]({th[t]['link']})" + f" ({th[t]['channel']})" for t in sorted(ts)) or "—"

    md = [f"# Pulse: {c['title']}, сравнение периодов", "",
          f"> Собрано одной командой `{c['cmd']}` из сохранённых данных, новых вызовов модели нет. Числа и ссылки "
          "подставлены кодом. Опубликованные реплики по периоду, треду и теме пересчитаны второй раз напрямую из "
          "`published.json` и времени комментария в базе, без агрегатора — расхождений нет (авторы и отложенные "
          "не пересчитывались).",
          f"> Группировка тем: **агентская (предварительная), не человеческая** — `{c['grouping']}`." if c["grouping"]
          else "> Группировка не выполнена: темы — aspect модели.",
          "> **Историческое окно**, не текущая неделя. Это не индекс настроения: считаются опубликованные реплики, "
          "а не мнения.", "",
          "## Вывод", ""]
    if not ta & tb:
        md += [f"- Ни один тред не даёт опубликованных реплик в обоих периодах: A — {tl(ta)}; B — {tl(tb)}. "
               "Разница между периодами — это смена постов, которые собрали обсуждение, а не изменение мнений "
               "внутри одного обсуждения."]
    else:
        md += [f"- Треды с опубликованными репликами в обоих периодах: {tl(ta & tb)}; только в A: {tl(ta - tb)}; "
               f"только в B: {tl(tb - ta)}."]
    gone = [t for t in c["topics_order"] if t in a["topics"] and t not in b["topics"]]
    new = [t for t in c["topics_order"] if t in b["topics"] and t not in a["topics"]]
    both = [t for t in c["topics_order"] if t in a["topics"] and t in b["topics"]]
    md += [f"- Темы только в A: {', '.join(gone) or '—'}; только в B: {', '.join(new) or '—'}; в обоих: "
           f"{', '.join(both) or '—'}."]
    for t in both:
        md.append(f"- «{t}» есть в обоих периодах: A — {a['topics'][t]['comments']} репл. "
                  f"({a['topics'][t]['threads']} тред.), B — {b['topics'][t]['comments']} репл. "
                  f"({b['topics'][t]['threads']} тред.).")
    if c["days"][0] != c["days"][1]:
        md.append(f"- Периоды разной длины ({c['days'][0]} и {c['days'][1]} дн.): абсолютные числа несравнимы.")
    md += ["", "## Периоды", "", f"| | A: {a['window'].replace('..', ' – ')} | B: {b['window'].replace('..', ' – ')} |",
           "|---|---:|---:|",
           row("дней", c["days"][0], c["days"][1]),
           row("опубликовано реплик", a["published"], b["published"]),
           row("отложено на проверку", a["held_for_review"], b["held_for_review"]),
           row("тредов с опубликованными", len(ta), len(tb)),
           row("каналов с опубликованными", len(a["channels_with_published"]), len(b["channels_with_published"])),
           row("наблюдений короткого ответа", len(a["observations"]), len(b["observations"])),
           row("пересчёт реплик совпал", "да" if a["verified"] else "нет", "да" if b["verified"] else "нет"),
           "", "## Темы", "", "| тема | A: реплик / авторов / тредов | B: реплик / авторов / тредов |",
           "|---|---:|---:|"]
    for t in c["topics_order"]:
        f = [" / ".join(str(p["topics"][t][k]) for k in ("comments", "authors", "threads")) if t in p["topics"]
             else "—" for p in (a, b)]
        md.append(row(t, *f))
    md += ["", "## Треды", "", "| тред | канал | A | B |", "|---|---|---:|---:|"]
    for t in sorted(ta | tb):
        md.append(f"| [{t}]({th[t]['link']}) | {th[t]['channel']} | {a['by_thread'].get(t, '—')} | "
                  f"{b['by_thread'].get(t, '—')} |")
    md += ["", "## Как читать", "",
           "- Сравниваются количества опубликованных реплик по дате комментария, не мнения и не их доли.",
           "- Число реплик зависит от того, какие посты вышли в период: один оживлённый тред меняет картину.",
           "- Авторы в периодах могут пересекаться; независимость источников не проверялась.",
           "- Подробности каждого периода — в брифах окна: "
           f"`brief-{a['window'].replace('..', '_')}.md`, `brief-{b['window'].replace('..', '_')}.md`.", ""]
    return "\n".join(md)


def main(db_path, topic, a, b):
    c = compare(db_path, topic, a, b)
    d = c.pop("dir")
    name = f"compare-{a.replace('..', '_')}-vs-{b.replace('..', '_')}"
    (d / f"{name}.json").write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n")
    (d / f"{name}.md").write_text(render(c))
    print(f"{d / name}.md: A {c['a']['published']} vs B {c['b']['published']} published, "
          f"shared threads {c['shared_threads'] or 'none'}, recount ok")


if __name__ == "__main__":
    main(*sys.argv[1:])
