"""Research Pulse, step 5: demo Pulse(topic, window) on prepared slices, one command.

python3 docs/research/pulse_brief.py astrafeed.db zec
python3 docs/research/pulse_brief.py astrafeed.db zec 2026-09-17..2026-09-19

The topic is looked up in artifacts/pulse-slices.json (aliases -> slice dir). Thread selection, model runs
and publication (pulse_publish.py) are already done for the slice; this script only reads them. It counts
with pulse_aggregate.aggregate and writes the brief: every number, link, coverage row, window and grounding
note comes from the data. Topics, units, their types, titles and notes come from the slice's grouping file,
which is agent work: the code checks that every id is published and sits in one unit, not that the units
are merged well. A slice without a grouping gets one line per reply: model aspect as topic, model kind as
type, model summary as text, marked as such.

Writes <dir>/brief.md and the aggregate (or brief-<from>_<to>.md and aggregate-...-<from>_<to>.json for a
window). The output depends on the database and the files only, so a second run gives the same bytes.
No LLM call; database opened read-only.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pulse_aggregate import aggregate  # noqa: E402

REGISTRY = Path("artifacts/pulse-slices.json")
TYPES = {  # order of rendering, label in counts, heading
    "argument": ("аргумент", "Аргументы (есть основание)"),
    "opinion": ("мнение", "Мнения и прогнозы (без основания)"),
    "recommendation": ("совет", "Советы"),
    "question": ("вопрос", "Вопросы"),
    "answer": ("ответ", "Ответы"),
    "info": ("сообщение", "Сообщения о фактах (не проверены)"),
    "experience": ("опыт", "Личный опыт"),
    "curator": ("дополнение подборки", "Дополнения подборки"),
    "reaction": ("реакция", "Реакции (без содержания для вывода)"),
    "service": ("служебные", "Служебные (в выводы не идут)"),
    "other": ("другое", "Другое"),
}
ASPECTS = {"market": "Рынок и цена", "technology": "Технология", "usage": "Использование", "other": "Другое"}
DIRECTION = {"up": "рост", "down": "падение", "none": "без направления", "unknown": "направление неясно"}


def slice_for(topic):
    for s in json.loads(REGISTRY.read_text())["slices"]:
        if topic.lower() in s["aliases"]:
            return s
    raise SystemExit(f"no prepared slice for {topic!r}; a new topic needs thread selection, runs and grouping")


def auto_grouping(d):
    """No agent grouping: one unit per published reply, straight from the model labels."""
    topics = {}
    for p in sorted(d.glob("thread-*/v3/demo/published.json")):
        t = p.parts[-4].removeprefix("thread-")
        for x in json.loads(p.read_text())["published"]:
            topics.setdefault(x.get("aspect") or "other", []).append(
                {"key": f"{t}/{x['id']}", "type": x.get("kind") if x.get("kind") in TYPES else "other",
                 "title": f"{x.get('summary')} *(пересказ модели)*", "ids": [f"{t}/{x['id']}"]})
    return {"grouping": "группировка не выполнена: тема = aspect модели, тип = kind модели, строка = пересказ модели",
            "auto": True,
            "topics": [{"topic": ASPECTS.get(a, a), "units": u} for a, u in sorted(topics.items())]}


def parse_window(window):
    """"YYYY-MM-DD..YYYY-MM-DD" -> (lo, hi), both real calendar dates, lo <= hi. SystemExit otherwise."""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", window or "")
    try:
        lo, hi = (date.fromisoformat(x) for x in m.groups()) if m else (None, None)
    except ValueError as e:
        raise SystemExit(f"window {window!r}: {e}") from None
    if lo is None:
        raise SystemExit(f"window must be YYYY-MM-DD..YYYY-MM-DD, got {window!r}")
    if lo > hi:
        raise SystemExit(f"window {window!r}: start is after end")
    return lo.isoformat(), hi.isoformat()


def limitation(x):
    return (x, None) if isinstance(x, str) else (x["text"], x.get("threads"))


def day(ts):
    return ts[:10] if ts else "—"


def link(i, url):
    return f"[{i.split('/')[1]}]({url})"


def counts(by_type):
    return ", ".join(f"{TYPES[k][0]} {by_type[k]['comments']}" for k in TYPES if k in by_type)


def unit_line(u):
    refs = ", ".join(link(i, l) for i, l in zip(u["ids"], u["links"]))
    extra = [DIRECTION[u["direction"]]] if u.get("direction") in DIRECTION else []
    size = f" — {u['comments']} репл., {u['authors']} авт." if u["comments"] > 1 else ""
    note = f" *({u['note']})*" if u.get("note") else ""
    return f"- {u['title']}{' [' + ', '.join(extra) + ']' if extra else ''}{note} ({refs}){size}"


def by_type_order(units):
    return sorted(units, key=lambda u: list(TYPES).index(u["type"]))


def render_topic(t, spec, units):
    md = [f"## {t['topic']}", "",
          f"*Реплик: {t['comments']}, авторов: {t['authors']}, тредов: {t['threads']}. По типам: {counts(t['by_type'])}.*", ""]
    if spec.get("note"):
        md += [f"Заметка агента: {spec['note']}", ""]
    if spec.get("groups"):
        for g in spec["groups"]:
            us = [u for u in units if u.get("group") == g["name"]]
            if not us:
                continue
            md.append(f"**{g['name']}**" + (f" ({g['subtitle']})" if g.get("subtitle") else "") + ":")
            md += [unit_line(u) + f" — {TYPES[u['type']][0]}" for u in by_type_order(us)]
            if g.get("note"):
                md += ["", f"Заметка агента: {g['note']}"]
            md.append("")
    else:
        for k, (_, head) in TYPES.items():
            us = [u for u in units if u["type"] == k]
            if us:
                md += [f"**{head}:**"] + [unit_line(u) for u in us] + [""]
    return md


def short_answer(res, groups):
    """First section: agent statements (no digits in their text), numbers and sources from the code."""
    if groups.get("auto"):
        return ["## Короткий ответ", "",
                "Короткий ответ не подготовлен: группировка не выполнена, наблюдения агента для этого среза нет. "
                "Ниже — охват и пересказы модели по одной реплике.", ""]
    obs, total = res.get("observations", []), len(groups.get("observations", {}).get("items", []))
    if not total:
        return []
    md = ["## Короткий ответ", "",
          "*Формулировки — агентские, предварительные, не человеческие; числа и ссылки подставлены кодом по "
          "единицам группировки, на которые опирается наблюдение. Полный отчёт ниже — детализация.*", ""]
    if len(obs) < total:
        md += [f"В окне осталось наблюдений: {len(obs)} из {total}; остальные опирались только на реплики "
               "вне окна.", ""]
    for n, o in enumerate(obs, 1):
        refs = ", ".join(link(x["id"], x["link"]) for x in o["links"])
        more = f" и ещё {o['more_links']}" if o["more_links"] else ""
        part = f"; в окне {len(o['units'])} из {o['units_total']} единиц" if len(o["units"]) < o["units_total"] else ""
        md.append(f"{n}. {o['text']} *Реплик: {o['comments']}, авторов: {o['authors']}, тредов: {o['threads']}, "
                  f"каналов: {o['channels']}{part}.* Источники: {refs}{more}.")
    return md + [""]


def brief_lines(res, threads, window=None):
    pub = sum(x["published"] for x in threads.values())
    total = {}
    for u in res["units"]:
        total[u["type"]] = total.get(u["type"], 0) + u["comments"]
    top = sorted(res["topics"], key=lambda t: -t["comments"])
    md = [f"- Опубликовано реплик: {pub} (тредов: {sum(x['published'] > 0 for x in threads.values())}, "
          f"каналов: {len({x['channel'] for x in threads.values() if x['published']})}); "
          f"отложено на проверку: {sum(x['held'] for x in threads.values())}."]
    if top:
        md.append("- Темы по числу реплик: " + "; ".join(
            f"{t['topic']} — {t['comments']} (авторов: {t['authors']}, тредов: {t['threads']})" for t in top) + ".")
    md.append(f"- По типам {'в окне' if window else 'во всём наборе'}: " + counts({k: {"comments": v} for k, v in total.items()}) + ".")
    one = [t["topic"] for t in top if t["threads"] == 1 and t["comments"] > 1]
    if one:
        md.append(f"- Только в одном треде: {', '.join(one)} — это разговор одного обсуждения, не общий фон.")
    return md


def grounding_lines(d, only=None):
    md = []
    for p in sorted(d.glob("thread-*/v3/demo/grounding.json")):
        g = json.loads(p.read_text())
        t = p.parts[-4].removeprefix("thread-")
        if g["mentions_changed"] and (only is None or t in only):
            md.append(f"- {t}: опора публикации (`{g['publication']['grounding_version']}`) отличается от входа модели "
                      f"в {', '.join(g['mentions_changed'])}; по входу модели было бы отложено "
                      f"{len(g['model_input']['held_if_published_on_it'])}, по опоре публикации — "
                      f"{len(g['publication']['held'])}. Вход модели — `request.json` (не меняется), "
                      f"разница — `{p.relative_to(d)}`.")
    return md or [f"- Во всех тредах{' окна' if only is not None else ''} опора публикации совпадает с тем, "
                  "что видела модель."]


def build(db_path, topic, window=None):
    """Pulse(topic, window) from saved data, without writing files: {"slice", "dir", "window", "aggregate",
    "aggregate_name", "brief", "brief_name"}. Raises SystemExit for an unknown topic or a bad window."""
    s = slice_for(topic)
    d = Path(s["dir"])
    groups = json.loads((d / s["grouping"]).read_text()) if s["grouping"] else auto_grouping(d)
    keep, suffix = None, ""
    if window:
        lo, hi = parse_window(window)
        keep, suffix = (lambda i, ts: lo <= ts[:10] <= hi), f"-{lo}_{hi}"
    res = aggregate(db_path, d, groups, keep)
    every = res["threads"]
    # in a window only threads with comments in it are counted and shown; the rest are named once
    threads = {t: x for t, x in every.items() if not window or x["comments"]}
    outside = [t for t in every if t not in threads]
    agg_name = s["aggregate"].removesuffix(".json") + suffix + ".json"

    span = [min((x["first"] for x in every.values() if x["first"])), max((x["last"] for x in every.values() if x["last"]))]
    cmd = f"python3 docs/research/pulse_brief.py {Path(db_path).name} {s['key']}" + (f" {window}" if window else "")
    md = [f"# Pulse: {s['title']}" + (f", окно {window.replace('..', ' – ')}" if window else ""), "",
          f"> Собрано одной командой `{cmd}` из сохранённых данных: новых вызовов модели нет. "
          "Числа, ссылки, охват и окно подставлены кодом.",
          f"> Группировка: {'**не выполнена** — строки ниже это пересказы модели по одной реплике' if groups.get('auto') else '**агентская (предварительная), не человеческая** — `' + s['grouping'] + '`'}.",
          f"> **Историческое окно.** Комментарии среза — с {day(span[0])} по {day(span[1])}; это не текущая неделя."
          + (f" Запрошено {window.replace('..', ' – ')}; " + (
              f"опубликованные реплики в окне — {day(res['window'][0])} – {day(res['window'][1])}." if res["units"]
              else "опубликованных реплик в окне нет.") if window else ""), ""]
    if not res["units"]:
        md += ["**В этом окне опубликованных реплик нет.**", ""]
    else:
        md += short_answer(res, groups) + ["## Коротко", ""] + brief_lines(res, threads, window) + [""]

    md += ["## Что автоматизировано, а что — агентская работа", "",
           "- **Код:** отбор реплик по опоре на тему, флаг `relevant_not_grounded`, слой исправлений, "
           "подсчёт реплик, авторов, тредов и каналов, ссылки, охват, окно. Проверяется, что каждая ссылка есть в "
           "опубликованном наборе и что реплика стоит ровно в одной единице.",
           "- **Модель** (сохранённые прогоны): relevance, aspect, kind, пересказ.",
           "- **Агент:** " + ("не участвовал в группировке этого среза." if groups.get("auto") else
                              "темы, объединение реплик в единицы, тип единицы, формулировки, подзаголовки и заметки. "
                              "Качество объединения кодом не проверяется."), "",
           "## Охват", "", "| тред | канал | комментарии (даты) | реплик | опубликовано | отложено |",
           "|---|---|---|---:|---:|---:|"]
    for t, x in threads.items():
        a, b = (x["first_kept"], x["last_kept"]) if window else (x["first"], x["last"])
        md.append(f"| [{t}]({x['link']}) | {x['channel']} | {day(a)} – {day(b)} | {x['comments']} | "
                  f"{x['published']} | {x['held']} |")
    md += [f"| **итого** | каналов: {len({x['channel'] for x in threads.values()})} | | "
           f"{sum(x['comments'] for x in threads.values())} | **{sum(x['published'] for x in threads.values())}** | "
           f"**{sum(x['held'] for x in threads.values())}** |", ""]
    if window:
        md += ["- В окне считаются реплики по дате комментария; «реплик» и даты — комментарии треда в окне."]
        if outside:
            md.append(f"- Вне окна (нет комментариев в окне, в итог не входят): {', '.join(outside)}.")
        md.append("")
    md += ["- Опубликовано — relevant у модели, без флага `relevant_not_grounded` (флаг ставится на метках модели, "
           "исправления его не снимают). Отложенные в бриф не входят, лежат в `thread-*/v3/demo/published.md`.",
           f"- Нераспределённых опубликованных реплик: {len(res['unassigned_published'])}."
           + ("".join(f" {link(u['id'], u['link'])}" for u in res["unassigned_published"])), "",
           "**Опора: что видела модель и что использует публикация**", ""] + grounding_lines(d, set(threads) if window else None) + [""]

    md += ["## Как читать", "",
           "- Тема ≠ аргумент. Число реплик в теме не означает, что столько людей поддерживают одно утверждение.",
           "- Число авторов у единицы — сколько разных авторов в неё попало, а не сколько «подтвердили».",
           "- Несколько тредов или каналов — не независимость: участники могут пересекаться.",
           "- Сведения из реплик (дедлайны, цены, мосты, маркеты) не проверялись.", ""]
    spec = {t["topic"]: t for t in groups["topics"]}
    for t in res["topics"]:
        md += render_topic(t, spec[t["topic"]], [u for u in res["units"] if u["subject"] == t["topic"]])

    empty = [t for t, x in threads.items() if x["published"] == 0]
    md += ["## Ограничения", "",
           "- Не настроение комьюнити: подготовленный срез из нескольких тредов за историческое окно, короткие реплики.",
           "- Человеческой проверки нет: метки — вывод модели, исправления" +
           ("" if groups.get("auto") else " и группировка") + " — агентские.",
           "- Каждая реплика учтена в одной единице по основному типу. Это ограничение демо, а не правило: "
           "реплика бывает и ответом, и аргументом."]
    if empty:
        md.append(f"- Без опубликованных реплик{' (из тредов с комментариями в окне)' if window else ''}: "
                  f"{', '.join(empty)}.")
    md += [f"- {text}" for text, ts in map(limitation, s["limitations"]) if ts is None or set(ts) & set(threads)]
    md += ["",
           "## Файлы", "",
           f"- `{d / agg_name}` — подсчёты этого брифа;"] + (
           [] if groups.get("auto") else [f"- `{d / s['grouping']}` — агентская группировка;"]) + [
           f"- `{d}/thread-*/v3/demo/published.json`, `grounding.json` — публикуемые наборы и опора;",
           f"- `{d}/thread-*/v3/request.json`, `labels.json` — вход и выход модели, не меняются."]
    return {"slice": s, "dir": d, "window": window, "span": span, "aggregate": res, "aggregate_name": agg_name,
            "threads": threads, "outside": outside,
            "brief": "\n".join(md) + "\n", "brief_name": f"brief{suffix}.md"}


def main(db_path, topic, window=None):
    b = build(db_path, topic, window)
    d, res, threads = b["dir"], b["aggregate"], b["aggregate"]["threads"]
    (d / b["aggregate_name"]).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    (d / b["brief_name"]).write_text(b["brief"])
    print(f"{d / b['brief_name']}: {sum(x['published'] for x in threads.values())} published, "
          f"{len(res['units'])} units, {len(res['topics'])} topics, window {day(b['span'][0])}..{day(b['span'][1])}")


if __name__ == "__main__":
    main(*sys.argv[1:])
