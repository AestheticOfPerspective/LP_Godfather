"""utils/skill_store.py — Skill file management.

Manages skill packs on disk under skills/<name>/SKILL.md.
State (draft vs active) is tracked in skills/manifest.json.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_MANIFEST_PATH = _SKILLS_DIR / "manifest.json"


def _ensure_dirs():
    _SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict:
    _ensure_dirs()
    if _MANIFEST_PATH.exists():
        try:
            return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load skill manifest: %s", e)
    return {}


def _save_manifest(manifest: dict) -> None:
    _ensure_dirs()
    try:
        _MANIFEST_PATH.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        logger.error("Failed to save skill manifest: %s", e)


def list_skills() -> list[dict]:
    manifest = _load_manifest()
    result = []
    for name, meta in manifest.items():
        result.append({
            "name": name,
            "state": meta.get("state", "draft"),
            "description": meta.get("description", ""),
            "created_at": meta.get("created_at", ""),
        })
    result.sort(key=lambda s: s["name"])
    return result


def list_active_skills() -> list[dict]:
    return [s for s in list_skills() if s["state"] == "active"]


def read_skill(name: str) -> str | None:
    skill_dir = _SKILLS_DIR / _safe_name(name)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        return skill_file.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Failed to read skill %s: %s", name, e)
        return None


def create_skill(name: str, content: str, description: str = "") -> bool:
    _ensure_dirs()
    safe = _safe_name(name)
    skill_dir = _SKILLS_DIR / safe
    skill_file = skill_dir / "SKILL.md"

    if skill_file.exists():
        return False

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content.strip() + "\n", encoding="utf-8")

        manifest = _load_manifest()
        manifest[safe] = {
            "state": "draft",
            "description": description or _extract_description(content),
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }
        _save_manifest(manifest)
        return True
    except OSError as e:
        logger.error("Failed to create skill %s: %s", name, e)
        return False


def activate_skill(name: str) -> bool:
    safe = _safe_name(name)
    skill_dir = _SKILLS_DIR / safe
    if not (skill_dir / "SKILL.md").exists():
        return False

    manifest = _load_manifest()
    if safe not in manifest:
        return False

    manifest[safe]["state"] = "active"
    _save_manifest(manifest)
    return True


def delete_skill(name: str) -> bool:
    safe = _safe_name(name)
    skill_dir = _SKILLS_DIR / safe
    if not skill_dir.exists():
        return False

    import shutil
    try:
        shutil.rmtree(skill_dir)
        manifest = _load_manifest()
        manifest.pop(safe, None)
        _save_manifest(manifest)
        return True
    except OSError as e:
        logger.error("Failed to delete skill %s: %s", name, e)
        return False


def match_skills(text: str) -> list[tuple[str, str]]:
    """Find active skills whose Signals section matches the message text.

    Returns list of (name, SKILL.md content) sorted by relevance.
    """
    text_lower = text.lower()
    matches = []
    for skill in list_active_skills():
        name = skill["name"]
        content = read_skill(name)
        if not content:
            continue
        signals = _extract_signals(content)
        if not signals:
            continue
        score = sum(1 for signal in signals if signal in text_lower)
        if score > 0:
            matches.append((score, name, content))
    matches.sort(key=lambda m: m[0], reverse=True)
    return [(name, content) for score, name, content in matches]


def _extract_description(content: str) -> str:
    match = re.search(r"^## Description\s*\n(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_signals(content: str) -> list[str]:
    match = re.search(
        r"^## Signals\s*\n(.+?)(?:\n##|\Z)", content, re.MULTILINE | re.DOTALL
    )
    if not match:
        return []
    raw = match.group(1)
    return [
        kw.strip().lower()
        for kw in re.split(r"[,;]\s*", raw)
        if kw.strip()
    ]


def _safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-")) or "unnamed"


def skill_help_text() -> str:
    skills = list_skills()
    if not skills:
        return "🤖 Keine Skills vorhanden. Sag: 'bau mir einen Skill fuer <zweck>' um einen zu erstellen."
    lines = ["🤖 GodFather Skills\n"]
    for s in skills:
        emoji = "✅" if s["state"] == "active" else "📝"
        lines.append(f"{emoji} <b>{escape_html(s['name'])}</b> — {escape_html(s['description'])}")
    lines.append("\n/skills show <name> — Detail anzeigen")
    lines.append("/skills activate <name> — Draft aktivieren (Admin)")
    return "\n".join(lines)


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
