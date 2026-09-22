from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(level: str, file: str | None) -> None:
    """Configure the astrafeed logger hierarchy.

    Sets up a stderr StreamHandler (always) and an optional FileHandler.
    Both use the same Formatter. Only the ``astrafeed`` logger subtree is
    configured so third-party libraries are unaffected.
    """
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    numeric = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger("astrafeed")
    root.setLevel(numeric)
    # Avoid duplicate handlers if called more than once (e.g. in tests)
    root.handlers.clear()

    stderr_h = logging.StreamHandler(sys.stderr)
    stderr_h.setLevel(numeric)
    stderr_h.setFormatter(fmt)
    root.addHandler(stderr_h)

    if file:
        # A log *sink* must never prevent the service from booting. On a
        # read-only / hardened container filesystem (read_only: true) the
        # configured path may be unwritable (OSError); degrade to stderr-only
        # with a warning instead of crashing the whole process on startup.
        try:
            file_h = logging.FileHandler(Path(file), encoding="utf-8")
        except OSError as exc:
            root.warning(
                "could not open log file %s (%s); continuing with stderr only",
                file,
                exc,
            )
        else:
            file_h.setLevel(numeric)
            file_h.setFormatter(fmt)
            root.addHandler(file_h)
