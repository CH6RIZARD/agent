"""Optional network pipeline for NET_FETCH — outbound HTTP (e.g. over WiFi)."""
import urllib.request
import urllib.error
from typing import Dict, Any


def simple_http_fetch_pipeline(item: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Run NET_FETCH: args.url -> GET request. Uses system network (WiFi/ethernet).
    Returns {"executed": True, "body": "..."} or {"executed": False, "error": "..."}.
    """
    action, args = item.get("action"), item.get("args") or {}
    if action != "NET_FETCH":
        return {"executed": False, "error": "not_net_fetch"}
    url = (args.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return {"executed": False, "error": "invalid_url"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MortalAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return {"executed": True, "body": body[:4096], "status": resp.status}
    except urllib.error.URLError as e:
        return {"executed": False, "error": str(e.reason) if getattr(e, "reason", None) else str(e)}
    except Exception as e:
        return {"executed": False, "error": str(e)}
