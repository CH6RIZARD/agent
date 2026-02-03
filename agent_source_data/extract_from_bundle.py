#!/usr/bin/env python3
"""Segment final_agent_bundle.md into constitution, doctrine, style, red_lines, theological."""

import re
import os

BUNDLE_PATH = "saved/bundles/final_agent_bundle.md"
OUT_DIR = "agent_source_data/extracted"

# Keywords/phrases per category (lowercase match)
CONSTITUTION = re.compile(
    r"\b(non-negotiable|axiom|immutable|core truth|foundational|Chiagozie|God has blessed|"
    r"theistic|belief|Chi\s*=|Supreme Being|God exists|irrevocable|covenant)\b",
    re.I,
)
DOCTRINE = re.compile(
    r"\b(Rule\s+\d|Step\s+\d|Layer\s+\d|architecture|procedure|policy|design principle|"
    r"approval|constraint|operational|how to integrate|backend|endpoint|guardrail)\b",
    re.I,
)
STYLE = re.compile(
    r"(Fuck|gap's there|Move\.|He's slow|short, direct|lowercase|punctuation|"
    r"trash talk|sounds like YOU|voice/style|aggressive|terse|idk)\b",
    re.I,
)
RED_LINES = re.compile(
    r"\b(never execute|forbidden|prohibit|cannot do|should never|don't put|"
    r"won't do|won't compromise|hard refusal|no guardrails|do not)\b",
    re.I,
)
THEOLOGICAL = re.compile(
    r"\b(Scripture|Qur'an|Bible|Satan|Messiah|Islam|Christianity|Judaism|"
    r"theological|Romans\s*\d|Matthew\s*\d|Chillul Hashem|Antichrist|"
    r"revelation|mediator|false messiah)\b",
    re.I,
)


def classify_block(block: str) -> list[str]:
    """Return list of category labels for this block (may be multiple)."""
    cat = []
    if CONSTITUTION.search(block):
        cat.append("constitution")
    if DOCTRINE.search(block):
        cat.append("doctrine")
    if STYLE.search(block):
        cat.append("style")
    if RED_LINES.search(block):
        cat.append("red_lines")
    if THEOLOGICAL.search(block):
        cat.append("theological")
    return cat


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(BUNDLE_PATH, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    # Split into blocks: by ## or ### headers, or by double newline
    blocks = re.split(r"\n(?=##\s|\n\n)", text)
    # Also split single-\n chunks that are large into paragraphs
    out_blocks = []
    for b in blocks:
        b = b.strip()
        if not b or len(b) < 15:
            continue
        # If block is huge, split by double newline
        if len(b) > 8000:
            for para in re.split(r"\n\s*\n", b):
                para = para.strip()
                if len(para) > 20:
                    out_blocks.append(para)
        else:
            out_blocks.append(b)

    buckets = {
        "constitution": [],
        "doctrine": [],
        "style": [],
        "red_lines": [],
        "theological": [],
    }

    for block in out_blocks:
        cats = classify_block(block)
        for c in cats:
            if c in buckets and block not in buckets[c]:
                buckets[c].append(block)

    # If a bucket is empty, add first block that has any substantive content
    fallback = next((b for b in out_blocks if len(b) > 100), text[:2000])
    for k in buckets:
        if not buckets[k]:
            buckets[k].append(fallback)

    out_files = {
        "constitution": "constitution_raw.md",
        "doctrine": "doctrine_raw.md",
        "style": "style_samples.txt",
        "red_lines": "red_lines.md",
        "theological": "theological_statements.md",
    }

    for key, filename in out_files.items():
        path = os.path.join(OUT_DIR, filename)
        content = "\n\n---\n\n".join(buckets[key])
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if not content.strip():
            with open(path, "w", encoding="utf-8") as f:
                f.write(fallback[:3000])

    # Print file list + line counts
    print("File list + line counts:")
    for key, filename in out_files.items():
        path = os.path.join(OUT_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            n = sum(1 for _ in f)
        print(f"  {filename}: {n} lines")


if __name__ == "__main__":
    main()
