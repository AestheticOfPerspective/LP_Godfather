from __future__ import annotations
from pathlib import Path
import tempfile
import shutil

import pytest
import yaml

from src.platforms.telegram.interviewer_agents import (
    resolve_alias,
    hard_mode_sequence,
    get_prompts,
    interviewer_prompt,
    all_interviewer_prompts,
)


_FIXTURE_YAML = """
interviewers:
  the-anchor:
    name: "THE ANCHOR"
    emoji: "🎙️"
    prompt: "You are The Anchor. Be neutral."
  recruiter-x:
    name: "RECRUITER-X"
    emoji: "👔"
    prompt: "You are Recruiter-X. HR expert."
  code-hammer:
    name: "CODE-HAMMER"
    emoji: "⚙️"
    prompt: "You are Code-Hammer. Tech interviewer."
  mind-mirror:
    name: "MIND-MIRROR"
    emoji: "🧠"
    prompt: "You are Mind-Mirror. Psych coach."
  shark:
    name: "SHARK"
    emoji: "🦈"
    prompt: "You are Shark. Pitch investor."
  press-room:
    name: "PRESS-ROOM"
    emoji: "📡"
    prompt: "You are Press-Room. Media trainer."

aliases:
  anchor: the-anchor
  hr: recruiter-x
  recruiter: recruiter-x
  tech: code-hammer
  coding: code-hammer
  psych: mind-mirror
  mirror: mind-mirror
  pitch: shark
  investor: shark
  media: press-room
  press: press-room

hard_mode_sequence:
  - recruiter-x
  - code-hammer
  - mind-mirror
  - shark
  - press-room
"""


@pytest.fixture(autouse=True)
def _patch_config_path(monkeypatch: pytest.MonkeyPatch):
    tmp = Path(tempfile.mkdtemp())
    config_path = tmp / "interviewers.yaml"
    config_path.write_text(_FIXTURE_YAML)
    monkeypatch.setattr(
        "src.platforms.telegram.interviewer_agents._CONFIG_PATH",
        config_path,
    )
    from src.platforms.telegram import interviewer_agents as m
    m._cached_data = None
    yield
    shutil.rmtree(tmp)
    m._cached_data = None


class TestResolveAlias:
    def test_resolves_known_aliases(self):
        cases = {
            "anchor": "the-anchor",
            "hr": "recruiter-x",
            "recruiter": "recruiter-x",
            "tech": "code-hammer",
            "coding": "code-hammer",
            "psych": "mind-mirror",
            "mirror": "mind-mirror",
            "pitch": "shark",
            "investor": "shark",
            "media": "press-room",
            "press": "press-room",
            "the-anchor": "the-anchor",
            "recruiter-x": "recruiter-x",
            "code-hammer": "code-hammer",
        }
        for alias, expected in cases.items():
            assert resolve_alias(alias) == expected, f"alias '{alias}' should resolve to {expected}"

    def test_unknown_alias_returns_none(self):
        assert resolve_alias("nonexistent") is None
        assert resolve_alias("") is None
        assert resolve_alias("random-name") is None

    def test_case_insensitive(self):
        assert resolve_alias("HR") == "recruiter-x"
        assert resolve_alias("Tech") == "code-hammer"
        assert resolve_alias("PSYCH") == "mind-mirror"

    def test_journalist_alias(self):
        assert resolve_alias("journalist") is None


class TestHardModeSequence:
    def test_returns_sequence(self):
        seq = hard_mode_sequence()
        assert len(seq) == 5
        assert seq[0] == "recruiter-x"
        assert seq[-1] == "press-room"

    def test_all_agents_exist(self):
        seq = hard_mode_sequence()
        all_prompts = all_interviewer_prompts()
        for agent in seq:
            assert agent in all_prompts, f"{agent} not in interviewers"


class TestGetPrompts:
    def test_get_prompts_returns_dict(self):
        prompts = get_prompts()
        assert isinstance(prompts, dict)
        assert len(prompts) == 6
        assert "the-anchor" in prompts
        assert "press-room" in prompts

    def test_each_prompt_is_string(self):
        prompts = get_prompts()
        for name, prompt in prompts.items():
            assert isinstance(prompt, str), f"{name} prompt is not a string"
            assert len(prompt) > 0, f"{name} prompt is empty"

    def test_all_interviewer_prompts_matches_get_prompts(self):
        assert get_prompts() == all_interviewer_prompts()


class TestInterviewerPrompt:
    def test_returns_prompt_for_valid_name(self):
        prompt = interviewer_prompt("the-anchor")
        assert prompt == "You are The Anchor. Be neutral."

    def test_returns_none_for_unknown(self):
        assert interviewer_prompt("nonexistent") is None
        assert interviewer_prompt("") is None

    def test_specific_prompts(self):
        prompts = {
            "recruiter-x": "You are Recruiter-X. HR expert.",
            "code-hammer": "You are Code-Hammer. Tech interviewer.",
            "mind-mirror": "You are Mind-Mirror. Psych coach.",
        }
        for name, expected in prompts.items():
            assert interviewer_prompt(name) == expected
