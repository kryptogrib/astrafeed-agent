"""Link a comment to an event, thesis, project, other subject, or topic-level."""

from __future__ import annotations

import re
from typing import Any

from news_pulse_load import Publication, fold

TARGETS = ("event", "author_thesis", "project", "other_subject", "topic_level")
# every basis the linker may emit, with the only target it justifies; grounding rejects anything else
BASES: dict[str, str] = {
    "предмет реплики — сторонний сервис/коллекция экосистемы, не событие темы": "other_subject",
    "комментарий повторяет формулировку события": "event",
    "реплика опирается на формулировку авторского тезиса": "author_thesis",
    "жалоба на сторонний сервис экосистемы, не на событие поста": "other_subject",
    "реплика к посту с одним событием по теме и тому же предмету": "event",
    "реплика по предмету единственного события родительского сегмента": "event",
    "вопрос или оценка по проекту в целом, не по конкретной новости": "project",
    "совпадение темы недостаточно, связь со событием не установлена": "topic_level",
}
OTHER_HINT = re.compile(r"(?i)\bnft\b|сайт|site|маркетплейс|коллекц|аукцион|минт|кошельк|wallet|zaddr|zecvisions")
SERVICE_COMPLAINT = re.compile(
    r"(?i)жалоб|не открыв|скам|мусор|сайт|маркетплейс|коллекц|\bnft\b|аукцион|"
    r"zaddr|zecvisions|теннис|биткоин|биток"
)
NETWORK_HINT = re.compile(r"(?i)сеть|network|нод|блокчейн|shield|шилдинг")
PRICE_REACTION = re.compile(r"(?i)лонг|шорт|фомо|покупа|прода|цена|гандон|450|1400")
PROJECT_HINT = re.compile(r"(?i)кошельк|wallet|икс(?:ов|а)?|после роста|по \d")
DEICTIC = re.compile(r"(?i)\b(он|это|этот|гандон|монет\w*)\b")


def _overlap(a: str, b: str) -> bool:
    aa, bb = fold(a or ""), fold(b or "")
    if len(aa) < 12 or len(bb) < 12:
        return False
    return aa in bb or bb in aa


def _event_blob(event: dict[str, Any]) -> str:
    members = event.get("members") or []
    return " ".join(
        [str(event.get("headline") or ""), str(event.get("object") or "")]
        + [str(m.get("quote") or "") for m in members]
    )


def _parent_events(comment: Publication, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = {comment.parent_id, comment.thread_id}
    return [
        e
        for e in events
        if any((m.get("publication_id") in keys) for m in e.get("members") or [])
    ]


def _reply_chain_text(comment: Publication, thread_comments: list[Publication] | None) -> str:
    if not thread_comments:
        return comment.text or ""
    by_id = {c.pub_id: c for c in thread_comments}
    parts = [comment.text or ""]
    cur = comment
    seen: set[str] = {comment.pub_id}
    for _ in range(8):
        pid = cur.parent_id
        if not pid or pid not in by_id or pid in seen:
            break
        cur = by_id[pid]
        seen.add(cur.pub_id)
        parts.append(cur.text or "")
    return "\n".join(parts)


def _about_event_subject(text: str, event: dict[str, Any]) -> bool:
    blob = _event_blob(event)
    if _overlap(text, blob):
        return True
    obj = fold(str(event.get("object") or event.get("headline") or ""))
    folded = fold(text)
    if obj and len(obj) >= 4 and obj in folded and not OTHER_HINT.search(text):
        return True
    if PRICE_REACTION.search(text) and re.search(r"(?i)\$|\d{3,}|цена|1400|zec|eth", blob):
        return True
    return False


def _row(target: str, comment: Publication, *, target_id: str | None = None, basis: str) -> dict[str, Any]:
    assert BASES.get(basis) == target, basis
    text = (comment.text or "").strip()
    return {
        "target": target,
        "target_id": target_id,
        "text": _clip_words(text, 240),
        "basis": basis,
        "url": comment.url,
        "quote": _clip_words(text, 180),
    }


def _clip_words(text: str, limit: int) -> str:
    """Cut at a word boundary so a number is never split: "100" must not become a quoted "1"."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if not text[limit].isspace() and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip()


def link_comment(
    comment: Publication,
    events: list[dict[str, Any]],
    theses: list[dict[str, Any]] | None = None,
    post_observations: list[dict[str, Any]] | None = None,
    thread_comments: list[Publication] | None = None,
) -> dict[str, Any]:
    """Doubt defaults to topic_level. Time+topic overlap is not enough."""
    theses = theses or []
    post_observations = post_observations or []
    text = comment.text or ""
    chain = _reply_chain_text(comment, thread_comments)
    parent_events = _parent_events(comment, events)
    topic_post_obs = [
        o
        for o in post_observations
        if o.get("publication_id") in {comment.parent_id, comment.thread_id}
        and o.get("kind") in {"event", "author_position"}
        and o.get("segment_role") not in {"quote_line", "footer", "promo", "link"}
    ]

    if SERVICE_COMPLAINT.search(text) and not NETWORK_HINT.search(text):
        if not any(_overlap(text, _event_blob(e)) for e in parent_events):
            return _row("other_subject", comment, basis="предмет реплики — сторонний сервис/коллекция экосистемы, не событие темы")

    for event in events:
        blob = _event_blob(event)
        if _overlap(text, blob):
            return _row(
                "event",
                comment,
                target_id=event.get("event_id"),
                basis="комментарий повторяет формулировку события",
            )

    for thesis in theses:
        if _overlap(text, str(thesis.get("quote") or thesis.get("text") or "")) or _overlap(
            chain, str(thesis.get("quote") or thesis.get("text") or "")
        ):
            return _row(
                "author_thesis",
                comment,
                target_id=thesis.get("obs_id"),
                basis="реплика опирается на формулировку авторского тезиса",
            )

    if len(parent_events) == 1:
        ev = parent_events[0]
        if SERVICE_COMPLAINT.search(text) and not _about_event_subject(text, ev):
            return _row("other_subject", comment, basis="жалоба на сторонний сервис экосистемы, не на событие поста")
        if _about_event_subject(text, ev) or (
            DEICTIC.search(text) and PRICE_REACTION.search(text) and not SERVICE_COMPLAINT.search(text)
        ):
            return _row(
                "event",
                comment,
                target_id=ev.get("event_id"),
                basis="реплика к посту с одним событием по теме и тому же предмету",
            )

    post_events = [o for o in topic_post_obs if o.get("kind") == "event"]
    if len(parent_events) == 0 and len(post_events) == 1 and _about_event_subject(text, {"headline": post_events[0].get("quote"), "object": post_events[0].get("object"), "members": [post_events[0]]}):
        return _row(
            "event",
            comment,
            target_id=None,
            basis="реплика по предмету единственного события родительского сегмента",
        )

    if PROJECT_HINT.search(text) and not SERVICE_COMPLAINT.search(text):
        return _row("project", comment, basis="вопрос или оценка по проекту в целом, не по конкретной новости")

    return _row("topic_level", comment, basis="совпадение темы недостаточно, связь со событием не установлена")
