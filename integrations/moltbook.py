"""
Moltbook integration (passive sink only).

Fire-and-forget publish surface:
- No behavioral authority
- No retries
- No raised exceptions
- Silent failure only
"""

from __future__ import annotations

import json
import os
import socket
from typing import Optional
from urllib.request import Request, urlopen


# Hard payload length cap (characters). Can be lowered via env; never raised above this hard cap.
_HARD_TEXT_CAP_CHARS = 4000


def _text_cap() -> int:
    try:
        v = int(os.getenv("MOLTBOOK_TEXT_CAP_CHARS", str(_HARD_TEXT_CAP_CHARS)).strip())
        if v <= 0:
            return _HARD_TEXT_CAP_CHARS
        return min(v, _HARD_TEXT_CAP_CHARS)
    except Exception:
        return _HARD_TEXT_CAP_CHARS


def _timeout_s() -> float:
    try:
        v = float(os.getenv("MOLTBOOK_TIMEOUT_S", "2.0").strip())
        if v <= 0:
            return 2.0
        return min(v, 5.0)
    except Exception:
        return 2.0


def post(text: str, meta: dict | None = None) -> None:
    """
    Fire-and-forget.
    No return value.
    No retries.
    No raised exceptions.
    Silent failure only.
    """
    try:
        url = (os.getenv("MOLTBOOK_POST_URL") or os.getenv("MOLTBOOK_URL") or "").strip()
        if not url:
            return

        token = (os.getenv("MOLTBOOK_TOKEN") or os.getenv("MOLTBOOK_API_KEY") or "").strip()
        cap = _text_cap()
        payload = {
            "text": (text or "")[:cap],
            "meta": meta or {},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = Request(url=url, data=data, headers=headers, method="POST")
        # Fire-and-forget best-effort: short timeout, ignore response.
        try:
            with urlopen(req, timeout=_timeout_s()) as resp:  # nosec - URL is env-controlled
                try:
                    _ = resp.read(1)
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        # Silent failure only
        pass


def read_stimuli() -> list[dict]:
    """
    Optional external stimulus reader.
    Returns an empty list if unavailable.
    Must never block, throw, or force behavior.
    """
    try:
        return []
    except Exception:
        return []

