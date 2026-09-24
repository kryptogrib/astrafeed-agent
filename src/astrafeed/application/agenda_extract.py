"""Open extraction with quote verification and time-independent reuse."""

from __future__ import annotations

import re

from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    ExtractionResult,
    Fragment,
    PublicationVersion,
    analysis_reuse_key,
    resolve_quote_span,
    resolve_relative_when,
)
from astrafeed.domain.spend_budget import BudgetExceeded
from astrafeed.ports.agenda import AgendaStore, OpenExtractor


def claim_is_noise(quote: str, *, is_ad: bool = False) -> bool:
    """Reject snippets that cannot support a story card or channel vote."""
    if is_ad:
        return True
    stripped = quote.strip()
    if len(re.findall(r"[^\W_]+", stripped, flags=re.UNICODE)) < 4:
        return True
    lowered = stripped.casefold()
    if lowered.startswith(("ранее:", "previously:", "топ дня", "дайджест дня")):
        return True
    bullet_count = len(re.findall(r"(?m)^\s*[-•]\s+", stripped))
    return bullet_count >= 2 and not re.search(r"[.!?](?:\s|$)", stripped)


def verify_fragment(text: str, fragment: Fragment) -> Fragment:
    claims: list[Claim] = []
    for claim in fragment.claims:
        span = resolve_quote_span(text, claim.quote, claim.start, claim.end)
        if span is None:
            continue
        start, end = span
        if claim_is_noise(text[start:end], is_ad=fragment.is_ad or claim.is_ad):
            continue
        claims.append(
            Claim(
                kind=claim.kind,
                speaker=claim.speaker,
                quote=text[start:end],
                start=start,
                end=end,
                is_ad=claim.is_ad,
                dates=claim.dates,
                numbers=claim.numbers,
            )
        )
    return Fragment(
        text=fragment.text,
        start=fragment.start,
        end=fragment.end,
        is_ad=fragment.is_ad,
        entities=fragment.entities,
        claims=tuple(claims),
    )


def resolve_instance(result: ExtractionResult, published_at) -> ExtractionResult:
    fragments = []
    for fragment in result.fragments:
        claims = []
        for claim in fragment.claims:
            claims.append(
                Claim(
                    kind=claim.kind,
                    speaker=claim.speaker,
                    quote=claim.quote,
                    start=claim.start,
                    end=claim.end,
                    is_ad=claim.is_ad,
                    dates=tuple(resolve_relative_when(d, published_at) for d in claim.dates),
                    numbers=claim.numbers,
                )
            )
        fragments.append(
            Fragment(
                text=fragment.text,
                start=fragment.start,
                end=fragment.end,
                is_ad=fragment.is_ad,
                entities=fragment.entities,
                claims=tuple(claims),
            )
        )
    return ExtractionResult(
        reuse_key=result.reuse_key,
        text_hash=result.text_hash,
        classifier_version=result.classifier_version,
        status=result.status,
        fragments=tuple(fragments),
        error=result.error,
    )


def _with_verified_status(
    result: ExtractionResult, fragments: tuple[Fragment, ...]
) -> ExtractionResult:
    has_claim = any(fragment.claims for fragment in fragments)
    status = result.status
    if result.status != "error":
        status = "ok" if has_claim else "empty"
    return ExtractionResult(
        reuse_key=result.reuse_key,
        text_hash=result.text_hash,
        classifier_version=result.classifier_version,
        status=status,
        fragments=fragments,
        error=result.error,
    )


async def analyze_publication(
    store: AgendaStore,
    extractor: OpenExtractor,
    publication: PublicationVersion,
) -> ExtractionResult:
    reuse_key = analysis_reuse_key(publication.text_hash, CLASSIFIER_VERSION)
    cached = await store.get_extraction(reuse_key)
    if cached is None:
        try:
            raw = await extractor.extract(publication.text)
        except BudgetExceeded:
            raise
        except Exception as exc:
            failed = ExtractionResult(
                reuse_key=reuse_key,
                text_hash=publication.text_hash,
                classifier_version=CLASSIFIER_VERSION,
                status="error",
                error=type(exc).__name__,
            )
            await store.enqueue(publication.publication_id, "extract_error")
            return failed
        verified = tuple(verify_fragment(publication.text, fragment) for fragment in raw.fragments)
        stored = _with_verified_status(raw, verified)
        stored = ExtractionResult(
            reuse_key=reuse_key,
            text_hash=publication.text_hash,
            classifier_version=CLASSIFIER_VERSION,
            status=stored.status,
            fragments=stored.fragments,
            error=stored.error,
        )
        await store.save_extraction(stored)
        cached = stored
    if cached.status == "error":
        await store.enqueue(publication.publication_id, "extract_error")
        return cached
    return resolve_instance(cached, publication.published_at)
