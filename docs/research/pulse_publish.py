"""Research Pulse, step 3: the publishable ETH set of one thread, from the v3 model labels.

python3 docs/research/pulse_publish.py astrafeed.db artifacts/entity-candidates \
        https://t.me/rawa_imagination/21055 ethereum,eth,ether artifacts/pulse-eth/thread-21055/v3

Reads <run>/labels.json (model output, never modified) and <run>/demo/corrections.json (agent review,
kept separate). Replies flagged relevant_not_grounded on the MODEL labels are held for review and
left out of the published set whatever the corrections say. Corrections then change fields of the
remaining replies; the corrected labels are checked again, and any new flag stops the script.
Grounding is recomputed with the current topic_mentions, so the published set may differ from what the
model saw. <run>/request.json is never rewritten; <run>/demo/grounding.json records the mentions of the
model's input (read back from request.json, checked against meta.json), the mentions used for publication,
GROUNDING_VERSION and the replies whose grounding changed.
Writes <run>/demo/published.json, published.md and grounding.json. No LLM call; database opened read-only.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pulse_classify_thread import (GROUNDING_VERSION, check, load_thread, saved_input, sha,  # noqa: E402
                                   thread_comments, thread_texts, topic_mentions)


def main(db_path, det_dir, link, topic, run_dir):
    run = Path(run_dir)
    sid, pid, post, rows = load_thread(db_path, link)
    mentions = topic_mentions(det_dir, sid, pid, tuple(topic.split(",")), thread_texts(post, rows))
    comments = thread_comments(rows)
    model = json.loads((run / "labels.json").read_text())
    corr_path = run / "demo" / "corrections.json"
    corr = json.loads(corr_path.read_text()) if corr_path.exists() else {"corrections": []}

    # held: decided on the model's own labels, so a correction cannot quietly bring a reply back
    held = set(check(model, comments, mentions, post).get("relevant_not_grounded", []))
    _, seen = saved_input(run)
    held_then = set(check(model, comments, seen, post).get("relevant_not_grounded", []))
    changed = sorted(k for k in set(seen) | set(mentions) if seen.get(k) != mentions.get(k))
    grounding = {
        "model_input": {"request": str(run / "request.json"),
                        "input_sha256": json.loads((run / "meta.json").read_text())["input_sha256"],
                        "mentions": seen, "held_if_published_on_it": sorted(held_then)},
        "publication": {"grounding_version": GROUNDING_VERSION,
                        "classifier_sha256": sha((Path(__file__).parent / "pulse_classify_thread.py").read_text()),
                        "mentions": mentions, "held": sorted(held)},
        "mentions_changed": changed,
        "released_by_new_grounding": sorted(held_then - held), "held_by_new_grounding": sorted(held - held_then)}

    labels = copy.deepcopy(model)
    by_id = {str(x["id"]): x for x in labels}
    applied = []
    for c in corr["corrections"]:
        x = by_id[c["id"]]
        for f, ch in c["changes"].items():
            if x.get(f) != ch["model"] and not (f == "context_ids" and [str(e) for e in x.get(f) or []] == ch["model"]):
                raise SystemExit(f"{c['id']}.{f}: model value changed since the review ({x.get(f)!r} != {ch['model']!r})")
            x[f] = ch["corrected"]
        applied.append(c["id"])
    # held replies keep the model's flags; only the published part must come out clean
    left = {k: v for k, v in ((k, [e for e in v if e.split(":")[0] not in held])
                              for k, v in check(labels, comments, mentions, post).items()) if v}
    if left:
        raise SystemExit(f"corrected labels still have flags: {left}")

    text_of = {c["id"]: c["text"] for c in comments}
    link_of = {str(r["comment_id"]): r["link"] for r in rows}
    corrected = {c["id"]: c for c in corr["corrections"]}
    published = [dict(x, link=link_of.get(str(x["id"])), corrected=str(x["id"]) in corrected,
                      borderline=corrected.get(str(x["id"]), {}).get("borderline", False))
                 for x in labels if x.get("relevance") == "relevant" and str(x["id"]) not in held]
    held_rows = [dict(x, link=link_of.get(str(x["id"])), text=text_of.get(str(x["id"])))
                 for x in model if str(x["id"]) in held]
    out = {"link": link, "model_labels": str(run / "labels.json"), "corrections": str(corr_path),
           "reviewer": corr.get("reviewer"), "published": published,
           "held_for_review": {"reason": "relevant_not_grounded на метках модели", "labels": held_rows}}
    (run / "demo").mkdir(exist_ok=True)
    (run / "demo" / "published.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    (run / "demo" / "grounding.json").write_text(json.dumps(grounding, ensure_ascii=False, indent=1) + "\n")

    cell = lambda s: (s or "").replace("|", "/")
    md = [f"# Публикуемый набор ({topic}): {link}", "",
          f"Исходная разметка модели: `{run / 'labels.json'}` (не меняется).",
          f"Исправления: `{corr_path}` — {corr.get('reviewer') or 'нет'}. Помечены «испр.».",
          f"Опубликовано {len(published)}, отложено на проверку {len(held_rows)} (флаг relevant_not_grounded).",
          f"Опора публикации: `{GROUNDING_VERSION}`. " + (
              "Совпадает с опорой во входе модели." if not changed else
              f"Отличается от входа модели (`request.json`, не меняется) у: {', '.join(changed)}; "
              f"по опоре входа было бы отложено {len(held_then)}. Подробно — `demo/grounding.json`."), "",
          "| id | aspect | kind | пересказ | цитата | испр. |", "|---|---|---|---|---|---|"]
    for x in published:
        md.append(f"| [{x['id']}]({x['link']}) | {x.get('aspect')} | {x.get('kind')} | {cell(x.get('summary'))} | "
                  f"{cell(x.get('quote'))} | {'да' if x['corrected'] else ''}{', погран.' if x['borderline'] else ''} |")
    md += ["", "## Отложено на проверку", "", "| id | модель: relevance/aspect | пересказ модели | текст |",
           "|---|---|---|---|"]
    for x in held_rows:
        md.append(f"| [{x['id']}]({x['link']}) | {x.get('relevance')}/{x.get('aspect')} | {cell(x.get('summary'))} | "
                  f"{cell((x.get('text') or '')[:120])} |")
    (run / "demo" / "published.md").write_text("\n".join(md) + "\n")
    print(f"{link}: published {len(published)}, held {len(held_rows)}, corrections applied {len(applied)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
