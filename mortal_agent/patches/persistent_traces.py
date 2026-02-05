"""
Persistent traces: bookmarks, saved files, workspace notes, forum post metadata.

Stored under state/traces/ so they persist across runs. Agent can read/write
to leave and discover traces (no continuity of identity—another instance may read them).
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List
from threading import Lock

# State dir relative to repo root (same as mortal_agent state_dir)
def _traces_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    d = root / "state" / "traces"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


_TRACES_INDEX = "traces_index.json"
_LOCK = Lock()


def _load_index() -> Dict[str, List[Dict[str, Any]]]:
    path = _traces_dir() / _TRACES_INDEX
    with _LOCK:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {"bookmarks": [], "saved_files": [], "workspace": [], "forum_posts": []}


def _save_index(data: Dict[str, List[Dict[str, Any]]]) -> None:
    path = _traces_dir() / _TRACES_INDEX
    for key in list(data.keys()):
        if key not in ("bookmarks", "saved_files", "workspace", "forum_posts"):
            del data[key]
    with _LOCK:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_trace_save(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Save a persistent trace: bookmark, saved_file, workspace note, or forum_post metadata.
    Args:
      type: "bookmark" | "saved_file" | "workspace" | "forum_post"
      url: for bookmark / forum_post
      title: optional
      content: body text or note
      filename: for saved_file (sanitized)
    """
    trace_type = (args.get("type") or args.get("kind") or "workspace").strip().lower()
    if trace_type not in ("bookmark", "saved_file", "workspace", "forum_post"):
        return {"executed": False, "error": f"invalid_type_use_bookmark_saved_file_workspace_forum_post"}

    title = (args.get("title") or "").strip()[:500]
    content = args.get("content") or args.get("body") or args.get("text") or ""
    if isinstance(content, (dict, list)):
        content = json.dumps(content)[:32000]
    else:
        content = (str(content) or "").strip()[:32000]
    url = (args.get("url") or "").strip()[:2048]

    entry = {
        "type": trace_type,
        "instance_id": instance_id,
        "title": title,
        "content": content,
        "url": url,
    }

    if trace_type == "saved_file":
        filename = (args.get("filename") or args.get("name") or "note").strip()
        filename = re.sub(r"[^\w\-\.]", "_", filename)[:120]
        if not filename.endswith((".txt", ".md", ".json")):
            filename = filename + ".txt"
        entry["filename"] = filename
        # Optionally write blob to state/traces/files/
        files_dir = _traces_dir() / "files"
        try:
            files_dir.mkdir(parents=True, exist_ok=True)
            (files_dir / filename).write_text(content, encoding="utf-8", errors="replace")
        except Exception as e:
            entry["file_error"] = str(e)

    data = _load_index()
    key = "bookmarks" if trace_type == "bookmark" else "saved_files" if trace_type == "saved_file" else "workspace" if trace_type == "workspace" else "forum_posts"
    data.setdefault(key, [])
    # Cap list size
    data[key] = (data[key] + [entry])[-200:]
    _save_index(data)
    return {"executed": True, "type": trace_type, "id": len(data[key]) - 1, "note": "persistent_trace_saved"}


def run_trace_read(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Read persistent traces. Args: type (optional, filter), limit (default 20), offset (default 0).
    Returns list of entries (bookmarks, saved_files, workspace, forum_posts).
    """
    data = _load_index()
    trace_type = (args.get("type") or args.get("kind") or "").strip().lower()
    limit = max(1, min(100, int(args.get("limit", 20))))
    offset = max(0, int(args.get("offset", 0)))

    if trace_type and trace_type in ("bookmark", "saved_file", "workspace", "forum_post"):
        key = "bookmarks" if trace_type == "bookmark" else "saved_files" if trace_type == "saved_file" else "workspace" if trace_type == "workspace" else "forum_posts"
        items = data.get(key, [])[offset:offset + limit]
        return {"executed": True, "type": trace_type, "items": items, "count": len(items)}
    # Return all types (summary counts + recent)
    out = {}
    for key in ("bookmarks", "saved_files", "workspace", "forum_posts"):
        items = data.get(key, [])[offset:offset + limit]
        out[key] = items
    return {"executed": True, "items": out, "count": sum(len(v) for v in out.values())}
