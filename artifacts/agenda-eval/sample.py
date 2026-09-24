#!/usr/bin/env python3
"""Frozen 60-post agenda sample. stdlib + sqlite readonly. No LLM.

python3 artifacts/agenda-eval/sample.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "astrafeed.db"
PREV = ("2026-09-21 00:00:00", "2026-09-22 00:00:00")
CURR = ("2026-09-22 00:00:00", "2026-09-23 00:00:00")

IDS_PREV = [
    4282,
    12872,
    747,
    13223,
    12875,
    14,
    12876,
    769,
    12878,
    7872,
    5275,
    39,
    5316,
    5324,
    12885,
    7896,
    7903,
    848,
    861,
    7919,
    7922,
    13249,
    7935,
    7941,
    7942,
    5633,
    5649,
    5415,
    5479,
    5103,
]
IDS_CURR = [
    899,
    12900,
    916,
    16,
    13933,
    938,
    943,
    948,
    7957,
    7959,
    7965,
    7966,
    955,
    7975,
    959,
    6104,
    984,
    12911,
    7991,
    42,
    1021,
    1027,
    1031,
    1039,
    1043,
    12916,
    1058,
    8024,
    12922,
    13777,
]

SEARCH = [
    ("BTC ETF", "Притоки в спотовые BTC ETF"),
    ("альтсезон", "Glassnode: альтсезон"),
    ("ZEC шорт Гаррет", "Закрытие шорта ZEC Гарретом"),
    ("Fetch.ai взлом", "Один хакер — три AI-криптопроекта"),
    ("цифровой рубль", "Цифровой рубль и бюджетные контракты"),
    ("Arthur Hayes", "Хейс: долговой пузырь AI"),
    ("RWA токенизация", "Рост токенизированных RWA"),
    ("CypherSquad ZEC", "Апдейт минтов 22 сентября"),
    ("ETF потоки вчера", "Финпотоки крипто-ETF"),
    ("Zaddr", "Минты и WL 21 сентября"),
]

INCLUSIONS = [
    (899, "Притоки в спотовые BTC ETF"),
    (7965, "Притоки в спотовые BTC ETF"),
    (7919, "Притоки в спотовые BTC ETF"),
    (12911, "Финпотоки крипто-ETF"),
    (4282, "Закрытие шорта ZEC Гарретом"),
    (12872, "Один хакер — три AI-криптопроекта"),
    (14, "Минты и WL 21 сентября"),
    (16, "Апдейт минтов 22 сентября"),
    (943, "Glassnode: альтсезон"),
    (861, "Glassnode: альтсезон"),
    (7975, "Рост токенизированных RWA"),
    (12900, "Хейс: долговой пузырь AI"),
    (938, "Цифровой рубль и бюджетные контракты"),
    (848, "Цифровой рубль и бюджетные контракты"),
    (955, "Нефтепровод Саудовской Аравии"),
    (959, "Нефтепровод Саудовской Аравии"),
    (8024, "Активности дня: ZEC NFT и Circle"),
    (1058, "Новые модели GPT-6 / Claude"),
    (12916, "Выкуп казначейских облигаций США"),
    (12922, "Утечка данных сотрудников ФБР"),
]


def main() -> None:
    ids = IDS_PREV + IDS_CURR
    if len(ids) != 60 or len(set(ids)) != 60:
        raise SystemExit(f"need 60 unique, got {len(ids)} unique={len(set(ids))}")
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = dict(
        con.execute(
            f"SELECT id, timestamp FROM raw_item WHERE id IN ({','.join('?' * 60)})",
            ids,
        )
    )
    missing = [i for i in ids if i not in rows]
    if missing:
        raise SystemExit(f"missing raw_item ids: {missing}")
    prev_n = curr_n = 0
    for raw_id in ids:
        ts = rows[raw_id]
        if PREV[0] <= ts < PREV[1]:
            prev_n += 1
        elif CURR[0] <= ts < CURR[1]:
            curr_n += 1
        else:
            raise SystemExit(f"{raw_id} outside windows: {ts}")
    if prev_n != 30 or curr_n != 30:
        raise SystemExit(f"window split prev={prev_n} curr={curr_n}")
    print(
        f"ok ids=60 prev=30 curr=30 search={len(SEARCH)} inclusions={len(INCLUSIONS)} labels=preliminary"
    )


if __name__ == "__main__":
    main()
