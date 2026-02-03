"""
Action commit: COMMIT_WINDOW_MS. No mid-commit reversal. RAM only.
"""

import time
from typing import Optional
from dataclasses import dataclass

try:
    from .will_config import COMMIT_WINDOW_MS
except ImportError:
    COMMIT_WINDOW_MS = 500


@dataclass
class CommitState:
    committed_at_ms: float = 0.0
    action_id: str = ""
    in_commit: bool = False


_commit_state = CommitState()


def commit_begin(action_id: str = "") -> bool:
    if _commit_state.in_commit:
        return False
    _commit_state.in_commit = True
    _commit_state.committed_at_ms = time.monotonic() * 1000.0
    _commit_state.action_id = action_id or str(time.monotonic())
    return True


def commit_end() -> None:
    _commit_state.in_commit = False


def in_commit_window() -> bool:
    if not _commit_state.in_commit:
        return False
    elapsed_ms = (time.monotonic() * 1000.0) - _commit_state.committed_at_ms
    if elapsed_ms >= COMMIT_WINDOW_MS:
        _commit_state.in_commit = False
        return False
    return True


def block_reversal() -> bool:
    return in_commit_window()


def get_commit_state() -> CommitState:
    return _commit_state
