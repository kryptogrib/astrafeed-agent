"""Compare the displayed evidence of two immutable snapshots, without model calls.

Membership is limited to the agenda and calendar. Added evidence can be a late
arrival; removed evidence can have left the rolling window. Neither is an event
or a retraction. Quote changes describe stored excerpts, not verified post edits.
"""

from dataclasses import asdict

from astrafeed.domain.agenda import PublicationRef, Snapshot, StoryCard
from astrafeed.textkey import normalized_text


def _listed(snapshot: Snapshot) -> dict[str, tuple[StoryCard, str]]:
    return {
        card.story_id: (card, section)
        for section, cards in (("agenda", snapshot.agenda), ("upcoming", snapshot.upcoming))
        for card in cards
    }


def _identity(card: StoryCard, section: str) -> dict:
    return {"story_id": card.story_id, "title": card.title, "section": section}


def _publications(snapshot: Snapshot, card: StoryCard) -> dict[str, PublicationRef]:
    detail = snapshot.stories.get(card.story_id)
    if detail is not None:
        return {pub.publication_id: pub for pub in detail.publications}
    return {}


def _sourcing(card: StoryCard) -> dict | None:
    if card.signals is None:
        return None
    return {
        "confirmation": card.signals.confirmation,
        "attributed_to": sorted(set(card.signals.attributed_to)),
    }


def _claims(card: StoryCard) -> dict[tuple[str, str, str, str], dict]:
    return {
        (claim.link, normalized_text(claim.quote), claim.kind, claim.speaker): {
            "quote": claim.quote,
            "link": claim.link,
            "channel": claim.channel_ref,
            "kind": claim.kind,
            "speaker": claim.speaker,
        }
        for claim in card.claims
    }


def _evidence_change(
    current: Snapshot, baseline: Snapshot, card: StoryCard, old_card: StoryCard
) -> dict:
    pubs, old_pubs = _publications(current, card), _publications(baseline, old_card)
    added = sorted(
        (pubs[key] for key in pubs.keys() - old_pubs.keys()),
        key=lambda pub: (pub.published_at, pub.publication_id),
    )
    current_channels = {pub.channel_ref for pub in pubs.values()}
    old_channels = {pub.channel_ref for pub in old_pubs.values()}
    added_channels = sorted(current_channels - old_channels)
    echoes = (
        {node.channel_ref for node in card.signals.sources if node.echo_of}
        if card.signals is not None
        else None
    )
    changed_quotes = [
        {
            "publication_id": key,
            "channel": pubs[key].channel_ref,
            "link": pubs[key].link,
            "before": old_pubs[key].quote,
            "after": pubs[key].quote,
        }
        for key in sorted(pubs.keys() & old_pubs.keys())
        if normalized_text(pubs[key].quote) != normalized_text(old_pubs[key].quote)
    ]
    sourcing, old_sourcing = _sourcing(card), _sourcing(old_card)
    caveat = card.signals.caveat_drop if card.signals else None
    old_caveat = old_card.signals.caveat_drop if old_card.signals else None
    claims, old_claims = _claims(card), _claims(old_card)
    change = {
        "added_publications": [
            {
                "publication_id": pub.publication_id,
                "channel": pub.channel_ref,
                "link": pub.link,
                "published_at": pub.published_at.isoformat(),
                "quote": pub.quote,
                "published_since_baseline": pub.published_at > baseline.published_at,
            }
            for pub in added
        ],
        "removed_publication_ids": sorted(old_pubs.keys() - pubs.keys()),
        "added_channels": added_channels,
        "removed_channels": sorted(old_channels - current_channels),
        "added_echo_channels": (
            sorted(set(added_channels) & echoes) if echoes is not None else None
        ),
        "changed_quotes": changed_quotes,
        "added_claims": [claims[key] for key in sorted(claims.keys() - old_claims.keys())],
        "removed_claims": [old_claims[key] for key in sorted(old_claims.keys() - claims.keys())],
        "sourcing": (
            {"before": old_sourcing, "after": sourcing} if sourcing != old_sourcing else None
        ),
        "caveat_drop": (
            {
                "before": asdict(old_caveat) if old_caveat else None,
                "after": asdict(caveat) if caveat else None,
            }
            if caveat != old_caveat
            else None
        ),
    }
    if card.story_id not in current.stories or old_card.story_id not in baseline.stories:
        # Missing references are unknown, not evidence of additions/removals.
        # Displayed claims remain comparable without inventing publication IDs.
        for field in (
            "added_publications",
            "removed_publication_ids",
            "added_channels",
            "removed_channels",
            "added_echo_channels",
            "changed_quotes",
        ):
            change[field] = None
    return change


def compare_snapshots(current: Snapshot, baseline: Snapshot) -> dict:
    if baseline.published_at > current.published_at:
        raise ValueError("since_snapshot_id is newer than the target snapshot")
    listed, old_listed = _listed(current), _listed(baseline)
    new_stories = []
    updated_stories = []
    for story_id, (card, section) in listed.items():
        identity = _identity(card, section)
        if story_id not in old_listed:
            new_stories.append(
                {
                    **identity,
                    "previously_known": story_id in baseline.stories,
                }
            )
            continue
        old_card, old_section = old_listed[story_id]
        change = _evidence_change(current, baseline, card, old_card)
        if section != old_section or any(change.values()):
            updated_stories.append(
                {
                    **identity,
                    "previous_section": old_section,
                    **change,
                }
            )
    return {
        "new_stories": new_stories,
        "updated_stories": updated_stories,
        "removed_stories": [
            _identity(card, section)
            for story_id, (card, section) in old_listed.items()
            if story_id not in listed
        ],
    }


def comparison_lines(payload: dict) -> list[str]:
    """Plain English shared by Markdown and escaped HTML renderers."""
    if payload.get("comparison_status") == "baseline_unavailable":
        return ["Comparison baseline unavailable; showing the full current agenda."]
    changes = payload.get("changes")
    if changes is None:
        return []
    lines = [f"Changes since snapshot {payload['compared_to']}."]
    if payload.get("comparison_limitations"):
        lines.append(
            "Some publication details are unavailable; comparison uses available evidence."
        )
    if not any(changes.values()):
        return [*lines, "No changes in comparable listed evidence."]
    for story in changes["new_stories"]:
        note = (
            "already known in the baseline" if story["previously_known"] else "absent from baseline"
        )
        lines.append(f"New to {story['section']}: {story['title']} ({note}).")
    for story in changes["updated_stories"]:
        parts = []
        if story["added_publications"]:
            parts.append(f"{len(story['added_publications'])} publications added")
        if story["added_channels"]:
            parts.append(f"{len(story['added_channels'])} channels added")
        if story["added_echo_channels"]:
            parts.append(f"{len(story['added_echo_channels'])} added channels marked as echoes")
        if story["removed_publication_ids"]:
            parts.append(f"{len(story['removed_publication_ids'])} publications no longer included")
        if story["changed_quotes"]:
            parts.append(f"{len(story['changed_quotes'])} quoted excerpts changed")
        if story["added_claims"] or story["removed_claims"]:
            parts.append("displayed claims changed")
        if story["sourcing"]:
            parts.append("sourcing labels changed")
        if story.get("caveat_drop"):
            parts.append("qualifier-drop signal changed")
        if story["section"] != story["previous_section"]:
            parts.append(f"moved to {story['section']}")
        lines.append(f"Updated: {story['title']} — {', '.join(parts)}.")
    for story in changes["removed_stories"]:
        lines.append(f"No longer listed: {story['title']} (previously in {story['section']}).")
    lines.append(
        "These are report changes; added posts may be older, and omissions are not retractions."
    )
    return lines
