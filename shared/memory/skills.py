"""shared/memory/skills.py — SAHOOL Farm Memory: skill loader.

Parses structured Markdown skill files into typed dictionaries.
Each skill file lives under shared/memory/skills/*.md.

Skill dict structure:
    {
        "title": str,
        "when_to_use": str,
        "procedure": list[str],
        "pitfalls": list[str],
    }
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"

# Map canonical names to filenames
_SKILL_FILES: dict[str, str] = {
    "crop_advisor": "crop_advisor_skill.md",
    "irrigation": "irrigation_skill.md",
    "pest_diagnosis": "pest_diagnosis_skill.md",
}


def _parse_skill_md(text: str) -> dict[str, Any]:
    """Parse a skill Markdown file into a structured dict.

    Sections parsed:
    - Title: first ``# ...`` heading
    - When to use: text under ``## When to use``
    - Procedure: ordered list under ``## Procedure``
    - Pitfalls: unordered list under ``## Pitfalls``

    Parameters
    ----------
    text:
        Raw Markdown content of the skill file.

    Returns
    -------
    dict
        Parsed skill with keys: title, when_to_use, procedure, pitfalls.
    """
    lines = text.splitlines()

    title = ""
    when_to_use = ""
    procedure: list[str] = []
    pitfalls: list[str] = []

    current_section = ""

    for line in lines:
        stripped = line.strip()

        # Title (H1)
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            continue

        # Section headings (H2)
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            if "when to use" in heading:
                current_section = "when_to_use"
            elif "procedure" in heading:
                current_section = "procedure"
            elif "pitfall" in heading:
                current_section = "pitfalls"
            else:
                current_section = "other"
            continue

        if not stripped:
            continue

        if current_section == "when_to_use":
            when_to_use = (when_to_use + " " + stripped).strip() if when_to_use else stripped

        elif current_section == "procedure":
            # Match numbered list: "1. ..." or "1) ..."
            m = re.match(r"^\d+[.)]\s+(.+)$", stripped)
            if m:
                procedure.append(m.group(1).strip())

        elif current_section == "pitfalls":
            # Match unordered list: "- ..." or "* ..."
            m = re.match(r"^[-*]\s+(.+)$", stripped)
            if m:
                pitfalls.append(m.group(1).strip())

    return {
        "title": title,
        "when_to_use": when_to_use,
        "procedure": procedure,
        "pitfalls": pitfalls,
    }


def load_skill(name: str) -> dict[str, Any]:
    """Load and parse a skill by name.

    Parameters
    ----------
    name:
        Skill name: one of ``crop_advisor`` | ``irrigation`` | ``pest_diagnosis``.
        Also accepts the full filename without extension (e.g. ``crop_advisor_skill``).

    Returns
    -------
    dict
        Parsed skill: {title, when_to_use, procedure: list[str], pitfalls: list[str]}.

    Raises
    ------
    KeyError
        If the skill name is not recognised.
    FileNotFoundError
        If the skill file does not exist.
    """
    # Normalise: strip _skill suffix if present, lowercase
    key = name.lower().removesuffix("_skill")
    if key not in _SKILL_FILES:
        raise KeyError(f"مهارة غير معروفة: {name!r}. المهارات المتاحة: {list(_SKILL_FILES)}")

    skill_path = _SKILLS_DIR / _SKILL_FILES[key]
    if not skill_path.exists():
        raise FileNotFoundError(
            f"ملف المهارة غير موجود: {skill_path}. تأكد من وجود الملف في {_SKILLS_DIR}"
        )

    text = skill_path.read_text(encoding="utf-8")
    skill = _parse_skill_md(text)
    logger.debug("skills: loaded '%s' from %s", name, skill_path.name)
    return skill


def list_skills() -> list[str]:
    """Return the list of available skill names.

    Returns
    -------
    list[str]
        Sorted list of canonical skill names (e.g. ["crop_advisor", ...]).
    """
    return sorted(_SKILL_FILES.keys())
