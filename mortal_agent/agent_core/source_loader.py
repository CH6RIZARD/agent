"""
Load identity/ideology source from saved/bundles, saved/claude_export, saved/claude_web_chats,
and optional docx files (e.g. Downloads). Fed into the mortal agent's system prompt.

IDEOLOGY, NOT MEMORY: memories.json and chat exports are treated as ideology feed
(values, beliefs, style, doctrine)—NOT continuity or episodic memory. They inform
what the agent says, not "what it remembers from last life." No persistence of self.
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple, Any

# Repo root (parent of mortal_agent)
_AGENT_CORE = Path(__file__).resolve().parent
_MORTAL_ROOT = _AGENT_CORE.parent
_REPO_ROOT = _MORTAL_ROOT.parent

# Paths under repo
BUNDLES_DIR = _REPO_ROOT / "saved" / "bundles"
CLAUDE_EXPORT_DIR = _REPO_ROOT / "saved" / "claude_export"
WEB_CHATS_DIR = _REPO_ROOT / "saved" / "claude_web_chats" / "save"
EXTRACTED_DIR = _REPO_ROOT / "agent_source_data" / "extracted"

# Downloads docx (ideology sources) - try exact names and common variants
DOWNLOADS_BASE = Path(r"C:\Users\chiagozie\Downloads")
DOWNLOADS_DOCX_NAMES = [
    "theology.docx",
    "surgents file .docx",
    "surgeon's file.docx",
    "surgeons file.docx",
    "closepd loop code openw orld .docx",
    "closed loop code open world.docx",
    "LOCKED ROOM RIGHT(impact.docx",
    "LOCKED ROOM RIGHT impact.docx",
    "LOCKED ROOM RIGHT(impact).docx",
]

# Per-source and total caps (chars) so we don't blow LLM context
MAX_BUNDLE_CHARS = 22000
MAX_FINAL_BUNDLE_CHARS = 25000
MAX_MEMORIES_CHARS = 12000
MAX_WEB_CHAT_CHARS_PER_FILE = 4000
MAX_DOCX_CHARS_PER_FILE = 15000
MAX_EXTRACTED_CHARS_PER_FILE = 8000
MAX_TOTAL_SOURCE_CHARS = 65000


def _read_text(path: Path, encoding: str = "utf-8", errors: str = "replace") -> str:
    try:
        return path.read_text(encoding=encoding, errors=errors)
    except Exception:
        return ""


def _truncate(text: str, max_chars: int, suffix: str = "\n\n[... truncated]") -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    return text[: max_chars - len(suffix)].rstrip() + suffix


def load_markdown(path: Path, max_chars: Optional[int] = None) -> str:
    if not path.exists() or not path.suffix.lower() == ".md":
        return ""
    text = _read_text(path)
    if max_chars and len(text) > max_chars:
        text = _truncate(text, max_chars)
    return text.strip()


def load_docx(path: Path, max_chars: Optional[int] = None) -> str:
    if not path.exists():
        return ""
    try:
        import docx
        doc = docx.Document(path)
        parts = []
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text)
        text = "\n\n".join(parts)
        if max_chars and len(text) > max_chars:
            text = _truncate(text, max_chars)
        return text.strip()
    except ImportError:
        return ""
    except Exception:
        return ""


def load_bundles(repo_root: Optional[Path] = None) -> str:
    root = repo_root or _REPO_ROOT
    bundles_dir = root / "saved" / "bundles"
    if not bundles_dir.exists():
        return ""
    out = []
    # final_agent_bundle.md first (main ideology bundle)
    p = bundles_dir / "final_agent_bundle.md"
    if p.exists():
        out.append("## Bundle: final_agent_bundle\n\n" + _truncate(_read_text(p), MAX_FINAL_BUNDLE_CHARS))
    for name in ["additional_docs.md", "creati_pack.md", "save_chats.md"]:
        p = bundles_dir / name
        if p.exists():
            out.append("## Bundle: " + name + "\n\n" + _truncate(_read_text(p), MAX_BUNDLE_CHARS))
    return "\n\n---\n\n".join(out)


def load_memories(repo_root: Optional[Path] = None) -> str:
    """Load Claude export memories as IDEOLOGY (values/style), not continuity memory."""
    root = repo_root or _REPO_ROOT
    p = root / "saved" / "claude_export" / "memories.json"
    if not p.exists():
        return ""
    try:
        raw = _read_text(p)
        if len(raw) > 500_000:
            raw = raw[:500_000] + "]"
        data = json.loads(raw)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if isinstance(data, dict):
            parts = []
            if "conversations_memory" in data:
                parts.append(_truncate(str(data["conversations_memory"]), MAX_MEMORIES_CHARS // 2))
            if "project_memories" in data and isinstance(data["project_memories"], dict):
                for k, v in data["project_memories"].items():
                    parts.append(_truncate(str(v), MAX_MEMORIES_CHARS // 3))
            return "## Ideology: prior conversations (values/style)\n\n" + "\n\n".join(parts)
    except Exception:
        pass
    return ""


def load_web_chats(repo_root: Optional[Path] = None) -> str:
    """Load web chats as IDEOLOGY (beliefs/doctrine/style), not continuity memory.
    File order is shuffled each load via HolyRNG (same RNG as rest of agent)."""
    root = repo_root or _REPO_ROOT
    save_dir = root / "saved" / "claude_web_chats" / "save"
    if not save_dir.exists():
        return ""
    md_files = list(save_dir.glob("*.md"))
    if md_files:
        from .holy_rng import HolyRNG, seed_from_entropy
        rng = HolyRNG(seed_from_entropy())
        rng.shuffle(md_files)
    parts = []
    for f in md_files:
        t = load_markdown(f, MAX_WEB_CHAT_CHARS_PER_FILE)
        if t:
            parts.append("### " + f.stem + "\n\n" + t)
    if not parts:
        return ""
    return "## Ideology: web chats (beliefs/doctrine/style)\n\n" + "\n\n---\n\n".join(parts)


def load_extracted(repo_root: Optional[Path] = None) -> str:
    root = repo_root or _REPO_ROOT
    extracted = root / "agent_source_data" / "extracted"
    if not extracted.exists():
        return ""
    parts = []
    for name in ["constitution_raw.md", "doctrine_raw.md", "theological_statements.md", "red_lines.md", "style_samples.txt"]:
        p = extracted / name
        if p.exists():
            t = _truncate(_read_text(p), MAX_EXTRACTED_CHARS_PER_FILE)
            if t.strip():
                parts.append("## Extracted: " + name + "\n\n" + t.strip())
    return "\n\n---\n\n".join(parts) if parts else ""


def load_downloads_docx(downloads_base: Optional[Path] = None) -> str:
    base = downloads_base or DOWNLOADS_BASE
    if not base.exists():
        return ""
    found = []
    for name in DOWNLOADS_DOCX_NAMES:
        p = base / name
        if p.exists():
            t = load_docx(p, MAX_DOCX_CHARS_PER_FILE)
            if t:
                found.append("## Docx: " + name + "\n\n" + t)
    return "\n\n---\n\n".join(found)


def _shuffle_with_rng(items: List[Any], rng: Any) -> None:
    """Fisher-Yates shuffle in place. rng must have randint(a, b) inclusive."""
    for i in range(len(items) - 1, 0, -1):
        j = rng.randint(0, i)
        items[i], items[j] = items[j], items[i]


def collect_all_source_items(
    repo_root: Optional[Path] = None,
    downloads_base: Optional[Path] = None,
) -> List[Tuple[str, str]]:
    """
    Collect all source items as (label, text) pairs.
    Each item is one file or logical chunk. Used by load_all_source_sampled.
    """
    root = repo_root or _REPO_ROOT
    base = downloads_base or DOWNLOADS_BASE
    items: List[Tuple[str, str]] = []

    # Extracted
    extracted = root / "agent_source_data" / "extracted"
    if extracted.exists():
        for name in ["constitution_raw.md", "doctrine_raw.md", "theological_statements.md", "red_lines.md", "style_samples.txt"]:
            p = extracted / name
            if p.exists():
                t = _truncate(_read_text(p), MAX_EXTRACTED_CHARS_PER_FILE).strip()
                if t:
                    items.append((f"extracted:{name}", "## Extracted: " + name + "\n\n" + t))

    # Bundles
    bundles_dir = root / "saved" / "bundles"
    if bundles_dir.exists():
        p = bundles_dir / "final_agent_bundle.md"
        if p.exists():
            t = _truncate(_read_text(p), MAX_FINAL_BUNDLE_CHARS).strip()
            if t:
                items.append(("bundle:final_agent_bundle", "## Bundle: final_agent_bundle\n\n" + t))
        for name in ["additional_docs.md", "creati_pack.md", "save_chats.md"]:
            p = bundles_dir / name
            if p.exists():
                t = _truncate(_read_text(p), MAX_BUNDLE_CHARS).strip()
                if t:
                    items.append((f"bundle:{name}", "## Bundle: " + name + "\n\n" + t))

    # Memories
    mem_text = load_memories(root)
    if mem_text.strip():
        items.append(("memories", mem_text))

    # Web chats - one item per .md file
    save_dir = root / "saved" / "claude_web_chats" / "save"
    if save_dir.exists():
        for f in sorted(save_dir.glob("*.md"), key=lambda x: x.name, reverse=True):
            t = load_markdown(f, MAX_WEB_CHAT_CHARS_PER_FILE)
            if t:
                items.append((f"web_chat:{f.stem}", "### " + f.stem + "\n\n" + t))

    # Downloads docx
    if base.exists():
        for name in DOWNLOADS_DOCX_NAMES:
            p = base / name
            if p.exists():
                t = load_docx(p, MAX_DOCX_CHARS_PER_FILE)
                if t:
                    items.append((f"docx:{name}", "## Docx: " + name + "\n\n" + t))

    return items


def load_all_source_sampled(
    repo_root: Optional[Path] = None,
    downloads_base: Optional[Path] = None,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
    rng: Optional[Any] = None,
) -> str:
    """
    Load ideology source with TempleOS holy RNG: shuffle items, fill to cap.
    Each call yields a different random subset. Use per interaction for varied context.
    """
    if rng is None:
        from .holy_rng import HolyRNG, seed_from_entropy
        rng = HolyRNG(seed_from_entropy())
    items = collect_all_source_items(repo_root, downloads_base)
    if not items:
        return ""
    _shuffle_with_rng(items, rng)
    sections: List[str] = []
    total = 0
    for _label, text in items:
        if total >= max_total_chars or not text.strip():
            continue
        if total + len(text) > max_total_chars:
            text = _truncate(text, max_total_chars - total)
        sections.append(text)
        total += len(text)
    combined = "\n\n---\n\n".join(sections)
    if len(combined) > max_total_chars:
        combined = _truncate(combined, max_total_chars)
    return combined.strip()


def load_all_source(
    repo_root: Optional[Path] = None,
    downloads_base: Optional[Path] = None,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
) -> str:
    """Load all ideology sources; returns combined string. Use load_all_source_with_labels for startup display."""
    text, _ = load_all_source_with_labels(repo_root, downloads_base, max_total_chars)
    return text


def load_all_source_with_labels(
    repo_root: Optional[Path] = None,
    downloads_base: Optional[Path] = None,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
) -> Tuple[str, List[str]]:
    """
    Load all ideology sources; return (combined string, list of source labels that had content).
    Labels: extracted, bundles, memories, web_chats, docx. For display: "Source loaded: bundles, web_chats, docx (ideology)".
    """
    root = repo_root or _REPO_ROOT
    base = downloads_base or DOWNLOADS_BASE

    sections: List[str] = []
    labels: List[str] = []
    total = 0

    def add(label: str, text: str) -> None:
        nonlocal total
        if not text.strip() or total >= max_total_chars:
            return
        if total + len(text) > max_total_chars:
            text = _truncate(text, max_total_chars - total)
        sections.append(text)
        total += len(text)
        labels.append(label)

    add("extracted", load_extracted(root))
    add("bundles", load_bundles(root))
    add("memories", load_memories(root))
    add("web_chats", load_web_chats(root))
    add("docx", load_downloads_docx(base))

    combined = "\n\n---\n\n".join(sections)
    if len(combined) > max_total_chars:
        combined = _truncate(combined, max_total_chars)
    return combined.strip(), labels


def get_system_with_source(identity_statement: str, source_context: str, max_system_chars: int = 100_000) -> str:
    """Combine identity statement and source context for LLM system prompt."""
    if not source_context.strip():
        return identity_statement
    combined = identity_statement + "\n\n---\n\n[Source (for relevance only): constitution, doctrine, theology, chats]\n\n" + source_context
    if len(combined) > max_system_chars:
        combined = _truncate(combined, max_system_chars, suffix="\n\n[... system context truncated]")
    return combined
