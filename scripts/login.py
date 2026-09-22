"""One-time Telegram login: generates a Telethon StringSession and writes it
into .env automatically.

Run interactively (it will ask for phone number, login code, and 2FA password
if enabled):

    make login           # or: uv run python scripts/login.py

On success it upserts the TELEGRAM_SESSION line in .env (replacing an
existing one, never duplicating) and keeps a .env.bak backup.
"""

from __future__ import annotations

from pathlib import Path

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

from astrafeed.config import Settings

KEY = "TELEGRAM_SESSION"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


def upsert_env(path: Path, key: str, value: str) -> None:
    """Replace the `key=...` line in an .env file, or append it if absent."""
    line = f"{key}={value}\n"
    if not path.exists():
        path.write_text(line, encoding="utf-8")
        print(f"Created {path} with {key}.")
        return

    backup = path.parent / (path.name + ".bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    replaced = False
    for i, existing in enumerate(lines):
        if existing.lstrip().startswith(f"{key}="):
            lines[i] = line
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(line)

    path.write_text("".join(lines), encoding="utf-8")
    action = "Updated" if replaced else "Appended"
    print(f"{action} {key} in {path} (backup at {backup}).")


def main() -> None:
    cfg = Settings.load()
    with TelegramClient(StringSession(), cfg.telegram.api_id, cfg.telegram.api_hash) as client:
        session_string = client.session.save()

    upsert_env(ENV_PATH, KEY, session_string)
    print("\nDone. Telegram session saved. You can now run: make serve / make live")


if __name__ == "__main__":
    main()
