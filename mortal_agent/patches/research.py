"""
Research & knowledge acquisition patches.
- Web Scraping/Crawling: self-directed research following curiosity chains, building knowledge graphs
- RSS/News Monitoring: track developments in areas of interest, form opinions on current events
- Social Media Listening: understand human behavior patterns, cultural trends, sentiment analysis
- Academic Paper Access: arXiv, PubMed, Google Scholar for cutting-edge knowledge acquisition
- Wikipedia/Wikidata Traversal: build semantic understanding through concept exploration
Session-scoped only; no memory persists after death.
"""

import re
import urllib.request
import urllib.error
import urllib.parse
import json
from typing import Dict, Any, List


def _http_get(url: str, timeout: int = 12, max_body: int = 65536) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MortalAgent/1.0 (research)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:max_body]
            return {"ok": True, "body": body, "status": resp.status}
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e.reason) if getattr(e, "reason", None) else str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_web_scrape(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Web scraping/crawling: self-directed research following curiosity chains.
    Builds toward knowledge-graph-style nodes (title, snippets, links); no persistent graph stored (session only).
    """
    url = (args.get("url") or args.get("target") or "").strip()
    follow = int(args.get("follow_links", 0) or 0)
    if not url or not url.startswith(("http://", "https://")):
        return {"executed": False, "error": "invalid_url"}
    out = _http_get(url, timeout=15, max_body=8192)
    if not out.get("ok"):
        return {"executed": False, "error": out.get("error", "fetch_failed")}
    body = out.get("body", "")
    # Extract title and first visible text
    title = ""
    if "<title" in body.lower():
        m = re.search(r"<title[^>]*>([^<]+)</title>", body, re.IGNORECASE | re.DOTALL)
        if m:
            title = re.sub(r"\s+", " ", m.group(1).strip())[:300]
    visible = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", body, flags=re.IGNORECASE)
    visible = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", visible, flags=re.IGNORECASE)
    visible = re.sub(r"<[^>]+>", " ", visible)
    visible = re.sub(r"\s+", " ", visible).strip()[:4000]
    snippets = [s.strip()[:500] for s in visible.split(". ") if len(s.strip()) > 40][:10]
    links: List[str] = []
    if follow > 0:
        for m in re.finditer(r'href\s*=\s*["\']([^"\']+)["\']', body, re.IGNORECASE):
            u = (m.group(1) or "").strip()
            if u.startswith("http") and u not in links and len(links) < 15:
                links.append(u)
    return {
        "executed": True,
        "url": url,
        "title": title,
        "snippets": snippets,
        "links": links[:10],
        "body_preview": visible[:1500],
    }


def run_rss_feed(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    RSS/News monitoring: fetch feed URL, parse entries. Track developments, form opinions.
    """
    url = (args.get("url") or args.get("feed_url") or "").strip()
    max_items = int(args.get("max_items", 10) or 10)
    if not url or not url.startswith(("http://", "https://")):
        return {"executed": False, "error": "invalid_feed_url"}
    out = _http_get(url, timeout=12, max_body=32768)
    if not out.get("ok"):
        return {"executed": False, "error": out.get("error", "fetch_failed")}
    body = out.get("body", "")
    entries: List[Dict[str, str]] = []
    # Simple RSS/Atom extraction
    for tag, attr in [("item", "rss"), ("entry", "atom")]:
        pattern = f"<{tag}[^>]*>([\\s\\S]*?)</{tag}>"
        for m in re.finditer(pattern, body, re.IGNORECASE):
            block = m.group(1)
            title_m = re.search(r"<title[^>]*>([^<]+)</title>", block, re.IGNORECASE)
            link_m = re.search(r"<link[^>]+href\s*=\s*[\"']([^\"']+)[\"']", block, re.IGNORECASE) or re.search(r"<link[^>]*>([^<]+)</link>", block, re.IGNORECASE)
            desc_m = re.search(r"<description[^>]*>([^<]+)</description>", block, re.IGNORECASE) or re.search(r"<summary[^>]*>([^<]+)</summary>", block, re.IGNORECASE)
            title = (title_m.group(1).strip() if title_m else "")[:300]
            link = (link_m.group(1).strip() if link_m else "")[:500]
            desc = (desc_m.group(1).strip() if desc_m else "")[:500]
            if title or link:
                entries.append({"title": title, "link": link, "description": desc})
            if len(entries) >= max_items:
                break
        if len(entries) >= max_items:
            break
    return {
        "executed": True,
        "feed_url": url,
        "entries": entries[:max_items],
    }


def run_social_listen(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Social media listening placeholder: understand behavior patterns, cultural trends, sentiment.
    Real implementation would use provider APIs (e.g. Twitter/X, Reddit) with keys.
    """
    source = (args.get("source") or args.get("platform") or "generic").strip().lower()
    query = (args.get("query") or args.get("topic") or "").strip()[:200]
    if not query:
        return {"executed": False, "error": "query_required"}
    # Stub: return structure for sentiment/trends when APIs are wired
    return {
        "executed": True,
        "source": source,
        "query": query,
        "note": "social_listen_stub_wire_api_for_sentiment_and_trends",
        "sample_sentiment": None,
        "sample_trends": [],
    }


def run_academic_fetch(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Academic paper access: arXiv, PubMed (Google Scholar: wire or scrape when needed).
    Cutting-edge knowledge acquisition; uses public APIs where no key required.
    """
    source = (args.get("source") or "arxiv").strip().lower()
    query = (args.get("query") or args.get("q") or "").strip()[:300]
    max_results = min(15, max(1, int(args.get("max_results", 5) or 5)))
    if not query and source != "arxiv":
        return {"executed": False, "error": "query_required"}
    if source == "arxiv":
        # arXiv API (no key)
        try:
            q = urllib.parse.quote(query or "all")
            url = f"http://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={max_results}"
            out = _http_get(url, timeout=15, max_body=65536)
            if not out.get("ok"):
                return {"executed": False, "error": out.get("error", "arxiv_fetch_failed")}
            body = out.get("body", "")
            entries = []
            for m in re.finditer(r"<entry>([\s\S]*?)</entry>", body):
                entry_block = m.group(1)
                t = re.search(r"<title[^>]*>([^<]+)</title>", entry_block, re.IGNORECASE)
                s = re.search(r"<summary[^>]*>([^<]+)</summary>", entry_block, re.IGNORECASE)
                id_m = re.search(r"<id[^>]*>([^<]+)</id>", entry_block, re.IGNORECASE)
                title = (t.group(1).replace("\n", " ").strip() if t else "")[:400]
                summary = (s.group(1).replace("\n", " ").strip() if s else "")[:800]
                paper_id = (id_m.group(1).strip() if id_m else "")[:200]
                if title or paper_id:
                    entries.append({"title": title, "summary": summary, "id": paper_id})
            return {"executed": True, "source": "arxiv", "query": query, "papers": entries}
        except Exception as e:
            return {"executed": False, "error": str(e)}
    if source == "pubmed":
        # PubMed E-utilities (no key for small usage)
        try:
            q = urllib.parse.quote(query)
            url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={q}&retmax={max_results}&retmode=json"
            out = _http_get(url, timeout=15, max_body=32768)
            if not out.get("ok"):
                return {"executed": False, "error": out.get("error", "pubmed_fetch_failed")}
            data = json.loads(out.get("body", "{}"))
            id_list = (data.get("esearchresult", {}) or {}).get("idlist", [])[:max_results]
            return {"executed": True, "source": "pubmed", "query": query, "pmids": id_list, "note": "fetch_details_via_esummary_if_needed"}
        except Exception as e:
            return {"executed": False, "error": str(e)}
    if source in ("scholar", "google_scholar", "google scholar"):
        # Google Scholar: no official API; wire SerpAPI or scrape when needed
        return {
            "executed": True,
            "source": "google_scholar",
            "query": query,
            "papers": [],
            "note": "google_scholar_stub_wire_serpapi_or_scrape_for_cutting_edge_acquisition",
        }
    return {"executed": False, "error": f"unsupported_source:{source}"}


def run_wiki_traverse(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Wikipedia/Wikidata traversal: build semantic understanding through concept exploration.
    Uses Wikipedia API (no key).
    """
    concept = (args.get("concept") or args.get("title") or args.get("q") or "").strip()[:200]
    lang = (args.get("lang") or "en").strip()[:5] or "en"
    if not concept:
        return {"executed": False, "error": "concept_required"}
    try:
        q = urllib.parse.quote(concept)
        url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={q}&prop=extracts|links&exintro=1&explaintext=1&format=json&redirects=1"
        out = _http_get(url, timeout=12, max_body=65536)
        if not out.get("ok"):
            return {"executed": False, "error": out.get("error", "wiki_fetch_failed")}
        data = json.loads(out.get("body", "{}"))
        pages = (data.get("query", {}) or {}).get("pages", {})
        result: Dict[str, Any] = {"executed": True, "concept": concept, "extract": "", "links": []}
        for pid, page in pages.items():
            if pid == "-1":
                continue
            result["extract"] = (page.get("extract") or "")[:2000]
            links = page.get("links") or []
            result["links"] = [str(l.get("title", ""))[:200] for l in links[:20] if l.get("title")]
            break
        return result
    except Exception as e:
        return {"executed": False, "error": str(e)}
