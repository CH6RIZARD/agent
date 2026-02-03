"""
Output policy: ban second-person + meta; compact in-world replies only.
Thin wrapper over response_policy and output_sanitizer. Enforced at final output boundary.
"""

from typing import Optional


def apply_output_policy(
    text: str,
    user_text: str = "",
    recent_messages: Optional[list] = None,
) -> str:
    """
    Enforce: no second-person, no meta disclaimers, compact replies.
    Runs after all generation. No identity sermons.
    """
    if not text or not text.strip():
        return text
    recent = recent_messages or []
    try:
        from .response_policy import assess_depth, enforce_policy, compress_to_depth
        depth = assess_depth(user_text)
        out = enforce_policy(text, user_text, recent)
        out = compress_to_depth(out, depth)
    except Exception:
        out = text
    intermediate = out or text
    try:
        from .output_sanitizer import enforce_no_user_attribution
        return enforce_no_user_attribution(intermediate) or intermediate
    except Exception:
        return intermediate
