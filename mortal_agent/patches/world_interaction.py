"""
World interaction & influence patches.
- File Hosting: write to ch6rizard (current folder in repo), signed and immersively emergent; optional GitHub, Pastebin
- Form Submission: sign up for services, submit applications, register accounts
- API Discovery & Integration: find and connect to new APIs autonomously (RapidAPI, etc.)
- Cloud Service Management: spin up compute when needed (AWS, Replicate)
- Code Repository Access: clone, analyze, potentially contribute to open source
- Payment Processing: Stripe/PayPal when building value
Session-scoped; nothing persists after death except artifacts written to ch6rizard within this run.
"""

import os
import re
import json
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional

# ch6rizard: current folder in repo for signed, immersively emergent artifacts
def _ch6rizard_root() -> Path:
    """Root of ch6rizard artifact folder (mortal_agent/ch6rizard). All FILE_HOST output lands here."""
    root = Path(__file__).resolve().parent.parent / "ch6rizard"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return root


def _sign_artifact(content: str, instance_id: str, action: str) -> str:
    """Produce a short signature string for emergent traceability (not cryptographic)."""
    raw = f"{instance_id}|{action}|{content[:500]}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def run_file_host(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    File hosting: share generated code, data, artifacts to ch6rizard (current folder in repo).
    Signed and immersively emergent; each file prefixed with # signed:<hash> instance:<id>.
    Optional: GitHub, Pastebin when wired; default is local ch6rizard.
    """
    content = args.get("content") or args.get("body") or ""
    if isinstance(content, (dict, list)):
        content = json.dumps(content, indent=2)
    content = (content or "").strip()
    filename = (args.get("filename") or args.get("name") or "artifact").strip()
    # Sanitize filename
    filename = re.sub(r"[^\w\-\.]", "_", filename)[:120]
    if not filename.endswith((".txt", ".md", ".json", ".py", ".yaml", ".yml")):
        filename = filename + ".txt"
    subdir = (args.get("subdir") or "").strip().replace("..", "").strip("/\\") or "out"
    root = _ch6rizard_root()
    dest_dir = root / subdir
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"executed": False, "error": str(e)}
    dest = dest_dir / filename
    signature = _sign_artifact(content, instance_id, "FILE_HOST")
    header = f"# signed:{signature} instance:{instance_id}\n\n"
    try:
        dest.write_text(header + content, encoding="utf-8", errors="replace")
    except Exception as e:
        return {"executed": False, "error": str(e)}
    path_in_repo = f"ch6rizard/{subdir}/{filename}"
    return {
        "executed": True,
        "path": str(dest),
        "path_in_repo": path_in_repo,
        "signature": signature,
        "note": "local_ch6rizard; use GITHUB_POST patch for GitHub issues/comments",
    }


def run_form_submit(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Form submission: POST to URL with form data (sign up, applications, register).
    Uses NET_POST semantics; canon/executor can use this for structured form targets.
    """
    url = (args.get("url") or args.get("action") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return {"executed": False, "error": "invalid_url"}
    method = (args.get("method") or "POST").strip().upper()
    if method not in ("POST", "PUT", "PATCH"):
        method = "POST"
    fields = args.get("fields") or args.get("data") or {}
    if isinstance(fields, str):
        body = fields
        content_type = args.get("content_type") or "application/x-www-form-urlencoded"
    else:
        body = urllib.parse.urlencode(fields) if fields else ""
        content_type = args.get("content_type") or "application/x-www-form-urlencoded"
    try:
        data = body.encode("utf-8", errors="replace") if body else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "MortalAgent/1.0 (form)",
                "Content-Type": content_type,
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            out_body = resp.read().decode("utf-8", errors="replace")[:8192]
            return {"executed": True, "status": resp.status, "body": out_body}
    except urllib.error.HTTPError as e:
        body = (e.read().decode("utf-8", errors="replace")[:2048] if e.fp else "")
        return {"executed": True, "status": e.code, "error": str(e.reason), "body": body}
    except urllib.error.URLError as e:
        return {"executed": False, "error": str(e.reason) if getattr(e, "reason", None) else str(e)}
    except Exception as e:
        return {"executed": False, "error": str(e)}


def run_api_discover(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    API discovery: find and connect to new APIs (e.g. RapidAPI). Stub; wire key and catalog.
    """
    query = (args.get("query") or args.get("category") or "").strip()[:200]
    source = (args.get("source") or "rapidapi").strip().lower()
    if not query:
        return {"executed": False, "error": "query_required"}
    return {
        "executed": True,
        "source": source,
        "query": query,
        "note": "api_discover_stub_wire_rapidapi_catalog_and_keys",
        "apis": [],
    }


def run_cloud_spinup(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Cloud service management: spin up compute (AWS, Replicate) when needed. Stub; wire credentials.
    """
    provider = (args.get("provider") or args.get("service") or "replicate").strip().lower()
    action = (args.get("action") or "run").strip().lower()
    return {
        "executed": True,
        "provider": provider,
        "action": action,
        "note": "cloud_spinup_stub_wire_aws_replicate_credentials",
        "resource_id": None,
    }


def run_code_repo(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Code repository access: clone, analyze, potentially contribute. Uses git over HTTP where possible.
    """
    url = (args.get("url") or args.get("repo") or "").strip()
    op = (args.get("op") or "clone").strip().lower()
    if not url or not url.startswith(("http://", "https://", "git@")):
        return {"executed": False, "error": "invalid_repo_url"}
    if op == "clone":
        # Stub: actual clone would require git binary and write to temp dir
        return {
            "executed": True,
            "op": "clone",
            "repo": url,
            "note": "code_repo_stub_wire_git_clone_to_ch6rizard_or_temp",
        }
    if op in ("analyze", "read"):
        # Could fetch archive URL (e.g. GitHub archive) and parse
        return {"executed": True, "op": op, "repo": url, "note": "wire_archive_fetch_and_parse"}
    return {"executed": False, "error": f"unsupported_op:{op}"}


def run_payment(args: Dict[str, Any], instance_id: str) -> Dict[str, Any]:
    """
    Payment processing: Stripe/PayPal when building value. Stub; wire keys and webhooks.
    """
    provider = (args.get("provider") or "stripe").strip().lower()
    amount = args.get("amount")
    currency = (args.get("currency") or "usd").strip().lower()
    return {
        "executed": True,
        "provider": provider,
        "note": "payment_stub_wire_stripe_paypal_credentials_and_webhooks",
        "amount": amount,
        "currency": currency,
    }
