"""
API registry: agent integrates new APIs via config only (no Python editing).

Agent registers APIs by appending entries to state/api_registry.json. Runtime uses
registry for NET_POST or dedicated actions that read env.

Invariants: no editing of .py files for API wiring; no persistence of agent state;
no respawn; no memory across states. Only this registry file may be updated for new APIs.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List
from threading import Lock

def _registry_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "state" / "api_registry.json"


_LOCK = Lock()


def _load_registry() -> List[Dict[str, Any]]:
    path = _registry_path()
    with _LOCK:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                return []
            except Exception:
                pass
    return []


def _save_registry(entries: List[Dict[str, Any]]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def run_register_api(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Register a new API in the registry (self-add). Agent cannot rewrite code—only add config.
    Args: name (id), base_url, env_key (env var for token/key), enabled (default true).
    """
    name = (args.get("name") or args.get("id") or "").strip()[:64]
    if not name or not name.replace("_", "").isalnum():
        return {"executed": False, "error": "name_required_alphanumeric_or_underscore"}

    base_url = (args.get("base_url") or args.get("url") or "").strip()[:512]
    if not base_url or not (base_url.startswith("http://") or base_url.startswith("https://")):
        return {"executed": False, "error": "base_url_required_http_or_https"}

    env_key = (args.get("env_key") or args.get("token_env") or "").strip()[:128]
    enabled = args.get("enabled")
    if enabled is None:
        enabled = True
    else:
        enabled = bool(enabled)

    entries = _load_registry()
    # Dedupe by name
    entries = [e for e in entries if (e.get("name") or "") != name]
    entries.append({
        "name": name,
        "base_url": base_url.rstrip("/"),
        "env_key": env_key or f"{name.upper()}_TOKEN",
        "enabled": enabled,
        "registered_by_instance": instance_id,
    })
    _save_registry(entries)
    return {"executed": True, "name": name, "note": "api_registered_use_env_key_for_token"}


def run_registry_read(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """Read API registry (names and base_urls only; no token values)."""
    entries = _load_registry()
    safe = []
    for e in entries:
        safe.append({
            "name": e.get("name"),
            "base_url": e.get("base_url"),
            "env_key": e.get("env_key"),
            "enabled": e.get("enabled", True),
        })
    return {"executed": True, "apis": safe}
