"""Независимая демо-проверка news-first Pulse (stdlib, без импорта конвейера).

python3 docs/research/news_pulse_eval.py --db astrafeed.db
БД открывается исключительно URI mode=ro. Замороженные файлы не изменяются.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = re.compile(r"https://t\.me/[A-Za-z0-9_]+/\d+(?:\?comment=\d+)?")


def ts(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


OPTIONAL_SAMPLE = frozenset({"windows.json", "holdout.json", "README.md", "sample.py"})


def load_sample(directory):
    manifest = read_json(directory / "manifest.json")
    hashes = manifest.get("sha256", {})
    for name in ("posts.jsonl", "comments.jsonl", "pairs.jsonl"):
        if name not in hashes:
            raise ValueError(f"В manifest.json нет sha256: {name}")
    for name, expected in hashes.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError(f"Путь вне выборки: {name}")
        if name in OPTIONAL_SAMPLE and not path.is_file():
            continue
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Несовпадение sha256 замороженной выборки: {name}")
    data = {name: [json.loads(line) for line in (directory / (name + ".jsonl")).read_text().splitlines() if line.strip()]
            for name in ("posts", "comments", "pairs")}
    windows_path = directory / "windows.json"
    windows = read_json(windows_path) if windows_path.is_file() else {"topics": {}}
    return {**data, "windows": windows, "manifest": manifest}


def load_db(path):
    """Исходные записи без правил отбора/классификации из конвейера."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        posts = []
        for row in db.execute("SELECT source_id, external_id, timestamp, payload FROM raw_item"):
            payload = json.loads(row["payload"])
            posts.append({"source_id": row["source_id"], "external_id": str(row["external_id"]),
                          "link": payload.get("link", ""), "published_at": payload.get("timestamp") or row["timestamp"],
                          "author_id": payload.get("author_id") or payload.get("author_key")})
        comments = [dict(r) for r in db.execute("SELECT comment_key, source_id, ts AS published_at, link, author_key AS author_id FROM comment")]
        return posts, comments
    finally:
        db.close()


class Metric:
    def __init__(self, title, threshold=None, zero=False, note=""):
        self.title, self.threshold, self.zero, self.note = title, threshold, zero, note
        self.numerator = self.denominator = 0
        self.errors, self.missing = [], []

    def add(self, correct, **detail):
        self.denominator += 1
        self.numerator += int(not correct if self.zero else correct)
        if not correct:
            self.errors.append(detail)

    def result(self):
        value = self.numerator / self.denominator if self.denominator else None
        failed = value is not None and self.threshold is not None and (self.numerator > 0 if self.zero else value < self.threshold)
        status = "fail" if failed else "unverified" if not self.denominator or self.missing or self.threshold is None else "pass"
        return dict(title=self.title, numerator=self.numerator, denominator=self.denominator,
                    value=value, threshold=("= 0 ошибок" if self.zero else self.threshold), status=status,
                    errors=self.errors, missing=self.missing, note=self.note)


def same_window(a, b):
    return ts(a["start"]) == ts(b["start"]) and ts(a["end"]) == ts(b["end"])


def discover(directory):
    runs, missing = [], []
    paths = sorted(set(directory.glob("*/*/pulse.json")) | set(directory.glob("*/*/decisions.json")))
    for folder in sorted({p.parent for p in paths}):
        run = {"path": str(folder)}
        for name in ("pulse", "decisions"):
            path = folder / (name + ".json")
            if path.exists():
                try:
                    run[name] = read_json(path)
                except (ValueError, OSError) as exc:
                    missing.append(f"Некорректный вход {path}: {exc}")
            else:
                missing.append(f"Отсутствует {path}")
        base = run.get("decisions", run.get("pulse", {}))
        if isinstance(base.get("window"), dict) and {"start", "end"} <= base["window"].keys():
            run.update(topic=base.get("topic", folder.parent.name), window=base["window"])
            runs.append(run)
        else:
            missing.append(f"Нет ISO-границ окна: {folder}")
    return runs, missing


def expected_events(post):
    ex = post["expected"]
    return set(ex.get("event_ids") or ([ex["event_id"]] if ex.get("event_id") else []))


def _coverage_by_topic(sample, runs, missing):
    posts = sample["posts"]
    topics_spec = (sample.get("windows") or {}).get("topics") or {}
    coverage = {}
    if topics_spec:
        for topic, spec in topics_spec.items():
            widest = max(spec["windows"], key=lambda w: ts(w["end"]) - ts(w["start"]))
            candidates = [r for r in runs if r["topic"] == topic and same_window(r["window"], widest) and "decisions" in r]
            coverage[topic] = candidates[0] if candidates else None
            if not candidates:
                missing.append(f"Нет decisions coverage {topic}: [{widest['start']}, {widest['end']})")
            if len(candidates) > 1:
                raise ValueError(f"Неоднозначные coverage-входы: {topic}")
        return coverage
    topics = {t for p in posts for t in p["expected"]["topics"]}
    for topic in topics:
        candidates = [r for r in runs if r["topic"] == topic and "decisions" in r]
        if not candidates:
            missing.append(f"Нет decisions coverage {topic}")
            coverage[topic] = None
            continue
        coverage[topic] = max(candidates, key=lambda r: ts(r["window"]["end"]) - ts(r["window"]["start"]))
    return coverage


def evaluate_sample(sample, runs, metrics, missing):
    posts = {p["id"]: p for p in sample["posts"]}
    coverage = _coverage_by_topic(sample, runs, missing)
    maps = {topic: {p["link"]: p for p in r["decisions"].get("publications", [])} if r else {} for topic, r in coverage.items()}
    for p in posts.values():
        for topic in p["expected"]["topics"]:
            actual = maps.get(topic, {}).get(p["link"])
            detail = dict(links=[p["link"]], topic=topic, reason="Нет записи в decisions" if actual is None else "Решение не совпало с разметкой")
            expected = p["expected"]["relevant_news"]
            selected = bool(actual and actual.get("selected_news"))
            if selected:
                metrics["news_precision"].add(expected, **detail)
            if expected:
                metrics["news_recall"].add(selected, **detail)
            if actual is None:
                metrics["news_precision"].missing.append(detail)
            for field in ("segments", "origin", "source_role"):
                metric = metrics[field]
                if actual is None:
                    metric.missing.append(detail)
                    continue
                a, b = actual.get(field), p["expected"].get(field)
                if field == "segments":
                    a, b = sorted({x["class"] for x in a or []}), sorted({x["class"] for x in b or []})
                metric.add(a == b, **detail, expected=b, actual=a)
    for pair in sample["pairs"]:
        for topic in pair["shared_topics"]:
            a, b = posts[pair["a"]], posts[pair["b"]]
            da, db = maps.get(topic, {}).get(a["link"]), maps.get(topic, {}).get(b["link"])
            metric = metrics["same_event_recall" if pair["same_event"] else "false_merge"]
            detail = dict(pair=pair["id"], topic=topic, links=[a["link"], b["link"]])
            if da is None or db is None:
                detail["reason"] = "Нет записи в decisions"
                if not pair["same_event"]:
                    metric.missing.append(detail)
                    continue
            common = set((da or {}).get("event_ids", [])) & set((db or {}).get("event_ids", []))
            metric.add(bool(common) == pair["same_event"], **detail, common_event_ids=sorted(common))
    counts = Counter({"claimed_event_links": 0, "abstentions": 0, "other_types": 0, "missing": 0})
    for c in sample["comments"]:
        for topic in posts[c["post_ref"]]["expected"]["topics"]:
            run = coverage.get(topic)
            found = next((x for x in run["decisions"].get("comments", []) if x.get("comment_key") == c["id"] or x.get("link") == c["link"]), None) if run else None
            if found is None:
                counts["missing"] += 1
                metrics["comment_event_precision"].missing.append(dict(topic=topic, links=[c["link"]], reason="Нет комментария в decisions"))
                continue
            target = found.get("link_target", "")
            if not target.startswith("event:"):
                counts["abstentions" if target in ("topic_level", "unlinked") else "other_types"] += 1
                counts["type:" + target] += 1
                continue
            counts["claimed_event_links"] += 1
            predicted = target.split(":", 1)[1]
            expected = c["expected"]["link_target"]
            subject = c["expected"].get("subject")
            # Пересечение ожидаемых событий всех размеченных членов группы:
            # случайный общий член смешанной группы не доказывает верную связь.
            labels = [expected_events(p) for p in posts.values()
                      if topic in p["expected"]["topics"] and predicted in maps.get(topic, {}).get(p["link"], {}).get("event_ids", [])]
            mapped = set.intersection(*labels) if labels else set()
            if expected == "event" and subject:
                correct = subject in mapped
            else:
                correct = expected.startswith("event:") and expected.split(":", 1)[1] in mapped
            metrics["comment_event_precision"].add(correct, topic=topic, links=[c["link"]], expected=expected, actual=target, mapped_events=sorted(mapped))
    return dict(counts)


def check_boundaries(sample, runs, metric, missing):
    posts = {p["id"]: p for p in sample["posts"]}
    for topic, spec in sample["windows"]["topics"].items():
        boundary = next((w for w in spec["windows"] if w["id"].endswith("-boundary")), None)
        checks = []
        if boundary:
            # Все размеченные посты проверяются в boundary, включая start/end.
            for p in posts.values():
                if topic in p["expected"]["topics"]:
                    checks.append((p, boundary, ts(boundary["start"]) <= ts(p["timestamp"]) < ts(boundary["end"])))
        for case in spec.get("boundary_cases", []):
            checks.extend((posts[case["post_ref"]], probe, probe["expected_included"]) for probe in case["probes"])
        for p, window, expected in checks:
            candidates = [r for r in runs if r["topic"] == topic and same_window(r["window"], window) and "decisions" in r]
            detail = dict(topic=topic, links=[p["link"]], window=window)
            if not candidates:
                metric.missing.append(detail)
                message = f"Нет decisions граничной пробы {topic}: [{window['start']}, {window['end']})"
                if message not in missing:
                    missing.append(message)
                continue
            actual = any(row.get("link") == p["link"] for row in candidates[0]["decisions"].get("publications", []))
            metric.add(actual == expected, **detail, expected=expected, actual=actual)


def check_temporal(run, records, metric, history):
    start, end = ts(run["window"]["start"]), ts(run["window"]["end"])
    index = {r["link"]: r for r in records if r.get("link")}

    def check(value, path, historical=False, links=None):
        date = ts(value)
        detail = dict(run=run["path"], path=path, links=links or [], timestamp=value)
        if date < start and historical:
            history.append(detail)
        else:
            metric.add(start <= date < end, **detail, reason="Будущее" if date >= end else "До начала окна")

    def walk(obj, path, historical=False):
        if isinstance(obj, dict):
            historical = historical or obj.get("is_history") is True or obj.get("is_historical") is True or obj.get("historical") is True or obj.get("is_background") is True or obj.get("context_only") is True or obj.get("temporal_role") in ("history", "background", "previous_period")
            for key, value in obj.items():
                if key in ("window", "coverage", "llm"):
                    continue  # Границы/время запуска не являются сообщениями.
                sub = path + "." + key
                if key in ("published_at", "timestamp", "ts") and value:
                    check(value, sub, historical, [obj.get("link") or obj.get("url")] if obj.get("link") or obj.get("url") else [])
                else:
                    walk(value, sub, historical or key in ("history", "background", "previous_period"))
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                walk(value, f"{path}[{i}]", historical)
        elif isinstance(obj, str):
            for link in set(URL.findall(obj)):
                if link in index:
                    check(index[link]["published_at"], path, historical, [link])
                else:
                    metric.missing.append(dict(run=run["path"], path=path, links=[link], reason="В БД нет времени ссылки"))
    for name in ("decisions", "pulse"):
        if name in run:
            walk(run[name], name)
        else:
            metric.missing.append(dict(run=run["path"], reason=f"Нет {name}.json"))


def check_aggregates(run, posts, comments, metric):
    start, end = ts(run["window"]["start"]), ts(run["window"]["end"])
    dbposts = {p["link"]: p for p in posts}
    window_posts = [p for p in posts if start <= ts(p["published_at"]) < end]
    window_comments = [c for c in comments if start <= ts(c["published_at"]) < end]
    pulse, decisions = run.get("pulse"), run.get("decisions")

    def compare(path, actual, expected, links=None):
        metric.add(actual == expected, run=run["path"], path=path, actual=actual, expected=expected, links=links or [])

    if pulse is None:
        metric.missing.append(dict(run=run["path"], reason="Нет pulse.json"))
        return
    if not same_window(pulse["window"], run["window"]):
        compare("pulse.window", pulse["window"], run["window"])
    coverage = pulse.get("coverage", {})
    for key, expected in (("publications", len(window_posts)), ("channels", len({p["source_id"] for p in window_posts})), ("comments", len(window_comments))):
        compare("coverage." + key, coverage.get(key), expected)
    changes = pulse.get("changes", {})
    previous_start = start - (end - start)
    previous_posts = [p for p in posts if previous_start <= ts(p["published_at"]) < start]
    previous_comments = [c for c in comments if previous_start <= ts(c["published_at"]) < start]
    for key, value in (("discussion_comments", len(window_comments)), ("previous_comments", len(previous_comments))):
        if key in changes:
            compare("changes." + key, changes[key], value)
    source_coverage = changes.get("source_coverage", {})
    for key, rows in (("current_channels", window_posts), ("previous_channels", previous_posts)):
        if key in source_coverage:
            compare("changes.source_coverage." + key, source_coverage[key], len({p["source_id"] for p in rows}))
    if decisions is None:
        metric.missing.append(dict(run=run["path"], reason="Без decisions нельзя пересчитать отбор и группы"))
        return
    selected = [p for p in decisions.get("publications", []) if p.get("selected_news")]
    compare("coverage.topic_publications", coverage.get("topic_publications"), len({p["link"] for p in selected}))
    if "not_processed" in coverage:
        compare("coverage.not_processed", coverage["not_processed"], sum(p.get("status") == "not_processed" for p in decisions.get("publications", [])))
    groups = defaultdict(dict)
    for p in decisions.get("publications", []):
        for event in p.get("event_ids", []):
            groups[event][p["link"]] = p
    devents = {e["event_id"]: e for e in decisions.get("events", [])}
    pevents = {e["event_id"]: e for e in pulse.get("events", [])}
    compare("events.ids", sorted(pevents), sorted(groups))
    compare("decisions.events.ids", sorted(devents), sorted(groups))
    for event, members in groups.items():
        links = sorted(members)
        valid = [dbposts[link] for link in links if link in dbposts and start <= ts(dbposts[link]["published_at"]) < end]
        compare(f"{event}.records_in_db_window", len(valid), len(links), links)
        expected = dict(events=1, publications=len(valid), channels=len({p["source_id"] for p in valid}),
                        known_authors=len({p["author_id"] for p in valid if p["author_id"]}),
                        unknown_authors=sum(not p["author_id"] for p in valid),
                        found_origins=sum(p.get("origin") == "own" for p in members.values()),
                        reprints=sum(p.get("origin") in ("retelling", "repost") for p in members.values()),
                        unknown_origin=sum(p.get("origin") == "unknown" for p in members.values()))
        event_decision = devents.get(event, {})
        compare(f"decisions.{event}.publications", sorted(set(event_decision.get("publications", []))), links, links)
        for key, value in expected.items():
            field = "n_" + key
            if key in ("publications", "channels", "known_authors", "reprints", "unknown_origin"):
                compare(f"decisions.{event}.{field}", event_decision.get(field), value, links)
            compare(f"pulse.{event}.counts.{key}", pevents.get(event, {}).get("counts", {}).get(key), value, links)
        origins = sorted(link for link, p in members.items() if p.get("origin") == "own")
        compare(f"decisions.{event}.found_origins", sorted(event_decision.get("found_origins", [])), origins, links)
        pulse_links = sorted({p.get("url") or p.get("link") for p in pevents.get(event, {}).get("members", [])})
        compare(f"pulse.{event}.members", pulse_links, links, links)


def check_grounding(runs, db_path, grounding, fabrications):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from news_pulse_ground import check_run, load_texts

    try:
        texts = load_texts(Path(db_path))
    except sqlite3.OperationalError as exc:
        grounding.missing.append(f"В БД нет текстов для проверки: {exc}")
        fabrications.missing.append(f"В БД нет текстов для проверки: {exc}")
        return
    for run in runs:
        folder = Path(run["path"])
        if not (folder / "pulse.json").exists() or not (folder / "brief.md").exists():
            grounding.missing.append(f"Нет pulse.json/brief.md: {folder}")
            continue
        report = check_run(folder, texts)
        for claim in report["failures"]:
            grounding.add(False, run=str(folder), kind=claim["kind"], where=claim["where"], text=claim["text"][:200])
            fabrications.add(claim["numbers_from_source"], run=str(folder), where=claim["where"], text=claim["text"][:200])
        for _ in range(report["claims"] - len(report["failures"])):
            grounding.add(True)
            fabrications.add(True)


def evaluate(sample_dir, runs_dir, db_path):
    sample = load_sample(sample_dir)  # До любых вычислений и записи отчёта.
    before = digest(db_path, "md5")
    if sample["manifest"].get("db_md5") and before != sample["manifest"]["db_md5"]:
        raise ValueError("MD5 БД не совпадает с manifest.json выборки")
    posts, comments = load_db(db_path)
    runs, missing = discover(runs_dir)
    metrics = {
        "news_precision": Metric("Точность отбора новостей", .95),
        "news_recall": Metric("Полнота отбора новостей", .90),
        "false_merge": Metric("Ошибочное объединение отрицательных пар", 0, zero=True),
        "same_event_recall": Metric("Полнота объединения положительных пар", .90),
        "comment_event_precision": Metric("Правильность заявленных связей комментарий → событие", .90),
        "future_leakage": Metric("Записи и ссылки вне окна", 0, zero=True, note="Числитель — нарушения; знаменатель — проверенные вхождения времени/ссылок. Включает время < start; явная предыстория отдельно."),
        "boundary": Metric("Граничные пробы [start,end)", 1),
        "numeric_aggregates": Metric("Правильность числовых агрегатов", 1),
        "brief_grounding": Metric("Подтверждённость фактов брифа", .95, note="news_pulse_ground.py: brief.md = рендер pulse.json; цитаты, заголовки, реплики и основания дословно есть в источнике БД; счётчики пересчитываются по участникам."),
        "fabrications": Metric("Выдуманные цены, даты, авторство, официальное подтверждение", 0, zero=True, note="Число в утверждении брифа, которого нет в связанном источнике. Бриф извлекающий: авторство и подтверждение не генерируются."),
        **{k: Metric(title, note="Информативно, без порога; segments — точное совпадение множества классов поста, без оценки границ.") for k, title in (("segments", "Согласие сегментных классов"), ("origin", "Согласие происхождения"), ("source_role", "Согласие роли источника"))},
    }
    comment_counts = evaluate_sample(sample, runs, metrics, missing)
    check_boundaries(sample, runs, metrics["boundary"], missing)
    history = []
    for run in runs:
        check_temporal(run, posts + comments, metrics["future_leakage"], history)
        check_aggregates(run, posts, comments, metrics["numeric_aggregates"])
    check_grounding(runs, db_path, metrics["brief_grounding"], metrics["fabrications"])
    for key in ("future_leakage", "numeric_aggregates"):
        metrics[key].missing.extend(missing)
    after = digest(db_path, "md5")
    if before != after:
        raise ValueError("MD5 БД изменился во время проверки")
    return dict(sample_status=sample["manifest"].get("status"), sample_counts={k: len(sample[k]) for k in ("posts", "comments", "pairs")},
                note="Маленькая выборка — демо-проверка, не доказательство качества на всех данных. Общий балл не вычисляется.",
                db_md5_before=before, db_md5_after=after, sha256_verified=sample["manifest"]["sha256"],
                missing_inputs=missing, runs=[r["path"] for r in runs], comment_links=comment_counts, history=history,
                conventions=["Для семантических метрик используется замороженное самое широкое coverage-окно; узкое окно его не заменяет.",
                             "Единица отбора — пара (пост, тема); пары и комментарии также проверяются отдельно по теме.",
                             "Нет решения: false negative для recall, unverified для precision/отрицательных пар. Fail имеет приоритет при наблюдаемом нарушении порога.",
                             "coverage.publications/channels/comments — все записи БД в окне; topic_publications — уникальные selected_news. Групповые счётчики — уникальные публикации, не сегменты.",
                             "Автор берётся только из author_id/author_key БД; канал не подменяет автора. Origin пересчитывается по решениям, его истинность оценивается отдельно.",
                             "Проверка времени охватывает сериализованные записи и ссылки, но не доказывает отсутствие скрытого влияния будущего на LLM."],
                metrics={k: m.result() for k, m in metrics.items()})


def write_report(report, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Независимая оценка news-first Pulse", "", report["note"], "", f"Разметка: {report['sample_status']}. SHA256 всех файлов manifest.json проверены.",
             f"MD5 БД до/после: `{report['db_md5_before']}` / `{report['db_md5_after']}`.", "",
             "Воспроизведение: `python3 docs/research/news_pulse_eval.py --db astrafeed.db`", "",
             "Синтетические тесты: `python3 -m unittest discover -s tests/research -p test_news_pulse_eval.py -v`", "",
             "| Метрика | Числитель | Знаменатель | Порог | Статус |", "|---|---:|---:|---|---|"]
    for m in report["metrics"].values():
        lines.append(f"| {m['title']} | {m['numerator']} | {m['denominator']} | {m['threshold'] if m['threshold'] is not None else 'нет'} | {m['status']} |")
    lines += ["", "## Методика", ""] + ["- " + s for s in report["conventions"]]
    lines += ["", "Связи комментариев: `" + json.dumps(report["comment_links"], ensure_ascii=False) + "`.",
              f"Явно помеченная предыстория: {len(report['history'])} вхождений; список в metrics.json.", "", "## Отсутствующие входы", ""]
    lines += ["- " + s for s in report["missing_inputs"]] or ["Нет."]
    for m in report["metrics"].values():
        lines += ["", "## " + m["title"], "", m["note"] or "Ошибки и непроверенные случаи:", ""]
        for kind in ("errors", "missing"):
            for detail in m[kind]:
                lines.append("- " + ("Ошибка: " if kind == "errors" else "Не проверено: ") + json.dumps(detail, ensure_ascii=False))
        if not m["errors"] and not m["missing"]:
            lines.append("Ошибок не обнаружено." if m["denominator"] else "Категория не проверена.")
    (out / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "astrafeed.db")
    parser.add_argument("--sample", type=Path, default=ROOT / "artifacts/news-eval")
    parser.add_argument("--runs", type=Path, default=ROOT / "artifacts/news-pulse")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/news-pulse/eval")
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.sample, args.runs, args.db)
        write_report(report, args.out)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        parser.exit(2, f"Ошибка оценщика: {exc}\n")
    for name, metric in report["metrics"].items():
        print(f"{name}: {metric['numerator']}/{metric['denominator']} {metric['status']}")
    print(f"Отсутствующих входов: {len(report['missing_inputs'])}; отчёт: {args.out}")
    return 0  # fail качества не является аварией измерителя; целостность — код 2.


if __name__ == "__main__":
    raise SystemExit(main())
