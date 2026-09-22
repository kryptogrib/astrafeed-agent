from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")


def normalized_text(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower())


def text_hash(text: str) -> str:
    return hashlib.sha256(normalized_text(text).encode()).hexdigest()
