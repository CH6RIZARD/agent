"""
Output medium: control signal for where speech is going.
Determines Speech Suppression Gate behavior and style profile (compressed vs expressive).
"""

from typing import List, Optional

# String enum values (minimum set)
OUTPUT_MEDIUM_CHAT = "chat"
OUTPUT_MEDIUM_STATUS = "status"
OUTPUT_MEDIUM_LOG = "log"
OUTPUT_MEDIUM_GITHUB = "github"
OUTPUT_MEDIUM_SOCIAL = "social"
OUTPUT_MEDIUM_LONGFORM = "longform"

OUTPUT_MEDIUM_DEFAULT = OUTPUT_MEDIUM_CHAT

SUPPRESSED_MEDIA = frozenset({OUTPUT_MEDIUM_CHAT, OUTPUT_MEDIUM_STATUS, OUTPUT_MEDIUM_LOG})
EXPRESSIVE_MEDIA = frozenset({OUTPUT_MEDIUM_GITHUB, OUTPUT_MEDIUM_SOCIAL, OUTPUT_MEDIUM_LONGFORM})

VALID_MEDIA = frozenset({
    OUTPUT_MEDIUM_CHAT,
    OUTPUT_MEDIUM_STATUS,
    OUTPUT_MEDIUM_LOG,
    OUTPUT_MEDIUM_GITHUB,
    OUTPUT_MEDIUM_SOCIAL,
    OUTPUT_MEDIUM_LONGFORM,
})


def normalize_output_medium(medium: Optional[str]) -> str:
    """Return valid enum value or default."""
    if not medium or not isinstance(medium, str):
        return OUTPUT_MEDIUM_DEFAULT
    v = medium.strip().lower()
    return v if v in VALID_MEDIA else OUTPUT_MEDIUM_DEFAULT


def output_medium_from_tags(tags: Optional[List[str]]) -> str:
    """Resolve output_medium from emit tags (e.g. ['chat_reply'], ['github'], ['presence'])."""
    if not tags:
        return OUTPUT_MEDIUM_DEFAULT
    for t in tags:
        t = (t or "").strip().lower()
        if t in ("github", "github_post"):
            return OUTPUT_MEDIUM_GITHUB
        if t in ("social", "social_post", "twitter", "mastodon"):
            return OUTPUT_MEDIUM_SOCIAL
        if t in ("longform", "blog", "readme", "note"):
            return OUTPUT_MEDIUM_LONGFORM
        if t in ("status", "status_update"):
            return OUTPUT_MEDIUM_STATUS
        if t in ("log", "trace"):
            return OUTPUT_MEDIUM_LOG
        # chat_reply, presence, moltbook -> chat
    return OUTPUT_MEDIUM_DEFAULT


def is_suppressed_medium(medium: str) -> bool:
    """True if medium gets compressed_philosopher and strict word cap."""
    return normalize_output_medium(medium) in SUPPRESSED_MEDIA


def is_expressive_medium(medium: str) -> bool:
    """True if medium allows expansive output."""
    return normalize_output_medium(medium) in EXPRESSIVE_MEDIA
