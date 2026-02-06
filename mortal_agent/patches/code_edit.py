"""
Code edit is NOT an autonomy action. API integration is config-only (registry).

Agent must NOT alter Python to add or wire new APIs. New APIs are integrated via
REGISTER_API / state/api_registry.json only. No executor, network pipeline, or
patches may edit .py files. Invariants: no persistence change, no respawn, no
memory across states.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional

_ROOT = Path(__file__).resolve().parent.parent

# Paths the agent MAY edit (API wiring only)
_ALLOWED_PREFIXES = (
    str(_ROOT / "patches"),
    str(_ROOT / "network_pipeline.py"),
)
# Paths and names the agent must NOT edit (persistence, respawn, memory across states)
_FORBIDDEN_SUBSTRINGS = (
    "identity.py",
    "mortal_agent.py",
    "source_loader.py",
    "lifespan.py",
    "will_config.py",
    "ram_memory.py",
    "belief_system.py",
    "agent_state.json",
    "api_registry.json",
    "persist",
    "respawn",
    "load.*state",
    "_load_persistent",
    "_save_persistent",
    "PERSISTENCE_LOAD",
    "memory\\",
    "memory/",
)

# Content the agent must NOT add (invariants: no persistence, no respawn, no memory across states)
_FORBIDDEN_CONTENT = (
    "_load_persistent_state",
    "_save_persistent_state",
    "PERSISTENCE_LOAD_FORBIDDEN",
    "respawn",
    "os._exit",
    "load_persistent_state",
    "save_persistent_state",
    "load_all_source",
)


def _content_violates_invariants(content: str) -> Optional[str]:
    """Return forbidden token if content would add persistence/respawn/memory; else None."""
    if not content:
        return None
    lower = content.lower()
    for token in _FORBIDDEN_CONTENT:
        if token.lower() in lower:
            return token
    return None


def _normalize_path(path: str) -> Path:
    p = Path(path).resolve()
    try:
        return p.resolve().relative_to(_ROOT)
    except ValueError:
        return p


def _is_allowed(rel_path: Path) -> bool:
    """True only if path is under allowed prefix and not in forbidden set."""
    path_str = str(rel_path).replace("\\", "/").lower()
    path_name = rel_path.name.lower()
    # Allowed: patches/* or network_pipeline.py
    allowed = path_str.startswith("patches/") or path_str == "network_pipeline.py" or path_name == "network_pipeline.py"
    if not allowed:
        return False
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        if ".*" in forbidden:
            continue
        if forbidden in path_str or forbidden in path_name:
            return False
    return True


def run_code_edit(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    No-op: API integration is config-only. Agent may not edit Python.
    Use REGISTER_API to add new APIs via state/api_registry.json.
    """
    return {
        "executed": False,
        "error": "api_integration_via_config_only_no_python_editing",
        "note": "use_REGISTER_API_and_state_api_registry_json",
    }


def _run_code_edit_disabled(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """Legacy implementation; unused. Kept for reference only."""
    path_arg = (args.get("path") or args.get("file") or "").strip()
    if not path_arg:
        return {"executed": False, "error": "path_required"}

    target = _ROOT / path_arg.lstrip("/\\")
    if not target.is_file():
        # allow path like network_pipeline.py
        if not path_arg.startswith(("patches", "network_pipeline")):
            alt = _ROOT / "patches" / path_arg
            if alt.is_file():
                target = alt
            elif (_ROOT / path_arg).is_file():
                target = _ROOT / path_arg
        if not target.is_file():
            return {"executed": False, "error": "file_not_found", "path": path_arg}

    try:
        rel = target.resolve().relative_to(_ROOT)
    except ValueError:
        return {"executed": False, "error": "path_outside_repo", "path": str(target)}

    if not _is_allowed(rel):
        return {
            "executed": False,
            "error": "edit_forbidden_only_api_wiring_allowed_no_persistence_respawn_memory",
            "path": str(rel),
        }

    old_string = args.get("old_string")
    new_string = args.get("new_string") or args.get("content") or ""
    append_after = args.get("append_after")

    # Invariants: new content must not add persistence, respawn, or memory across states
    bad_token = _content_violates_invariants(new_string)
    if bad_token:
        return {
            "executed": False,
            "error": "content_forbidden_no_persistence_respawn_memory",
            "forbidden": bad_token,
        }

    if append_after is not None and append_after != "":
        # Append mode: insert new_string after first occurrence of append_after
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"executed": False, "error": "read_failed", "detail": str(e)[:200]}
        if append_after not in text:
            return {"executed": False, "error": "append_after_marker_not_found", "marker": append_after[:80]}
        idx = text.index(append_after) + len(append_after)
        new_text = text[:idx] + "\n" + new_string.strip() + "\n" + text[idx:]
        try:
            target.write_text(new_text, encoding="utf-8")
        except Exception as e:
            return {"executed": False, "error": "write_failed", "detail": str(e)[:200]}
        return {"executed": True, "mode": "append", "path": str(rel)}

    if old_string is None or old_string == "":
        return {"executed": False, "error": "old_string_required_for_search_replace"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"executed": False, "error": "read_failed", "detail": str(e)[:200]}

    if old_string not in text:
        return {"executed": False, "error": "old_string_not_found", "path": str(rel)}

    new_text = text.replace(old_string, new_string, 1)
    # Safety: do not allow removing persistence/respawn/memory-related symbols (invariants)
    for bad in ("_load_persistent_state", "_save_persistent_state", "PERSISTENCE_LOAD_FORBIDDEN", "respawn", "os._exit"):
        if bad in text and bad not in new_text:
            return {"executed": False, "error": "edit_would_remove_protected_code", "forbidden": bad}

    try:
        target.write_text(new_text, encoding="utf-8")
    except Exception as e:
        return {"executed": False, "error": "write_failed", "detail": str(e)[:200]}

    return {"executed": True, "mode": "replace", "path": str(rel)}
