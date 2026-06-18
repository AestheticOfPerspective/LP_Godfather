from __future__ import annotations
from typing import Optional
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "interviewers.yaml"

_cached_data: dict | None = None

def _load():
    global _cached_data
    if _cached_data is None:
        with open(_CONFIG_PATH) as f:
            _cached_data = yaml.safe_load(f)
    return _cached_data

def interviewer_prompt(name: str) -> str | None:
    data = _load()
    entry = data.get("interviewers", {}).get(name)
    return entry["prompt"] if entry else None

def all_interviewer_prompts() -> dict[str, str]:
    data = _load()
    return {k: v["prompt"] for k, v in data.get("interviewers", {}).items()}

def resolve_alias(name: str) -> str | None:
    data = _load()
    name = name.lower().strip()
    aliases = data.get("aliases", {})
    if name in aliases:
        return aliases[name]
    if name in data.get("interviewers", {}):
        return name
    return None

def hard_mode_sequence() -> list[str]:
    data = _load()
    return data.get("hard_mode_sequence", [])

# Re-export as lazy callable for backward compat
def get_prompts():
    return all_interviewer_prompts()
