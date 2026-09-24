#!/usr/bin/env python3
"""Score manually corrected positive labels on the frozen 60-post corpus."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from astrafeed.adapters.repository.sqlite.agenda import loads
from astrafeed.application.agenda_query import search_in_snapshot

ROOT = Path(__file__).resolve().parents[2]
LABELS = {
    899: "btc etf",
    7965: "bitcoin etf",
    7919: "axis robotics",
    12911: "финпотоки крипто-etf",
    4282: "гаррет джин закрыл",
    12872: "fetch.ai",
    14: "zetachain",
    16: "cyphersquad",
    943: "glassnode",
    861: "grok 4.7",
    7975: "токенизированных реальных активов",
    12900: "хейс: ai-долговой пузырь",
    938: "цифровые рубли",
    1039: "афк «система» меняет президента",
    955: "нефтепровод восток-запад",
    959: "нефти через красное море",
    8024: "circle",
    1058: "gpt-6",
    12916: "обратного выкупа гос. облигаций",
    12922: "данные сотрудников",
}
SEARCH = [
    ("BTC ETF", "btc etf"),
    ("альтсезон", "альтсезон"),
    ("ZEC шорт Гаррет", "гаррет джин закрыл"),
    ("Fetch.ai взлом", "fetch.ai"),
    ("цифровой рубль", "цифровые рубли"),
    ("Arthur Hayes", "хейс"),
    ("RWA токенизация", "токенизированных реальных активов"),
    ("CypherSquad ZEC", "cyphersquad"),
    ("ETF потоки вчера", "финпотоки крипто-etf"),
    ("Zaddr", "zaddr"),
]


def main(path: str) -> None:
    db = sqlite3.connect(path)
    raw = sqlite3.connect(ROOT / "astrafeed.db")
    row = db.execute("SELECT payload FROM agenda_snapshot WHERE published=1").fetchone()
    snapshot = loads(row[0])
    good = 0
    for raw_id, expected in LABELS.items():
        source_id, external_id = raw.execute(
            "SELECT source_id, external_id FROM raw_item WHERE id=?", (raw_id,)
        ).fetchone()
        pid = f"{source_id}:{external_id}"
        story_ids = [
            json.loads(row[0])["story_id"]
            for row in db.execute(
                "SELECT payload FROM agenda_json WHERE kind='link' "
                "AND json_extract(payload, '$.publication_id')=?", (pid,)
            )
        ]
        titles = [
            snapshot.stories[story_id].card.title
            for story_id in story_ids if story_id in snapshot.stories
        ]
        hit = any(expected in title.casefold() for title in titles)
        good += hit
        print(f"INCLUSION {raw_id}: {'PASS' if hit else 'MISS'} {expected!r}")
    search_good = 0
    for query, expected in SEARCH:
        hits, _ = search_in_snapshot(snapshot, query, limit=5, offset=0)
        hit = any(expected in item.title.casefold() for item in hits)
        search_good += hit
        print(f"SEARCH {query!r}: {'PASS' if hit else 'MISS'}")
    print(f"TOTAL snapshot={snapshot.snapshot_id} inclusion={good}/20 search={search_good}/10")


if __name__ == "__main__":
    main(sys.argv[1])
