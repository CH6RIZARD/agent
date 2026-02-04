"""Optional network pipeline for NET_FETCH and WEB_SEARCH — outbound HTTP (e.g. over WiFi)."""
import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Dict, Any, List


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


def _parse_ddg_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse DuckDuckGo instant answer API response into snippets and URLs."""
    out: Dict[str, Any] = {"executed": True, "query": "", "abstract": "", "snippets": [], "urls": []}
    if not isinstance(data, dict):
        return out
    out["query"] = (data.get("Heading") or data.get("AbstractSource") or "").strip() or (data.get("RelatedTopics") and "search")
    abstract = (data.get("Abstract") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip()
    if abstract:
        out["abstract"] = abstract[:1500]
        if abstract_url and abstract_url.startswith(("http://", "https://")):
            out["urls"].append(abstract_url)
    for topic in (data.get("RelatedTopics") or [])[:10]:
        if isinstance(topic, dict):
            text = (topic.get("Text") or "").strip()
            url = (topic.get("FirstURL") or "").strip()
            if text:
                out["snippets"].append(text[:400])
            if url and url.startswith(("http://", "https://")):
                out["urls"].append(url)
        elif isinstance(topic, str):
            out["snippets"].append(str(topic)[:400])
    for r in (data.get("Results") or [])[:5]:
        if isinstance(r, dict):
            text = (r.get("Text") or "").strip()
            url = (r.get("FirstURL") or r.get("URL") or "").strip()
            if text:
                out["snippets"].append(text[:400])
            if url and url.startswith(("http://", "https://")):
                out["urls"].append(url)
    out["urls"] = list(dict.fromkeys(out["urls"]))[:15]
    return out


def web_search_pipeline(item: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Run WEB_SEARCH: args.query -> DuckDuckGo instant answer API (no API key).
    Returns {"executed": True, "query", "abstract", "snippets", "urls"} or {"executed": False, "error": "..."}.
    Agent can then NET_FETCH any of the returned urls to follow links.
    """
    action, args = item.get("action"), item.get("args") or {}
    if action != "WEB_SEARCH":
        return {"executed": False, "error": "not_web_search"}
    query = (args.get("query") or args.get("q") or "").strip()
    if not query or len(query) > 500:
        return {"executed": False, "error": "invalid_query"}
    try:
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({"q": query, "format": "json", "no_redirect": "1"})
        req = urllib.request.Request(url, headers={"User-Agent": "MortalAgent/1.0 (autonomous browse)"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body) if body else {}
        out = _parse_ddg_result(data)
        out["query"] = query
        return out
    except urllib.error.URLError as e:
        return {"executed": False, "error": str(e.reason) if getattr(e, "reason", None) else str(e)}
    except Exception as e:
        return {"executed": False, "error": str(e)}


def unified_network_pipeline(item: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Single entry point: NET_FETCH -> simple_http_fetch_pipeline, WEB_SEARCH -> web_search_pipeline.
    Use this as the executor's run_network_pipeline for unrestricted browse + fetch.
    """
    action = item.get("action")
    if action == "NET_FETCH":
        return simple_http_fetch_pipeline(item, instance_id)
    if action == "WEB_SEARCH":
        return web_search_pipeline(item, instance_id)
    return {"executed": False, "error": "unknown_action"}
