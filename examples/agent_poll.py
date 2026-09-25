"""Poll the free AstraFeed A2MCP service with a client-owned snapshot cursor."""

import argparse
from pathlib import Path

import httpx

ENDPOINT = "https://cutememe.lol/a2mcp/astrafeed"
DEFAULT_CURSOR = Path.home() / ".cache" / "astrafeed" / "agent_poll_snapshot_id"


def _card_line(card: dict) -> str:
    signals = card.get("signals") or {}
    price = signals.get("price") or {}
    confirmation = signals.get("confirmation")
    verdict = price.get("verdict")
    return (
        f"{card['title']} | confirmation={confirmation if confirmation is not None else 'null'}"
        f" | price.verdict={verdict if verdict is not None else 'null'}"
    )


def poll_once(
    client: httpx.Client,
    endpoint: str,
    cursor_file: Path,
    *,
    since_snapshot_id: str | None = None,
    snapshot_id: str | None = None,
) -> list[str]:
    """Read one report, describe only report changes, then save its cursor."""
    saved = cursor_file.read_text().strip() if cursor_file.exists() else ""
    baseline = since_snapshot_id or saved
    request = {"since_snapshot_id": baseline} if baseline else {}
    if snapshot_id:
        request["snapshot_id"] = snapshot_id
    response = client.post(endpoint, json=request)
    response.raise_for_status()
    body = response.json()
    if body.get("action") != "agenda" or not isinstance(body.get("result"), dict):
        raise ValueError("expected an AstraFeed agenda response")
    result = body["result"]
    returned_snapshot_id = result.get("snapshot_id")
    if not isinstance(returned_snapshot_id, str) or not returned_snapshot_id:
        raise ValueError("agenda response has no snapshot_id")
    if snapshot_id is not None and returned_snapshot_id != snapshot_id:
        raise ValueError("agenda response does not match the pinned snapshot_id")

    if not baseline:
        lines = [f"Saved baseline {returned_snapshot_id}; run again to see report changes."]
    else:
        cards = [*(result.get("stories") or []), *(result.get("upcoming") or [])]
        if result.get("comparison_status") == "baseline_unavailable":
            noun = "card" if len(cards) == 1 else "cards"
            lines = [
                f"Baseline {baseline} unavailable; rebuilt from full report "
                f"{returned_snapshot_id} ({len(cards)} {noun})."
            ]
        elif result.get("comparison_status") == "ok" and result.get("response_mode") == "delta":
            if cards:
                lines = [
                    f"{baseline} → {returned_snapshot_id}: {len(cards)} new or updated report cards"
                ]
            else:
                lines = [f"{baseline} → {returned_snapshot_id}: no new or updated report cards"]
        else:
            raise ValueError("agenda response has no usable comparison status")
        lines.extend(_card_line(card) for card in cards)

    cursor_file.parent.mkdir(parents=True, exist_ok=True)
    cursor_file.write_text(returned_snapshot_id + "\n")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--cursor-file", type=Path, default=DEFAULT_CURSOR)
    parser.add_argument("--since-snapshot-id", help="Override saved cursor for a pinned comparison")
    parser.add_argument("--snapshot-id", help="Pin the target report for a reproducible demo")
    args = parser.parse_args()
    with httpx.Client(timeout=15.0) as client:
        lines = poll_once(
            client,
            args.endpoint,
            args.cursor_file,
            since_snapshot_id=args.since_snapshot_id,
            snapshot_id=args.snapshot_id,
        )
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
