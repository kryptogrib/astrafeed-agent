"""Синтетические проверки независимого оценщика; реальная БД не изменяется."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "docs/research/news_pulse_eval.py"
spec = importlib.util.spec_from_file_location("news_pulse_eval", MODULE)
eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval)

START, END = "2026-09-10T00:00:00+00:00", "2026-09-12T00:00:00+00:00"
WINDOW = {"start": START, "end": END}


def post(i, event="gold", relevant=True):
    return {
        "id": f"p{i}",
        "source_id": i,
        "external_id": str(i),
        "link": f"https://t.me/channel/{i}",
        "timestamp": START,
        "expected": {
            "topics": ["test"],
            "relevant_news": relevant,
            "event_ids": [event],
            "origin": "own",
            "source_role": "editorial",
            "segments": [{"class": "event"}],
        },
    }


def decision(p, group="g"):
    return {
        "link": p["link"],
        "source_id": p["source_id"],
        "external_id": p["external_id"],
        "published_at": p["timestamp"],
        "selected_news": True,
        "topic_mention": True,
        "event_ids": [group],
        "segments": [{"class": "event"}],
        "origin": "own",
        "source_role": "editorial",
        "status": "processed",
    }


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sample = self.root / "sample"
        self.sample.mkdir()
        self.runs = self.root / "runs"
        self.folder = self.runs / "test" / "coverage"
        self.folder.mkdir(parents=True)
        self.db = self.root / "data.db"
        # Только синтетическая БД создаётся writeable — production load_db всегда mode=ro.
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE raw_item(source_id, external_id, timestamp, payload)")
            db.execute("CREATE TABLE comment(comment_key, source_id, ts, link, author_key)")
        self.posts = [post(1), post(2), post(3, "other", False)]
        self.comments = [
            {
                "id": "c1",
                "post_ref": "p1",
                "link": "https://t.me/channel/1?comment=1",
                "expected": {"link_target": "event:gold"},
            }
        ]
        with closing(sqlite3.connect(self.db)) as db, db:
            for p in self.posts:
                db.execute(
                    "INSERT INTO raw_item VALUES(?,?,?,?)",
                    (
                        p["source_id"],
                        p["external_id"],
                        p["timestamp"],
                        json.dumps({"link": p["link"]}),
                    ),
                )
            db.execute(
                "INSERT INTO comment VALUES(?,?,?,?,?)",
                ("c1", 1, START, self.comments[0]["link"], "author"),
            )
        self.pairs = [
            {"id": "positive", "a": "p1", "b": "p2", "same_event": True, "shared_topics": ["test"]},
            {
                "id": "negative",
                "a": "p1",
                "b": "p3",
                "same_event": False,
                "shared_topics": ["test"],
            },
        ]
        self.windows = {
            "topics": {
                "test": {
                    "windows": [
                        dict(id="test-coverage", **WINDOW),
                        dict(id="test-boundary", **WINDOW),
                    ],
                    "boundary_cases": [],
                }
            }
        }
        self.freeze()
        ds = [decision(p, "g" if i < 2 else "h") for i, p in enumerate(self.posts)]
        ds[2]["selected_news"] = False
        ds[2]["event_ids"] = []
        self.decisions = {
            "topic": "test",
            "window": WINDOW,
            "publications": ds,
            "comments": [
                {
                    "comment_key": "c1",
                    "link": self.comments[0]["link"],
                    "published_at": START,
                    "link_target": "event:g",
                }
            ],
            "events": [
                {
                    "event_id": "g",
                    "publications": [p["link"] for p in self.posts[:2]],
                    "n_publications": 2,
                    "n_channels": 2,
                    "n_known_authors": 0,
                    "found_origins": [p["link"] for p in self.posts[:2]],
                    "n_reprints": 0,
                    "n_unknown_origin": 0,
                }
            ],
        }
        self.pulse = {
            "topic": "test",
            "window": WINDOW,
            "coverage": {
                "publications": 3,
                "channels": 3,
                "comments": 1,
                "topic_publications": 2,
                "not_processed": 0,
            },
            "events": [
                {
                    "event_id": "g",
                    "counts": {
                        "events": 1,
                        "publications": 2,
                        "channels": 2,
                        "known_authors": 0,
                        "unknown_authors": 2,
                        "found_origins": 2,
                        "reprints": 0,
                        "unknown_origin": 0,
                    },
                    "members": [{"url": p["link"]} for p in self.posts[:2]],
                }
            ],
        }
        self.write_runs()

    def tearDown(self):
        self.tmp.cleanup()

    def freeze(self):
        for name in ("posts", "comments", "pairs"):
            (self.sample / (name + ".jsonl")).write_text(
                "\n".join(json.dumps(x) for x in getattr(self, name))
            )
        (self.sample / "windows.json").write_text(json.dumps(self.windows))
        (self.sample / "manifest.json").write_text(
            json.dumps(
                {
                    "status": "синтетическая",
                    "db_md5": eval.digest(self.db, "md5"),
                    "sha256": {
                        p.name: eval.digest(p)
                        for p in self.sample.iterdir()
                        if p.name != "manifest.json"
                    },
                }
            )
        )

    def write_runs(self):
        for name in ("decisions", "pulse"):
            (self.folder / (name + ".json")).write_text(json.dumps(getattr(self, name)))

    def result(self):
        return eval.evaluate(self.sample, self.runs, self.db)

    def test_correct_and_database_unchanged(self):
        before = eval.digest(self.db)
        report = self.result()
        for key in (
            "news_precision",
            "news_recall",
            "false_merge",
            "same_event_recall",
            "comment_event_precision",
            "numeric_aggregates",
            "boundary",
            "future_leakage",
        ):
            self.assertEqual(report["metrics"][key]["status"], "pass", key)
        self.assertEqual(before, eval.digest(self.db))
        self.assertEqual(report["metrics"]["brief_grounding"]["status"], "unverified")
        eval.write_report(report, self.root / "out")
        self.assertTrue((self.root / "out/metrics.md").exists())

    def test_database_connection_enforces_read_only_uri(self):
        original = sqlite3.connect
        calls = []

        def capture(database, **kwargs):
            calls.append((database, kwargs))
            return original(database, **kwargs)

        with patch.object(eval.sqlite3, "connect", side_effect=capture):
            eval.load_db(self.db)
        self.assertEqual(calls, [(self.db.resolve().as_uri() + "?mode=ro", {"uri": True})])

    def test_tamper_fails_before_evaluation(self):
        with (self.sample / "posts.jsonl").open("a") as f:
            f.write("\n")
        with self.assertRaisesRegex(ValueError, "sha256"):
            self.result()

    def test_missing_decisions_is_recall_miss_not_success(self):
        (self.folder / "decisions.json").unlink()
        report = self.result()
        self.assertEqual(report["metrics"]["news_recall"]["numerator"], 0)
        self.assertEqual(report["metrics"]["news_recall"]["denominator"], 2)
        self.assertEqual(report["metrics"]["false_merge"]["status"], "unverified")
        self.assertTrue(report["missing_inputs"])
        self.assertEqual(report["comment_links"]["missing"], 1)

    def test_mixed_group_is_false_merge_and_wrong_comment_link(self):
        self.decisions["publications"][2]["event_ids"] = ["g"]
        self.write_runs()
        metrics = self.result()["metrics"]
        self.assertEqual(metrics["false_merge"]["numerator"], 1)
        self.assertEqual(metrics["comment_event_precision"]["numerator"], 0)
        self.assertEqual(metrics["comment_event_precision"]["denominator"], 1)

    def test_abstention_and_other_type_not_in_precision_denominator(self):
        for target, count in (("topic_level", "abstentions"), ("author_thesis", "other_types")):
            self.decisions["comments"][0]["link_target"] = target
            self.write_runs()
            report = self.result()
            self.assertEqual(report["comment_links"][count], 1)
            self.assertEqual(report["metrics"]["comment_event_precision"]["denominator"], 0)

    def test_comment_event_subject_without_id_prefix(self):
        self.comments[0]["expected"] = {"link_target": "event", "subject": "gold"}
        self.freeze()
        self.write_runs()
        metric = self.result()["metrics"]["comment_event_precision"]
        self.assertEqual(metric["numerator"], 1)
        self.assertEqual(metric["denominator"], 1)

    def test_future_link_in_text_and_history(self):
        records = [
            {"link": "https://t.me/channel/9", "published_at": END},
            {"link": "https://t.me/channel/8", "published_at": "2026-09-09T00:00:00Z"},
        ]
        run = {
            "path": "synthetic",
            "window": WINDOW,
            "decisions": {},
            "pulse": {
                "brief": "Источник https://t.me/channel/9",
                "history": [{"link": records[1]["link"]}],
            },
        }
        metric, history = eval.Metric("Время", 0, zero=True), []
        eval.check_temporal(run, records, metric, history)
        self.assertEqual(metric.numerator, 1)
        self.assertEqual(len(history), 1)
        run["pulse"]["history"].append({"link": records[0]["link"]})
        metric = eval.Metric("Время", 0, zero=True)
        eval.check_temporal(run, records, metric, [])
        self.assertEqual(metric.numerator, 2)  # Маркер history не разрешает будущее.

    def test_duplicate_segments_do_not_inflate_publications(self):
        self.pulse["events"][0]["members"].append(self.pulse["events"][0]["members"][0])
        self.pulse["events"][0]["counts"]["publications"] = 3
        self.write_runs()
        errors = self.result()["metrics"]["numeric_aggregates"]["errors"]
        self.assertTrue(
            any(e["path"] == "pulse.g.counts.publications" and e["expected"] == 2 for e in errors)
        )

    def test_boundary_start_included_end_excluded(self):
        self.posts[0]["timestamp"] = END
        self.freeze()
        self.write_runs()
        metrics = self.result()["metrics"]
        self.assertEqual(metrics["boundary"]["status"], "fail")
        self.assertEqual(metrics["boundary"]["errors"][0]["links"], [self.posts[0]["link"]])

    def test_narrower_window_cannot_hide_missing_coverage(self):
        self.decisions["window"] = {"start": START, "end": "2026-09-11T00:00:00Z"}
        self.pulse["window"] = self.decisions["window"]
        self.write_runs()
        metrics = self.result()["metrics"]
        self.assertEqual(metrics["news_recall"]["numerator"], 0)
        self.assertEqual(metrics["news_recall"]["denominator"], 2)

    def test_windows_and_holdout_files_are_optional(self):
        (self.sample / "windows.json").unlink()
        hashes = json.loads((self.sample / "manifest.json").read_text())["sha256"]
        hashes.pop("windows.json", None)
        hashes.pop("holdout.json", None)
        (self.sample / "manifest.json").write_text(
            json.dumps(
                {"status": "синтетическая", "db_md5": eval.digest(self.db, "md5"), "sha256": hashes}
            )
        )
        report = self.result()
        self.assertEqual(report["metrics"]["news_precision"]["denominator"], 2)
        self.assertEqual(report["metrics"]["news_recall"]["denominator"], 2)
        self.assertEqual(report["metrics"]["false_merge"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
