"""A vs B: does a separate author-thesis extractor add specific comment→thesis links?

A is the already-run transfer v2 (no extra theses). B is the same v2 prompt, id
contract and verifier, with accepted extractor theses added. Old transfer sample,
labels, caches and both DBs stay untouched. New candidates and answers go to
artifacts/reaction-subject/transfer/thesis/.

    python3 docs/research/reaction_subject_thesis.py label
    python3 docs/research/reaction_subject_thesis.py estimate
    python3 docs/research/author_thesis_extract.py extract --db astrafeed-transfer.db
    python3 docs/research/reaction_subject_thesis.py build-b
    python3 docs/research/reaction_subject_thesis.py llm --db astrafeed-transfer.db
    python3 docs/research/reaction_subject_thesis.py eval
    python3 docs/research/reaction_subject_thesis.py check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from author_thesis_extract import (  # noqa: E402
    OUT_T,
    OUT_TH,
    accept_theses,
    extract_payload,
    leaks_extract,
    match_gold_to_extracted,
    theses_for_linker,
)
from author_thesis_labels import COMMENT_LINKS, EMPTY_POSTS, POST_THESES, gold_id  # noqa: E402
from reaction_subject import USD_PER_M_IN, USD_PER_M_OUT, _correct, _jsonl, _read, _tokens  # noqa: E402
from reaction_subject_transfer import SLICES, manifest  # noqa: E402
from reaction_subject_v2 import (  # noqa: E402
    OUT_TOKENS,
    PROMPT,
    VERIFY_OUT_TOKENS,
    VERIFY_PROMPT,
    context_for,
    leaks,
    run_llm,
    score,
    v2_arms,
)

OUT_B = OUT_TH / "v2-b"
FROZEN = {
    OUT_T / "labels.jsonl": "ea73cf311ffe637ff74729f2c11a50f3",
    OUT_T / "threads.jsonl": "62a55130e6efdf13277ab277df25f1c5",
    OUT_T / "baseline.jsonl": "d9e284330e4c651e1c45f6edc878c6db",
    OUT_T / "snapshot.json": "b51d098e5d67f1416a3d51cedc99b1ec",
    Path("artifacts/reaction-subject/labels.jsonl"): "c537d7d3e03edcbcebea51158ab0f6eb",
    OUT_T / "v2" / "llm.jsonl": "89326a5efea473e1d14c9e345cfe1e88",
    OUT_T / "v2" / "verify.jsonl": "6057e6800684b7e5cee19a77eef37267",
}


def _sha(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _posts() -> dict[str, dict]:
    return {th["thread"]: th for th in _read(OUT_T / "threads.jsonl")}


def _span(post: str, quote: str) -> tuple[int, int]:
    start = post.find(quote)
    if start < 0:
        raise SystemExit(f"gold quote not in post: {quote[:80]!r}")
    if post.find(quote, start + 1) >= 0:
        raise SystemExit(f"gold quote is ambiguous in post: {quote[:80]!r}")
    end = start + len(quote)
    if post[start:end] != quote:
        raise SystemExit(f"gold span mismatch: {quote[:80]!r}")
    return start, end


def label() -> None:
    posts = _posts()
    gold_posts: list[dict] = []
    by_thread: dict[str, list[dict]] = {url: [] for url in posts}
    for thread, quote, kind, role, origin, rank, disputed, note in POST_THESES:
        th = posts[thread]
        start, end = _span(th["post"]["text"], quote)
        row = {
            "gold_id": gold_id(thread, rank) if rank else gold_id(thread, 0) + ":cited",
            "thread": thread,
            "quote": quote,
            "start": start,
            "end": end,
            "kind": kind,
            "topic_role": role,
            "origin": origin,
            "rank": rank,
            "expected_extract": origin == "author" and 1 <= rank <= 3,
            "overflow": origin == "author" and rank >= 4,
            "disputed": disputed,
            "note": note,
            "status": "preliminary",
        }
        if origin == "cited":
            row["gold_id"] = gold_id(thread, 0) + ":cited"
        by_thread.setdefault(thread, []).append(row)
    for url in EMPTY_POSTS:
        by_thread.setdefault(url, [])
    missing = [url for url in posts if url not in by_thread]
    if missing:
        raise SystemExit(f"posts without a gold decision: {missing}")
    extra = [url for url in by_thread if url not in posts]
    if extra:
        raise SystemExit(f"gold for unknown post: {extra}")
    for url, theses in by_thread.items():
        gold_posts.append(
            {
                "thread": url,
                "topic": posts[url]["topic"],
                "theses": theses,
                "n_author": sum(1 for t in theses if t["origin"] == "author"),
                "n_expected": sum(1 for t in theses if t["expected_extract"]),
                "status": "preliminary",
            }
        )
    gold_posts.sort(key=lambda r: r["thread"])
    comments = []
    old = {r["id"]: r for r in _read(OUT_T / "labels.jsonl")}
    for cid, expected, linkable, basis_c, basis_p, disputed, note in COMMENT_LINKS:
        g = old[cid]
        th = posts[g["thread"]]
        c = next(x for x in th["comments"] if x["id"] == cid)
        if basis_c not in c["text"]:
            raise SystemExit(f"{cid}: basis_comment not in comment")
        if basis_p not in th["post"]["text"]:
            raise SystemExit(f"{cid}: basis_post not in post")
        comments.append(
            {
                "id": cid,
                "thread": g["thread"],
                "old_target": g["target"],
                "old_target_id": g["target_id"],
                "expected_gold_id": expected,
                "linkable": linkable,
                "basis_comment": basis_c,
                "basis_post": basis_p,
                "disputed": disputed or g["disputed"],
                "missing_parent": g["missing_parent"],
                "nontext_parent": g["nontext_parent"],
                "note": note,
                "status": "preliminary",
            }
        )
    if {c["id"] for c in comments} != {i for i, *_ in COMMENT_LINKS}:
        raise SystemExit("comment gold size mismatch")
    OUT_TH.mkdir(parents=True, exist_ok=True)
    _jsonl(OUT_TH / "gold-posts.jsonl", gold_posts)
    _jsonl(OUT_TH / "gold-comments.jsonl", comments)
    summary = {
        "status": "preliminary",
        "posts": len(gold_posts),
        "author_theses": sum(r["n_author"] for r in gold_posts),
        "expected_extract": sum(r["n_expected"] for r in gold_posts),
        "overflow": sum(1 for r in gold_posts for t in r["theses"] if t["overflow"]),
        "cited_not_author": sum(1 for r in gold_posts for t in r["theses"] if t["origin"] == "cited"),
        "empty_posts": sum(1 for r in gold_posts if r["n_author"] == 0),
        "comments": len(comments),
        "linkable": sum(c["linkable"] for c in comments),
        "unlinkable_old_thesis": sum(1 for c in comments if not c["linkable"]),
        "disputed_comments": sum(c["disputed"] for c in comments),
        "note": "agent preliminary gold; not a human holdout",
    }
    (OUT_TH / "gold-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


def gold_author(expected_only: bool = True) -> list[dict]:
    out = []
    for row in _read(OUT_TH / "gold-posts.jsonl"):
        for t in row["theses"]:
            if t["origin"] != "author":
                continue
            if expected_only and not t["expected_extract"]:
                continue
            out.append(t)
    return out


def extracted_by_thread() -> dict[str, list[dict]]:
    return {r["thread"]: r.get("theses") or [] for r in _read(OUT_TH / "extracted.jsonl")}


def build_b() -> None:
    extracted = extracted_by_thread()
    if len(extracted) != len(_posts()):
        raise SystemExit("extracted.jsonl does not cover every transfer thread")
    rows = []
    for th in _read(OUT_T / "threads.jsonl"):
        accepted = extracted[th["thread"]]
        copy = json.loads(json.dumps(th))
        copy["theses"] = theses_for_linker(accepted)
        copy["pipeline_theses"] = th.get("theses") or []
        copy["added_theses"] = True
        rows.append(copy)
    _jsonl(OUT_TH / "threads-b.jsonl", rows)
    n = sum(len(th["theses"]) for th in rows)
    print(json.dumps({"threads": len(rows), "theses_offered": n}))


def estimate() -> None:
    from author_thesis_extract import estimate as estimate_extract

    estimate_extract()
    rows = _read(OUT_T / "threads.jsonl")
    extracted = extracted_by_thread() if (OUT_TH / "extracted.jsonl").exists() else {}
    n = n_in = changed = 0
    for th in rows:
        theses = extracted.get(th["thread"]) or []
        b = {**th, "theses": theses_for_linker(theses)}
        for c in th["comments"]:
            if not c["text"].strip():
                continue
            n += 1
            payload = context_for(b, c)
            n_in += _tokens(PROMPT, payload)
            if payload["theses"]:
                changed += 1
    first = (n_in * USD_PER_M_IN + n * OUT_TOKENS * USD_PER_M_OUT) / 1e6
    verify = (n * 400 * USD_PER_M_IN + n * VERIFY_OUT_TOKENS * USD_PER_M_OUT) / 1e6
    print(
        f"linker B upper: comments={n} changed_context~{changed} first_usd~{first:.4f} "
        f"verify_upper~{verify:.4f}; identical empty-thesis payloads can hit the v2 cache"
    )


def llm_b(db: str, *, pay: bool, max_usd: float) -> None:
    manifest(db)
    if not (OUT_TH / "threads-b.jsonl").exists():
        raise SystemExit("run build-b first")
    # Shared cache with transfer v2: identical payloads (no new theses) are hits,
    # a changed thesis list is a new identity and must be a new call.
    run_llm(db, pay=pay, max_usd=max_usd, src=OUT_TH, dst=OUT_B, cache=OUT_T / "v2" / "cache")
    # run_llm reads src/threads.jsonl; copy B threads there only inside thesis/
    # so we write threads.jsonl next to threads-b for the caller.
    # If the user called us, we already need src/threads.jsonl == threads-b.


def _ensure_b_src() -> None:
    b = OUT_TH / "threads-b.jsonl"
    src = OUT_TH / "threads.jsonl"
    if b.exists():
        src.write_bytes(b.read_bytes())


def _mapping() -> dict[str, str | None]:
    extracted = extracted_by_thread()
    mapping: dict[str, str | None] = {}
    for row in _read(OUT_TH / "gold-posts.jsonl"):
        mapping.update(match_gold_to_extracted(row["theses"], extracted.get(row["thread"]) or []))
    return mapping


def _specific_ok(pred: dict, gold: dict, mapping: dict[str, str | None]) -> bool:
    if not gold.get("linkable") or not gold.get("expected_gold_id"):
        return False
    want = mapping.get(gold["expected_gold_id"])
    if not want:
        return False
    return pred.get("target") == "author_thesis" and pred.get("target_id") == want


def _pred_status(pred: dict | None) -> str:
    if pred is None:
        return "cache_miss"
    return pred.get("status") or "ok"


def evaluate() -> None:
    old = [r for r in _read(OUT_T / "labels.jsonl") if r["target"] != "skip"]
    comments = _read(OUT_TH / "gold-comments.jsonl")
    mapping = _mapping()
    a_arms = v2_arms(OUT_T / "v2")
    b_arms = v2_arms(OUT_B)
    arms = {
        "A v2 context+id+verify": a_arms["v2 context+id+verify"],
        "B v2 context+id+verify": b_arms["v2 context+id+verify"],
        "A v2 context+id": a_arms["v2 context+id"],
        "B v2 context+id": b_arms["v2 context+id"],
    }
    extract_rows = _read(OUT_TH / "extracted.jsonl")
    extraction = _extraction_score(extract_rows, mapping)
    thesis_metrics = {
        name: _thesis_score(preds, comments, mapping) for name, preds in arms.items()
    }
    event_metrics = {name: score(preds, old) for name, preds in arms.items()}
    slices = {}
    for part, keep in SLICES.items():
        gold = [g for g in comments if keep({**g, "disputed": g["disputed"], "kind": "n/a",
                                               "missing_parent": g["missing_parent"],
                                               "nontext_parent": g["nontext_parent"]})]
        # SLICES uses kind/news — skip kind slices for comment gold
        if part in ("news", "topic_shift"):
            continue
        slices[part] = {name: _thesis_score(preds, gold, mapping) for name, preds in arms.items()}
    changes = _changes(arms["A v2 context+id+verify"], arms["B v2 context+id+verify"], comments, mapping, old)
    result = {
        "kind": "regression_experiment",
        "extraction": extraction,
        "thesis": thesis_metrics,
        "event_regression": {
            name: {
                k: sc.get(k)
                for k in (
                    "pred_event_ok",
                    "pred_event",
                    "gold_event_found",
                    "gold_event",
                    "false_event",
                    "claim_correct",
                    "claim_wrong",
                    "recall",
                )
            }
            for name, sc in event_metrics.items()
        },
        "slices": slices,
        "changes": changes,
    }
    lines = _render(result, extract_rows, comments, mapping, arms, old)
    OUT_TH.mkdir(parents=True, exist_ok=True)
    (OUT_TH / "eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    (OUT_TH / "eval.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def _extraction_score(rows: list[dict], mapping: dict[str, str | None]) -> dict:
    gold = _read(OUT_TH / "gold-posts.jsonl")
    expected = [t for r in gold for t in r["theses"] if t["expected_extract"]]
    overflow = [t for r in gold for t in r["theses"] if t["overflow"]]
    cited = [t for r in gold for t in r["theses"] if t["origin"] == "cited"]
    extracted_ids = {t["thesis_id"] for r in rows for t in r.get("theses") or []}
    matched_expected = sum(1 for t in expected if mapping.get(t["gold_id"]))
    matched_overflow = sum(1 for t in overflow if mapping.get(t["gold_id"]))
    matched_cited = sum(1 for t in cited if mapping.get(t["gold_id"]))
    used = {mapping[t["gold_id"]] for t in expected + overflow if mapping.get(t["gold_id"])}
    extras = extracted_ids - used
    available_comments = 0
    comments = _read(OUT_TH / "gold-comments.jsonl")
    for c in comments:
        if c["linkable"] and c["expected_gold_id"] and mapping.get(c["expected_gold_id"]):
            available_comments += 1
    return {
        "posts": len(rows),
        "extracted": len(extracted_ids),
        "expected": len(expected),
        "hit_expected": matched_expected,
        "missed_expected": len(expected) - matched_expected,
        "overflow_gold": len(overflow),
        "overflow_also_extracted": matched_overflow,
        "cited_extracted": matched_cited,
        "extras": len(extras),
        "available_linkable_comments": available_comments,
        "linkable_comments": sum(1 for c in comments if c["linkable"]),
        "cache_miss_posts": sum(1 for r in rows if r.get("status") == "cache_miss"),
        "rejected_spans": sum(len(r.get("rejected") or []) for r in rows),
    }


def _thesis_score(preds: dict[str, dict], comments: list[dict], mapping: dict[str, str | None]) -> dict:
    m: Counter = Counter()
    for g in comments:
        p = preds.get(g["id"]) or {}
        status = _pred_status(preds.get(g["id"]))
        m["n"] += 1
        m[f"status_{status}"] += 1
        if status == "cache_miss":
            m["cache_miss"] += 1
            continue
        if status in ("invalid", "unverified"):
            m["unprocessed"] += 1
        specific = _specific_ok(p, g, mapping)
        class_only = p.get("target") == "author_thesis" and not specific
        claimed_thesis = p.get("target") == "author_thesis" and bool(p.get("target_id"))
        m["specific_ok"] += specific
        m["class_only"] += class_only
        m["thesis_id_claimed"] += claimed_thesis
        m["thesis_id_wrong"] += claimed_thesis and not specific
        m["abstained"] += p.get("target") in (None, "unclear") or status == "no_id"
        if g.get("linkable") and g.get("expected_gold_id"):
            m["expected_links"] += 1
            m["available"] += bool(mapping.get(g["expected_gold_id"]))
            m["available_hit"] += specific
        m["old_thesis_class"] += g.get("old_target") == "author_thesis"
    n = m["expected_links"]
    claimed = m["thesis_id_claimed"]
    return dict(
        m,
        precision=round(m["specific_ok"] / claimed, 3) if claimed else None,
        recall_linkable=round(m["specific_ok"] / n, 3) if n else None,
        recall_available=round(m["available_hit"] / m["available"], 3) if m["available"] else None,
    )


def _changes(a: dict, b: dict, comments: list[dict], mapping: dict, old: list[dict]) -> dict:
    old_by = {r["id"]: r for r in old}
    text = {}
    for th in _read(OUT_T / "threads.jsonl"):
        for c in th["comments"]:
            text[c["id"]] = " ".join(c["text"].split())[:120]
    new_ok, new_wrong, lost = [], [], []
    event_reg = []
    for g in comments:
        pa, pb = a.get(g["id"]) or {}, b.get(g["id"]) or {}
        oka, okb = _specific_ok(pa, g, mapping), _specific_ok(pb, g, mapping)
        wa = pa.get("target") == "author_thesis" and pa.get("target_id") and not oka
        wb = pb.get("target") == "author_thesis" and pb.get("target_id") and not okb
        row = f"«{text.get(g['id'], '')}» gold={g.get('expected_gold_id')} A={pa.get('target')}/{pa.get('target_id')}/{pa.get('status')} B={pb.get('target')}/{pb.get('target_id')}/{pb.get('status')}"
        if okb and not oka:
            new_ok.append(row)
        elif wb and not wa:
            new_wrong.append(row)
        elif oka and not okb:
            lost.append(row)
    for g in old:
        if g["target"] != "event":
            continue
        pa, pb = a.get(g["id"]) or {}, b.get(g["id"]) or {}
        if _correct(pa, g) != _correct(pb, g) or pa.get("target") != pb.get("target"):
            event_reg.append(
                f"«{text.get(g['id'], '')}» gold_event={g.get('target_id')} A={pa.get('target')}/{pa.get('status')} B={pb.get('target')}/{pb.get('status')}"
            )
    return {"new_specific_ok": new_ok, "new_specific_wrong": new_wrong, "lost_specific": lost, "event_changed": event_reg}


def _render(result: dict, extract_rows: list[dict], comments: list[dict], mapping: dict, arms: dict, old: list[dict]) -> list[str]:
    ex = result["extraction"]
    lines = [
        "# Author-thesis extraction — regression experiment (not a holdout)",
        "",
        "Transfer sample already seen at labelling and after v2. Labels are preliminary.",
        "Old labels.jsonl was not edited. A specific link needs a matched gold claim, not the class name.",
        "",
        "## Извлечение",
        "",
        f"- постов: {ex['posts']}; извлечено тезисов: {ex['extracted']}",
        f"- ожидаемых авторских (rank 1–3): верных {ex['hit_expected']} / {ex['expected']}, пропусков {ex['missed_expected']}",
        f"- overflow тоже извлечён: {ex['overflow_also_extracted']} / {ex['overflow_gold']}",
        f"- чужих/цитируемых извлечено: {ex['cited_extracted']}; лишних: {ex['extras']}",
        f"- доступность нужного тезиса для связывателя: {ex['available_linkable_comments']} / {ex['linkable_comments']}",
        "",
        "## Связи с конкретным тезисом",
        "",
        "| arm | n | specific_ok | claimed | wrong | class_only | precision | recall_linkable | recall_available | unprocessed | cache_miss |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, sc in result["thesis"].items():
        lines.append(
            f"| {name} | {sc.get('n', 0)} | {sc.get('specific_ok', 0)} | {sc.get('thesis_id_claimed', 0)} | "
            f"{sc.get('thesis_id_wrong', 0)} | {sc.get('class_only', 0)} | {sc.get('precision')} | "
            f"{sc.get('recall_linkable')} | {sc.get('recall_available')} | {sc.get('unprocessed', 0)} | "
            f"{sc.get('cache_miss', 0)} |"
        )
    lines += ["", "## Срезы (B vs A, context+id+verify)", ""]
    lines += ["| срез | n | A specific | B specific | A recall | B recall |", "|---|---|---|---|---|---|"]
    for part, arms_sc in result["slices"].items():
        a, b = arms_sc["A v2 context+id+verify"], arms_sc["B v2 context+id+verify"]
        lines.append(
            f"| {part} | {a.get('n', 0)} | {a.get('specific_ok', 0)} | {b.get('specific_ok', 0)} | "
            f"{a.get('recall_linkable')} | {b.get('recall_linkable')} |"
        )
    lines += ["", "## Регрессия event-связей (старые метки)", ""]
    lines += ["| arm | event верно/заявлено | найдено/в эталоне | ложных event | общая полнота |", "|---|---|---|---|---|"]
    for name, sc in result["event_regression"].items():
        lines.append(
            f"| {name} | {sc.get('pred_event_ok')}/{sc.get('pred_event')} | "
            f"{sc.get('gold_event_found')}/{sc.get('gold_event')} | {sc.get('false_event')} | {sc.get('recall')} |"
        )
    ch = result["changes"]
    lines += ["", "## Конкретные изменения A → B", ""]
    for key, title in (
        ("new_specific_ok", "Новые верные конкретные связи"),
        ("new_specific_wrong", "Новые ложные конкретные связи"),
        ("lost_specific", "Потерянные конкретные связи"),
        ("event_changed", "Изменившиеся event-связи"),
    ):
        rows = ch[key]
        lines += [f"### {title} ({len(rows)})", *([f"- {r}" for r in rows] or ["- нет"]), ""]
    a_run = json.loads((OUT_T / "v2" / "run.json").read_text()) if (OUT_T / "v2" / "run.json").exists() else {}
    b_run = json.loads((OUT_B / "run.json").read_text()) if (OUT_B / "run.json").exists() else {}
    e_run = json.loads((OUT_TH / "extract-run.json").read_text()) if (OUT_TH / "extract-run.json").exists() else {}
    lines += [
        "## Стоимость и задержка",
        "",
        f"- extract: calls={e_run.get('calls')} hits={e_run.get('cache_hits')} usd={e_run.get('spent_usd')} llm_s={e_run.get('llm_seconds')}",
        f"- A (cached v2): hits={a_run.get('cache_hits')} usd={a_run.get('spent_usd')} (повторное чтение, не новый расход)",
        f"- B: calls={b_run.get('calls')} hits={b_run.get('cache_hits')} usd={b_run.get('spent_usd')} llm_s={b_run.get('llm_seconds')}",
        "",
    ]
    return lines


def check() -> None:
    problems = []
    posts = _posts()
    for th in posts.values():
        problems += [f"extract payload: {x}" for x in leaks_extract(th, extract_payload(th))]
    if (OUT_TH / "extracted.jsonl").exists():
        for row in _read(OUT_TH / "extracted.jsonl"):
            th = posts[row["thread"]]
            post = th["post"]["text"]
            for t in row.get("theses") or []:
                if post[t["start"] : t["end"]] != t["quote"]:
                    problems.append(f"span {row['thread']} {t['thesis_id']}")
            raw = json.dumps(row.get("raw") or {})
            for c in th["comments"]:
                if len(c["text"]) >= 24 and c["text"] in json.dumps(extract_payload(th), ensure_ascii=False):
                    problems.append(f"comment in extract payload {c['id']}")
    if (OUT_TH / "threads-b.jsonl").exists():
        for th in _read(OUT_TH / "threads-b.jsonl"):
            ids = {t["thesis_id"] for t in th["theses"]}
            for c in th["comments"]:
                bad = leaks(th, c, context_for(th, c))
                problems += [f"B leak {c['id']}: {x}" for x in bad]
            if (OUT_B / "llm.jsonl").exists():
                pass
        if (OUT_B / "llm.jsonl").exists():
            for r in _read(OUT_B / "llm.jsonl"):
                if r.get("target") == "author_thesis" and r.get("target_id"):
                    # foreign id already invalid in check_item; record if status ok with unknown id
                    th = next(t for t in _read(OUT_TH / "threads-b.jsonl") if any(c["id"] == r["id"] for c in t["comments"]))
                    local = {t["thesis_id"] for t in th["theses"]}
                    if r.get("status") == "ok" and r["target_id"] not in local:
                        problems.append(f"accepted foreign thesis id {r['id']} {r['target_id']}")
    for path, expected in FROZEN.items():
        if not path.exists():
            problems.append(f"missing frozen {path}")
        elif _sha(path) != expected:
            problems.append(f"frozen hash changed {path}: {_sha(path)} != {expected}")
    if problems:
        raise SystemExit("\n".join(problems[:30]))
    print("ok checks")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("label")
    sub.add_parser("estimate")
    sub.add_parser("build-b")
    r = sub.add_parser("llm")
    r.add_argument("--db", default="astrafeed-transfer.db")
    r.add_argument("--pay", action="store_true")
    r.add_argument("--max-usd", type=float, default=0.20)
    sub.add_parser("eval")
    sub.add_parser("check")
    args = ap.parse_args()
    if args.cmd == "label":
        label()
    elif args.cmd == "estimate":
        estimate()
    elif args.cmd == "build-b":
        build_b()
    elif args.cmd == "llm":
        _ensure_b_src()
        llm_b(args.db, pay=args.pay, max_usd=args.max_usd)
    elif args.cmd == "eval":
        evaluate()
    elif args.cmd == "check":
        check()


if __name__ == "__main__":
    main()
