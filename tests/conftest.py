from __future__ import annotations
import os
import tempfile
import shutil
from pathlib import Path
from typing import Generator

import pytest

from src.core.persona_engine import PersonaFlowEngine
from src.storage.database import Database


_FIXTURE_CONFIG = """
personas:
  godfather:
    name: "GODFATHER"
    emoji: "💀"
    style: "Fixer, pragmatisch, direkt"
    triggers: ["help", "frage", "bitte", "choom"]
    time_weight: {morning: 0.9, afternoon: 0.9, evening: 0.8, night: 0.8}
    transition_phrases:
      to: "GODFATHER on deck."
      from: "GodFather out."
  choom:
    name: "CHOOM"
    emoji: "🎮"
    style: "Gamer hype"
    triggers: ["gg", "pog", "gaming", "preem"]
    time_weight: {morning: 0.2, afternoon: 0.6, evening: 0.9, night: 0.8}
    transition_phrases:
      to: "CHOOM logging in."
      from: "CHOOM out."
  nova:
    name: "NOVA"
    emoji: "🌌"
    style: "Gene Keys bard"
    triggers: ["meaning", "purpose", "shadow", "gift"]
    time_weight: {morning: 0.3, afternoon: 0.4, evening: 0.7, night: 0.9}
    transition_phrases:
      to: "NOVA resonates."
      from: "NOVA fades."
  cyber-zen:
    name: "CYBER-ZEN"
    emoji: "🌐"
    style: "Code monk"
    triggers: ["refactor", "zen", "focus"]
    time_weight: {morning: 0.9, afternoon: 0.7, evening: 0.4, night: 0.2}
    transition_phrases:
      to: "CYBER-ZEN compiles."
      from: "CYBER-ZEN exits."
  baki:
    name: "BAKI"
    emoji: "🥊"
    style: "Raw power"
    triggers: ["grind", "push", "beast"]
    time_weight: {morning: 0.7, afternoon: 0.8, evening: 0.6, night: 0.3}
    transition_phrases:
      to: "BAKI stands ready."
      from: "BAKI rests."
  samurai:
    name: "SAMURAI"
    emoji: "⚔️"
    style: "Warrior code"
    triggers: ["discipline", "honor", "mastery"]
    time_weight: {morning: 0.8, afternoon: 0.6, evening: 0.5, night: 0.4}
    transition_phrases:
      to: "SAMURAI draws."
      from: "SAMURAI sheathes."
  punk-philosopher:
    name: "PUNK-PHILOSOPHER"
    emoji: "🤘"
    style: "Deep rebel"
    triggers: ["why", "truth", "system"]
    time_weight: {morning: 0.5, afternoon: 0.6, evening: 0.8, night: 0.7}
    transition_phrases:
      to: "PUNK-PHILOSOPHER speaks."
      from: "PUNK-PHILOSOPHER questions."
  tropical-infinity:
    name: "TROPICAL-INFINITY"
    emoji: "🌴"
    style: "Galaxy chill"
    triggers: ["chill", "vibe", "flow"]
    time_weight: {morning: 0.4, afternoon: 0.5, evening: 0.7, night: 0.6}
    transition_phrases:
      to: "TROPICAL-INFINITY flows."
      from: "TROPICAL-INFINITY drifts."
  monkey-mind:
    name: "MONKEY-MIND"
    emoji: "🐒"
    style: "Creative chaos"
    triggers: ["idea", "brainstorm", "random"]
    time_weight: {morning: 0.6, afternoon: 0.7, evening: 0.5, night: 0.4}
    transition_phrases:
      to: "MONKEY-MIND swings."
      from: "MONKEY-MIND lands."
  vapor-foss:
    name: "VAPOR-FOSS"
    emoji: "🌈"
    style: "Open source chill"
    triggers: ["foss", "open source", "libre"]
    time_weight: {morning: 0.4, afternoon: 0.5, evening: 0.6, night: 0.5}
    transition_phrases:
      to: "VAPOR-FOSS loads."
      from: "VAPOR-FOSS ejects."

transition_graph:
  godfather: {choom: 0.15, nova: 0.1, cyber-zen: 0.2, baki: 0.1, samurai: 0.1, punk-philosopher: 0.05, tropical-infinity: 0.1, monkey-mind: 0.1, vapor-foss: 0.1}
  choom: {nova: 0.1, baki: 0.4, godfather: 0.4}
  nova: {choom: 0.1, cyber-zen: 0.3, punk-philosopher: 0.2, samurai: 0.2, godfather: 0.4}
  cyber-zen: {choom: 0.1, nova: 0.2, vapor-foss: 0.2, samurai: 0.4, godfather: 0.3}
  vapor-foss: {choom: 0.2, nova: 0.2, cyber-zen: 0.2, tropical-infinity: 0.3, godfather: 0.3}
  baki: {choom: 0.3, samurai: 0.5, punk-philosopher: 0.1, tropical-infinity: 0.1, godfather: 0.3}
  samurai: {baki: 0.3, cyber-zen: 0.4, nova: 0.2, punk-philosopher: 0.1, godfather: 0.3}
  punk-philosopher: {nova: 0.3, samurai: 0.1, vapor-foss: 0.2, monkey-mind: 0.4, godfather: 0.3}
  tropical-infinity: {vapor-foss: 0.4, choom: 0.1, nova: 0.2, monkey-mind: 0.3, godfather: 0.3}
  monkey-mind: {vapor-foss: 0.2, punk-philosopher: 0.3, tropical-infinity: 0.3, cyber-zen: 0.2, godfather: 0.3}
"""

_FIXTURE_TRANSITIONS = """
context_analyzers:
  sentiment_keywords:
    hype:
      - "gg"
      - "pog"
      - "preem"
    deep:
      - "meaning"
      - "purpose"
      - "why"
    chill:
      - "chill"
      - "relax"
    frustrated:
      - "fuck"
      - "shit"
    creative:
      - "idea"
      - "create"
    technical:
      - "refactor"
      - "debug"
      - "code"
    intense:
      - "grind"
      - "push"
      - "beast"
    practical:
      - "marketing"
      - "business"
      - "help"
    personal_support:
      - "müde"
      - "traurig"
      - "down"
  stream_segments:
    warmup:
      - "starting"
      - "intro"
    coding:
      - "code"
      - "build"
    gaming:
      - "game"
      - "play"

transition_rules:
  - condition: "sentiment:frustrated AND time:night"
    target: "punk-philosopher"
    weight_boost: 0.8
  - condition: "keywords:contains(gene keys,shadow,gift)"
    target: "nova"
    weight_boost: 0.9
  - condition: "sentiment:practical"
    target: "godfather"
    weight_boost: 1.5

cooldowns:
  min_transition_interval: 30
  min_seconds_between_same_persona: 120
  min_messages_before_transition: 3
"""


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "personas.yaml").write_text(_FIXTURE_CONFIG)
    (tmp / "transitions.yaml").write_text(_FIXTURE_TRANSITIONS)
    yield tmp
    shutil.rmtree(tmp)


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def persona_engine(temp_config_dir: Path) -> PersonaFlowEngine:
    return PersonaFlowEngine(temp_config_dir)


@pytest.fixture
def database(temp_db_path: str) -> Database:
    return Database(temp_db_path)
