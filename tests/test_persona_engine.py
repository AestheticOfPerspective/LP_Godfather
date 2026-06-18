from __future__ import annotations
import time
from pathlib import Path

import pytest

from src.core.persona_engine import PersonaFlowEngine, PersonaName, PersonaState


class TestPersonaEngine:
    def test_engine_loads_all_personas(self, temp_config_dir: Path):
        engine = PersonaFlowEngine(temp_config_dir)
        assert len(engine.personas) == 10
        assert PersonaName.GODFATHER in engine.personas
        assert PersonaName.CHOOM in engine.personas

    def test_default_state_is_godfather(self, persona_engine: PersonaFlowEngine):
        state = persona_engine.get_state("telegram", "chat_1", "user_1")
        assert state.current == PersonaName.GODFATHER

    def test_get_state_returns_same_instance(self, persona_engine: PersonaFlowEngine):
        s1 = persona_engine.get_state("telegram", "chat_1", "user_1")
        s2 = persona_engine.get_state("telegram", "chat_1", "user_1")
        assert s1 is s2

    def test_different_users_get_different_states(self, persona_engine: PersonaFlowEngine):
        s1 = persona_engine.get_state("telegram", "chat_1", "user_1")
        s2 = persona_engine.get_state("telegram", "chat_1", "user_2")
        assert s1 is not s2

    def test_different_chats_get_different_states(self, persona_engine: PersonaFlowEngine):
        s1 = persona_engine.get_state("telegram", "chat_1", "user_1")
        s2 = persona_engine.get_state("telegram", "chat_2", "user_1")
        assert s1 is not s2

    @pytest.mark.asyncio
    async def test_force_persona_switches(self, persona_engine: PersonaFlowEngine):
        msg, switched = await persona_engine.force_persona("telegram", "chat_1", "user_1", PersonaName.CHOOM)
        assert switched is True
        state = persona_engine.get_state("telegram", "chat_1", "user_1")
        assert state.current == PersonaName.CHOOM

    @pytest.mark.asyncio
    async def test_force_same_persona_returns_false(self, persona_engine: PersonaFlowEngine):
        _, switched = await persona_engine.force_persona("telegram", "chat_1", "user_1", PersonaName.CHOOM)
        assert switched is True
        msg, switched = await persona_engine.force_persona("telegram", "chat_1", "user_1", PersonaName.CHOOM)
        assert switched is False
        assert "Already" in msg

    @pytest.mark.asyncio
    async def test_force_persona_locks(self, persona_engine: PersonaFlowEngine):
        await persona_engine.force_persona("telegram", "chat_1", "user_1", PersonaName.CHOOM, lock=True)
        state = persona_engine.get_state("telegram", "chat_1", "user_1")
        assert state.locked is True
        assert state.locked_by == "user_1"

    @pytest.mark.asyncio
    async def test_set_vibe_maps_correctly(self, persona_engine: PersonaFlowEngine):
        target, msg = await persona_engine.set_vibe("telegram", "chat_1", "user_1", "hype")
        assert target == PersonaName.CHOOM
        assert "CHOOM" in msg

    @pytest.mark.asyncio
    async def test_set_vibe_invalid(self, persona_engine: PersonaFlowEngine):
        target, msg = await persona_engine.set_vibe("telegram", "chat_1", "user_1", "nonexistent")
        assert target is None

    @pytest.mark.asyncio
    async def test_set_vibe_all_modes(self, persona_engine: PersonaFlowEngine):
        vibes = {
            "hype": PersonaName.CHOOM,
            "deep": PersonaName.NOVA,
            "chill": PersonaName.TROPICAL_INFINITY,
            "intense": PersonaName.BAKI,
            "focus": PersonaName.CYBER_ZEN,
            "creative": PersonaName.MONKEY_MIND,
            "rebel": PersonaName.PUNK_PHILOSOPHER,
            "warrior": PersonaName.SAMURAI,
            "free": PersonaName.VAPOR_FOSS,
        }
        for vibe, expected in vibes.items():
            target, _ = await persona_engine.set_vibe("telegram", f"chat_{vibe}", "user_1", vibe)
            assert target == expected, f"vibe '{vibe}' should map to {expected}"

    def test_analyze_context_finds_keywords(self, persona_engine: PersonaFlowEngine):
        ctx = persona_engine.analyze_context(
            "I need help with my setup, choom",
            "telegram", "chat_1", "user_1",
        )
        assert "help" in ctx.keywords
        assert "choom" in ctx.keywords

    def test_analyze_context_sentiment(self, persona_engine: PersonaFlowEngine):
        ctx = persona_engine.analyze_context(
            "gg that was preem gameplay",
            "telegram", "chat_1", "user_1",
        )
        assert ctx.sentiment["hype"] > 0
        assert ctx.sentiment["deep"] == 0

    @pytest.mark.asyncio
    async def test_select_next_respects_cooldown(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        state = engine.get_state("telegram", "chat_1", "user_1")
        state.last_transition = time.time()
        state.messages_since_transition = 10

        next_p, switched = await engine.select_next("telegram", "chat_1", "user_1", "gg preem")
        assert switched is False

    @pytest.mark.asyncio
    async def test_select_next_respects_min_messages(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        engine.get_state("telegram", "chat_1", "user_1")
        state = engine.get_state("telegram", "chat_1", "user_1")
        state.last_transition = 0
        state.messages_since_transition = 1

        next_p, switched = await engine.select_next("telegram", "chat_1", "user_1", "gg preem")
        assert switched is False

    @pytest.mark.asyncio
    async def test_select_next_returns_current_on_low_confidence(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        state = engine.get_state("telegram", "chat_1", "user_1")
        state.last_transition = 0
        state.messages_since_transition = 10

        next_p, switched = await engine.select_next("telegram", "chat_1", "user_1", "zzz totally neutral nothing")
        assert next_p == PersonaName.GODFATHER

    def test_affinity_increases_on_transition(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        state = engine.get_state("telegram", "chat_1", "user_1")
        state.last_transition = 0
        state.messages_since_transition = 10

        engine._apply_transition(state, PersonaName.CHOOM)
        assert state.affinity[PersonaName.CHOOM] == 0.05

    def test_get_persona_info(self, persona_engine: PersonaFlowEngine):
        info = persona_engine.get_persona_info(PersonaName.GODFATHER)
        assert info.display_name == "GODFATHER"
        assert info.emoji == "💀"

    def test_list_personas(self, persona_engine: PersonaFlowEngine):
        lst = persona_engine.list_personas()
        assert len(lst) == 10
        names = [name for name, _, _ in lst]
        assert PersonaName.GODFATHER in names
        assert PersonaName.CHOOM in names

    def test_get_all_persona_data(self, persona_engine: PersonaFlowEngine):
        data = persona_engine.get_all_persona_data()
        assert len(data) == 10
        assert data["godfather"]["emoji"] == "💀"
        assert data["choom"]["display"] == "CHOOM"

    def test_transition_tracks_previous(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        state = engine.get_state("telegram", "chat_1", "user_1")
        engine._apply_transition(state, PersonaName.CHOOM)
        assert state.previous == PersonaName.GODFATHER
        assert state.current == PersonaName.CHOOM

    @pytest.mark.asyncio
    async def test_same_persona_cooldown(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        state = engine.get_state("telegram", "chat_1", "user_1")
        state.last_transition = 0
        state.messages_since_transition = 10

        await engine.force_persona("telegram", "chat_1", "user_1", PersonaName.CHOOM)
        state.last_transition = time.time()
        state.messages_since_transition = 10

        next_p, switched = await engine.select_next("telegram", "chat_1", "user_1", "gg preem")
        assert switched is False

    @pytest.mark.asyncio
    async def test_locked_state_always_returns_locked(self, persona_engine: PersonaFlowEngine):
        engine = persona_engine
        await engine.force_persona("telegram", "chat_1", "user_1", PersonaName.NOVA, lock=True)
        state = engine.get_state("telegram", "chat_1", "user_1")
        weights = engine.compute_weights(state, engine.analyze_context("gg", "telegram", "chat_1", "user_1"))
        assert weights[PersonaName.NOVA] == 1.0

    def test_get_transition_message(self, persona_engine: PersonaFlowEngine):
        msg = persona_engine.get_transition_message(PersonaName.CHOOM, incoming=True)
        assert "CHOOM" in msg
        msg_out = persona_engine.get_transition_message(PersonaName.CHOOM, incoming=False)
        assert "CHOOM" in msg_out
