"""List the Telegram account's channel subscriptions and whether comments are open.

Pulse reads discussion comments, so only broadcast channels with a linked
discussion group are useful. Usage:

    uv run python scripts/channels.py            # print the table
    uv run python scripts/channels.py --write    # also put usable channels into config.yaml
    uv run python scripts/channels.py --folder крипта --write   # only one chat folder

``--write`` keeps every other key in config.yaml (creating it from
config.example.yaml when missing) and replaces only ``channels``.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

import yaml
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest

from astrafeed.adapters.source.telegram import public_username
from astrafeed.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent


def _title(folder: object) -> str:
    # Newer layers wrap the folder title in TextWithEntities.
    title = getattr(folder, "title", "")
    return str(getattr(title, "text", title))


async def _folder_filter(client: TelegramClient, name: str):
    """Return a predicate for channels that belong to the chat folder ``name``.

    A folder is explicit peers plus type flags (e.g. "all channels"), minus
    excluded peers; both parts are honoured.
    """
    result = await client(GetDialogFiltersRequest())
    folders = getattr(result, "filters", result)
    titles = [_title(f) for f in folders if _title(f)]
    folder = next((f for f in folders if _title(f).casefold() == name.casefold()), None)
    if folder is None:
        raise SystemExit(f"folder {name!r} not found; available: {', '.join(titles)}")
    pinned = getattr(folder, "pinned_peers", None) or []
    include = getattr(folder, "include_peers", None) or []
    included = {getattr(p, "channel_id", None) for p in [*pinned, *include]}
    exclude = getattr(folder, "exclude_peers", None) or []
    excluded = {getattr(p, "channel_id", None) for p in exclude}
    all_channels = bool(getattr(folder, "broadcasts", False))
    return lambda entity: entity.id not in excluded and (all_channels or entity.id in included)


async def _scan(cfg: Settings, folder: str | None = None) -> list[dict[str, object]]:
    client = TelegramClient(
        StringSession(cfg.telegram.session), cfg.telegram.api_id, cfg.telegram.api_hash
    )
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Telegram session is not authorized: run `make login` first")
    rows: list[dict[str, object]] = []
    try:
        in_folder = await _folder_filter(client, folder) if folder else (lambda _e: True)
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not getattr(entity, "broadcast", False):
                continue  # supergroups/chats are not Pulse sources
            if not in_folder(entity):
                continue
            username = public_username(entity)
            try:
                full = await client(GetFullChannelRequest(entity))
                comments = full.full_chat.linked_chat_id is not None
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                full = await client(GetFullChannelRequest(entity))
                comments = full.full_chat.linked_chat_id is not None
            rows.append(
                {
                    "ref": f"@{username}" if username else None,
                    "title": dialog.name,
                    "comments": comments,
                    "subscribers": getattr(full.full_chat, "participants_count", None),
                }
            )
    finally:
        await client.disconnect()
    return rows


def _write_config(config_path: Path, refs: list[str], news: list[str]) -> None:
    if not config_path.exists():
        shutil.copy(REPO_ROOT / "config.example.yaml", config_path)
    data = yaml.safe_load(config_path.read_text()) or {}
    data["channels"] = refs
    data["news_channels"] = news
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    print(f"\nWrote {len(refs)} channels + {len(news)} news_channels to {config_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--folder", help="Only channels from this Telegram chat folder")
    args = parser.parse_args()
    cfg = Settings.load(args.config)
    rows = asyncio.run(_scan(cfg, args.folder))

    print(f"{'channel':<32} {'comments':<9} {'subs':>9}  title")
    for row in sorted(rows, key=lambda r: (not r["comments"], str(r["ref"]))):
        ref = row["ref"] or "(private)"
        mark = "yes" if row["comments"] else "no"
        print(f"{ref:<32} {mark:<9} {row['subscribers'] or '?':>9}  {row['title']}")

    usable = [str(r["ref"]) for r in rows if r["ref"] and r["comments"]]
    news = [str(r["ref"]) for r in rows if r["ref"] and not r["comments"]]
    skipped = len(rows) - len(usable) - len(news)
    print(f"\nWith comments: {len(usable)}; news only: {len(news)}; private skipped: {skipped}")
    if args.write:
        _write_config(Path(args.config), usable, news)


if __name__ == "__main__":
    main()
