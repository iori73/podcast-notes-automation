"""Loader for the editorial philosophy injected into every generation prompt.

Why this exists
---------------
The generation prompts used to carry only *rules* — length limits and a growing
list of 禁止 clauses accumulated one bug at a time. Rules tell Gemini what not to
do; they never say what a good note is *for*. The result was output that satisfied
every constraint and still read like a neutral abstract of the episode.

This module loads `config/philosophy.md`, which states the intent instead: these
notes exist to be transferable to the reader's own work, so what matters is the
central question of the episode and the specifics needed to act on it.

Keeping it in a Markdown file rather than in the prompt string means the author
can revise their editorial stance without touching Python, and the file is small
enough to prepend to every call without meaningful token cost.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

# Resolved relative to the repo root so it works regardless of CWD.
_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "philosophy.md"

_SHOW_HEADING = re.compile(r"^###\s*show:\s*(.+?)\s*$", re.M)


def _normalize(text: str) -> str:
    return re.sub(r"[\s　・.]", "", text).lower()


def _strip_comments(text: str) -> str:
    """Drop HTML comments so the commented-out usage example is not parsed as a
    real per-show section (it contains a `### show:` heading by design)."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def load_philosophy(show_name: Optional[str] = None, path: Optional[Path] = None) -> str:
    """Return the editorial philosophy, with only the matching show's section kept.

    Per-show sections live under `### show: <name>` headings. Every other show's
    section is dropped so the prompt never carries guidance for a different
    programme. Returns "" when the file is absent — the pipeline must keep working
    without it.
    """
    p = path or _DEFAULT_PATH
    try:
        raw = _strip_comments(p.read_text(encoding="utf-8"))
    except OSError:
        return ""

    marker = "## 番組別の補足"
    idx = raw.find(marker)
    if idx < 0:
        return raw.strip()

    general = raw[:idx].rstrip()
    per_show = _extract_show_section(raw[idx:], show_name)
    return f"{general}\n\n{per_show}".strip() if per_show else general


def _extract_show_section(block: str, show_name: Optional[str]) -> str:
    if not show_name:
        return ""

    matches = list(_SHOW_HEADING.finditer(block))
    if not matches:
        return ""

    target = _normalize(show_name)
    for i, m in enumerate(matches):
        heading = _normalize(m.group(1))
        # Substring either way: Spotify's show_name and the heading rarely match
        # exactly ("fukabori.fm" vs "fukabori.fm - 技術を深掘り").
        if not heading or not (heading in target or target in heading):
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        body = block[m.end():end].strip()
        if body:
            return f"この番組についての補足:\n{body}"
    return ""


def available_shows(path: Optional[Path] = None) -> List[str]:
    """Show names that currently have their own section. Useful for diagnostics."""
    p = path or _DEFAULT_PATH
    try:
        raw = _strip_comments(p.read_text(encoding="utf-8"))
    except OSError:
        return []
    return [m.group(1) for m in _SHOW_HEADING.finditer(raw)]
