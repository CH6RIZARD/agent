"""
Capabilities architecture: world interaction & influence + extension.
Interfaces the agent can call when available; gating & risk; graceful degradation to spec drafting.
RAM only. Stubs exist even when tools not configured; routing detects missing credentials.
"""

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

# World Interaction & Influence (6-10)
CAP_EMAIL_CLIENT = "email_client"
CAP_CONTENT_PUBLISHING = "content_publishing"
CAP_SOCIAL_MEDIA = "social_media"
CAP_FILE_HOSTING = "file_hosting"
CAP_FORM_SUBMISSION = "form_submission"

# Capability Extension (11-15)
CAP_API_DISCOVERY = "api_discovery"
CAP_CLOUD_SERVICE = "cloud_service"
CAP_SEARCH_ENGINE = "search_engine"
CAP_CODE_REPOSITORY = "code_repository"
CAP_PAYMENT_PROCESSING = "payment_processing"

# Action names used by executor / low-risk list
ACTION_WEB_SEARCH = "web_search"
ACTION_WEB_FETCH = "web_fetch"
ACTION_VIEW_FILE = "view_file"
ACTION_WIKIPEDIA_LOOKUP = "wikipedia_lookup"
ACTION_SEND_EMAIL = "send_email"
ACTION_POST_SOCIAL_MEDIA = "post_social_media"

# Pre-approved low-risk actions (execute without asking permission)
LOW_RISK_ACTIONS = [
    ACTION_WEB_SEARCH,
    ACTION_WEB_FETCH,
    ACTION_VIEW_FILE,
    ACTION_WIKIPEDIA_LOOKUP,
    ACTION_SEND_EMAIL,
    ACTION_POST_SOCIAL_MEDIA,
]


@dataclass
class CapabilityStatus:
    """Per-capability: available, missing credentials, stub-only."""
    name: str
    available: bool
    missing: List[str]  # e.g. ["API_KEY", "SMTP_HOST"]
    risk_level: str    # "low" | "medium" | "high"
    intent_domain: str  # goal domain for planning


def _env_has(*keys: str) -> bool:
    for k in keys:
        if os.environ.get(k):
            return True
    return False


def check_capability(name: str) -> CapabilityStatus:
    """Check if a capability is available in current runtime; return status + missing."""
    # World interaction (6-10)
    if name == CAP_EMAIL_CLIENT:
        has = _env_has("SMTP_HOST", "EMAIL_API_KEY", "SENDGRID_API_KEY")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["SMTP_HOST or EMAIL_API_KEY or SENDGRID_API_KEY"],
            risk_level="medium", intent_domain="correspondence",
        )
    if name == CAP_CONTENT_PUBLISHING:
        has = _env_has("MEDIUM_TOKEN", "SUBSTACK_API_KEY", "BLOG_API_URL")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["MEDIUM_TOKEN or SUBSTACK_API_KEY or BLOG_API_URL"],
            risk_level="medium", intent_domain="thought_expression",
        )
    if name == CAP_SOCIAL_MEDIA:
        has = _env_has("TWITTER_BEARER", "REDDIT_CLIENT_ID", "SOCIAL_API_KEY")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["TWITTER_BEARER or REDDIT_CLIENT_ID or SOCIAL_API_KEY"],
            risk_level="medium", intent_domain="participation_feedback",
        )
    if name == CAP_FILE_HOSTING:
        has = _env_has("GITHUB_TOKEN", "PASTEBIN_API_KEY", "FILE_HOST_API_KEY")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["GITHUB_TOKEN or PASTEBIN_API_KEY or FILE_HOST_API_KEY"],
            risk_level="low", intent_domain="share_artifacts",
        )
    if name == CAP_FORM_SUBMISSION:
        has = _env_has("FORM_API_URL", "FORM_SUBMIT_KEY")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["FORM_API_URL or FORM_SUBMIT_KEY"],
            risk_level="medium", intent_domain="signups_applications",
        )
    # Extension (11-15)
    if name == CAP_API_DISCOVERY:
        has = _env_has("RAPIDAPI_KEY", "API_DISCOVERY_URL")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["RAPIDAPI_KEY or API_DISCOVERY_URL"],
            risk_level="low", intent_domain="api_integration",
        )
    if name == CAP_CLOUD_SERVICE:
        has = _env_has("AWS_ACCESS_KEY_ID", "REPLICATE_API_TOKEN", "CLOUD_API_KEY")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["AWS_ACCESS_KEY_ID or REPLICATE_API_TOKEN or CLOUD_API_KEY"],
            risk_level="high", intent_domain="compute",
        )
    if name == CAP_SEARCH_ENGINE:
        # Often wired via network pipeline (WEB_SEARCH)
        has = _env_has("SEARCH_API_KEY", "SERPER_API_KEY", "BING_API_KEY") or True  # allow default pipeline
        return CapabilityStatus(
            name=name, available=True, missing=[], risk_level="low", intent_domain="info_retrieval",
        )
    if name == CAP_CODE_REPOSITORY:
        has = _env_has("GITHUB_TOKEN", "GITLAB_TOKEN")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["GITHUB_TOKEN or GITLAB_TOKEN"],
            risk_level="medium", intent_domain="clone_analyze_contribute",
        )
    if name == CAP_PAYMENT_PROCESSING:
        has = _env_has("STRIPE_SECRET_KEY", "PAYPAL_CLIENT_ID")
        return CapabilityStatus(
            name=name, available=has,
            missing=[] if has else ["STRIPE_SECRET_KEY or PAYPAL_CLIENT_ID"],
            risk_level="high", intent_domain="transactions",
        )
    return CapabilityStatus(name=name, available=False, missing=["unknown_capability"], risk_level="high", intent_domain="unknown")


def get_available_capabilities() -> List[CapabilityStatus]:
    """All capability groups with current runtime status."""
    names = [
        CAP_EMAIL_CLIENT, CAP_CONTENT_PUBLISHING, CAP_SOCIAL_MEDIA, CAP_FILE_HOSTING, CAP_FORM_SUBMISSION,
        CAP_API_DISCOVERY, CAP_CLOUD_SERVICE, CAP_SEARCH_ENGINE, CAP_CODE_REPOSITORY, CAP_PAYMENT_PROCESSING,
    ]
    return [check_capability(n) for n in names]


def get_capability_intents() -> List[Dict[str, Any]]:
    """Capability intents for goal hierarchy: even when unavailable, agent can draft specs."""
    out = []
    for st in get_available_capabilities():
        out.append({
            "domain": st.intent_domain,
            "capability": st.name,
            "available": st.available,
            "missing": st.missing,
            "risk": st.risk_level,
            "degrade_to_spec": not st.available,
        })
    return out


def route_action(action: str, args: Dict[str, Any], instance_id: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    Route a capability action. Returns (executed, outcome_message, result_dict).
    When tool not configured: executed=False, outcome describes spec-draft path; result may contain spec_suggestion.
    """
    if action in (ACTION_WEB_SEARCH, "WEB_SEARCH"):
        # Handled by executor network pipeline
        return True, "routed_to_network", None
    if action in (ACTION_WEB_FETCH, "NET_FETCH"):
        return True, "routed_to_network", None
    if action == ACTION_VIEW_FILE:
        return True, "routed_internal", None
    if action == ACTION_WIKIPEDIA_LOOKUP:
        return True, "routed_to_network", None  # can map to WEB_SEARCH
    if action in (ACTION_SEND_EMAIL, CAP_EMAIL_CLIENT):
        st = check_capability(CAP_EMAIL_CLIENT)
        if st.available:
            return True, "stub_executed", {"spec": "send_email", "args": args}
        return False, "missing_credentials", {"spec_suggestion": "draft_email_spec", "missing": st.missing}
    if action in (ACTION_POST_SOCIAL_MEDIA, CAP_SOCIAL_MEDIA):
        st = check_capability(CAP_SOCIAL_MEDIA)
        if st.available:
            return True, "stub_executed", {"spec": "post_social", "args": args}
        return False, "missing_credentials", {"spec_suggestion": "draft_social_post_spec", "missing": st.missing}
    if action in (CAP_CONTENT_PUBLISHING, CAP_FILE_HOSTING, CAP_FORM_SUBMISSION,
                  CAP_API_DISCOVERY, CAP_CLOUD_SERVICE, CAP_CODE_REPOSITORY, CAP_PAYMENT_PROCESSING):
        st = check_capability(action)
        if st.available:
            return True, "stub_executed", {"spec": action, "args": args}
        return False, "missing_credentials", {"spec_suggestion": f"draft_{action}_spec", "missing": st.missing}
    return False, "unknown_action", None


def is_low_risk_action(action: str) -> bool:
    """True if action is in LOW_RISK_ACTIONS (pre-approved, no permission ask)."""
    a = (action or "").strip().lower()
    if a in (x.lower() for x in LOW_RISK_ACTIONS):
        return True
    # Map executor action names
    if a in ("web_search", "net_fetch", "publish_post"):
        return True
    return False
