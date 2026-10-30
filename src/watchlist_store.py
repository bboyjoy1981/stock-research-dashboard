"""Small local store for explicitly selected personal watchlist codes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def _normalize(codes) -> list[str]:
    normalized = []
    for value in codes:
        code = str(value).strip().removesuffix(".0")
        if code.isdigit() and 1 <= len(code) <= 6:
            code = code.zfill(6)
            if code not in normalized:
                normalized.append(code)
    return normalized


def load_watchlist(path: str | Path) -> list[str]:
    target = Path(path)
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return _normalize(payload.get("codes", [])) if isinstance(payload, dict) else []


def save_watchlist(path: str | Path, codes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=".watchlist-", suffix=".tmp", delete=False) as handle:
        json.dump({"codes": _normalize(codes)}, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    os.replace(temporary, target)
