"""
Crash handler: write crash reports for humans (stack trace). NO mind state.
Debugging that doesn't cheat. RAM-only identity is never written.
"""

import os
import sys
import traceback
from pathlib import Path
from typing import Optional
from datetime import datetime

# Logs under mortal_agent root
_CRASH_DIR = Path(__file__).resolve().parent.parent / "logs" / "crash_reports"


def write_crash_report(
    reason: str = "unknown",
    instance_id: Optional[str] = None,
    exc: Optional[BaseException] = None,
) -> Path:
    """
    Write a crash report file: timestamp, reason, instance_id (for correlation only), stack trace.
    NO internal state, no memory, no identity reconstruction.
    """
    _CRASH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"crash_{ts}.txt"
    path = _CRASH_DIR / name
    lines = [
        f"Crash report {ts}",
        f"Reason: {reason}",
        f"Instance ID (for correlation only): {instance_id or 'n/a'}",
        "",
    ]
    if exc is not None:
        lines.append("Traceback:")
        lines.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    else:
        lines.append("No exception captured.")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def install_crash_handler(instance_id: Optional[str] = None) -> None:
    """Install sys.excepthook to write crash report on uncaught exception. No mind state."""
    def hook(exc_type, exc_value, tb):
        write_crash_report(
            reason="uncaught_exception",
            instance_id=instance_id,
            exc=exc_value if isinstance(exc_value, BaseException) else None,
        )
        sys.__excepthook__(exc_type, exc_value, tb)
    sys.excepthook = hook
