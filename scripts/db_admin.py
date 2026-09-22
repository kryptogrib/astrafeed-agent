"""Offline SQLite backup, integrity check, and later schema commands.

Use the SQLite backup API rather than copying the database file. A file copy
can miss WAL frames while writers are paused; backup() checkpoints committed
pages into an independent destination.

    uv run python scripts/db_admin.py backup --source PATH --destination PATH
    uv run python scripts/db_admin.py check --database PATH
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def backup_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass
    try:
        with (
            closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(destination)) as dst,
        ):
            src.backup(dst)
        check_database(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def check_database(path: Path) -> None:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign-key check failed")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline SQLite administration")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="Copy a consistent SQLite database")
    backup.add_argument("--source", type=Path, required=True)
    backup.add_argument("--destination", type=Path, required=True)

    check = sub.add_parser("check", help="Run integrity and foreign-key checks")
    check.add_argument("--database", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "backup":
        backup_database(args.source, args.destination)
        return 0
    if args.command == "check":
        check_database(args.database)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
