"""Render a published agenda in English.

Stories, quotes and comments arrive in the language of their channels. Before a
snapshot is published, every non-English text a reader sees on the agenda and on
its story pages is translated. Titles and explanations are replaced; quotes keep
the original as evidence and gain a translation. Any failure keeps the original.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace

from astrafeed.domain.agenda import (
    Discussion,
    Snapshot,
    StoryCard,
    StoryDetail,
    numbers_in,
)
from astrafeed.ports.agenda import Translator

_log = logging.getLogger(__name__)

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_THOUSANDS = re.compile(r"(?<=\d)[   ,](?=\d{3}(?!\d))")
_IDIOMS = re.compile(r"\b24/7\b")
CHUNK = 12
CACHE_LIMIT = 5000


def needs_translation(text: str) -> bool:
    return bool(text) and _CYRILLIC.search(text) is not None


def _grounded_numbers(text: str, evidence: list[str]) -> bool:
    def canonical(number: str) -> str:
        # Decimal punctuation changes in translation; thousands separators do not.
        return number.replace(",", ".") if re.fullmatch(r"\d+[,.]\d{1,2}", number) else number

    def numbers(value: str) -> set[str]:
        # "$10 000" and "$10,000" are one number; "круглосуточно" becomes "24/7".
        value = _IDIOMS.sub(" ", _THOUSANDS.sub("", value))
        return {canonical(number) for number in numbers_in(value)}

    allowed = {number for quote in evidence for number in numbers(quote)}
    return numbers(text) <= allowed


class EnglishLocalizer:
    def __init__(
        self, translator: Translator, *, chunk: int = CHUNK, timeout_seconds: float = 120
    ) -> None:
        self._translator = translator
        self._chunk = chunk
        self._timeout = timeout_seconds
        self._cache: dict[str, str] = {}

    async def localize(self, snapshot: Snapshot) -> Snapshot:
        shown = {card.story_id for card in snapshot.agenda}
        details = [snapshot.stories[sid] for sid in shown if sid in snapshot.stories]
        texts = [
            *(
                text
                for card in (*snapshot.agenda, *snapshot.upcoming)
                for text in _card_texts(card)
            ),
            *(text for detail in details for text in _detail_texts(detail)),
        ]
        missing = list(dict.fromkeys(t for t in texts if needs_translation(t)))
        missing = [t for t in missing if t not in self._cache]
        if missing:
            try:
                async with asyncio.timeout(self._timeout):
                    await self._translate(missing)
            except Exception as exc:
                _log.warning("agenda translation skipped: %s", type(exc).__name__)
        return replace(
            snapshot,
            agenda=tuple(self._card(card) for card in snapshot.agenda),
            upcoming=tuple(self._card(card) for card in snapshot.upcoming),
            stories={
                sid: self._detail(detail) if sid in shown else detail
                for sid, detail in snapshot.stories.items()
            },
        )

    async def _translate(self, texts: list[str]) -> None:
        chunks = [texts[i : i + self._chunk] for i in range(0, len(texts), self._chunk)]
        results = await asyncio.gather(
            *(self._translator.to_english(chunk) for chunk in chunks), return_exceptions=True
        )
        if len(self._cache) > CACHE_LIMIT:
            self._cache.clear()
        for chunk, result in zip(chunks, results, strict=True):
            if isinstance(result, BaseException):
                _log.warning("agenda translation chunk failed: %s", type(result).__name__)
                continue
            for source, english in zip(chunk, result, strict=False):
                # A reply still in Russian is a failed translation: retry next cycle.
                if english.strip() and not needs_translation(english):
                    self._cache[source] = english.strip()

    def _english(self, text: str, evidence: list[str] | None = None) -> str:
        """Translation of a non-English text, or "" when none is needed or known."""
        translated = self._cache.get(text, "") if needs_translation(text) else ""
        if translated and evidence is not None and not _grounded_numbers(translated, evidence):
            return ""
        return translated

    def _card(self, card: StoryCard) -> StoryCard:
        quotes = [claim.quote for claim in card.claims]
        discussion = card.discussion
        if discussion is not None:
            discussion = self._discussion(discussion)
        return replace(
            card,
            title=self._english(card.title, quotes) or card.title,
            entities=tuple(dict.fromkeys(self._english(e) or e for e in card.entities)),
            explanation=self._english(card.explanation, quotes) or card.explanation,
            claims=tuple(
                replace(claim, translation=self._english(claim.quote, [claim.quote]))
                for claim in card.claims
            ),
            discussion=discussion,
        )

    def _discussion(self, discussion: Discussion) -> Discussion:
        return replace(
            discussion,
            quotes=tuple(
                replace(comment, translation=self._english(comment.text))
                for comment in discussion.quotes
            ),
        )

    def _detail(self, detail: StoryDetail) -> StoryDetail:
        return replace(
            detail,
            card=self._card(detail.card),
            positions=tuple(
                replace(position, translation=self._english(position.quote))
                for position in detail.positions
            ),
        )


def _card_texts(card: StoryCard) -> list[str]:
    texts = [
        card.title,
        card.explanation,
        *card.entities,
        *(claim.quote for claim in card.claims),
    ]
    if card.discussion is not None:
        texts += [comment.text for comment in card.discussion.quotes]
    return texts


def _detail_texts(detail: StoryDetail) -> list[str]:
    return [*_card_texts(detail.card), *(position.quote for position in detail.positions)]
