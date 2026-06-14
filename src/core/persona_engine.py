from __future__ import annotations
import random
import time
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime

import yaml


class PersonaName(str, Enum):
    CHOOM = "choom"
    NOVA = "nova"
    CYBER_ZEN = "cyber-zen"
    VAPOR_FOSS = "vapor-foss"
    BAKI = "baki"
    SAMURAI = "samurai"
    PUNK_PHILOSOPHER = "punk-philosopher"
    TROPICAL_INFINITY = "tropical-infinity"
    MONKEY_MIND = "monkey-mind"


@dataclass
class Persona:
    name: PersonaName
    display_name: str
    emoji: str
    style: str
    triggers: List[str]
    time_weights: Dict[str, float]
    transition_to: str
    transition_from: str


@dataclass
class ContextVector:
    time_of_day: str
    sentiment: Dict[str, float]
    stream_segment: Optional[str]
    keywords: List[str]
    platform: str
    user_id: str
    chat_id: str


@dataclass
class PersonaState:
    current: PersonaName
    previous: Optional[PersonaName] = None
    affinity: Dict[PersonaName, float] = field(default_factory=dict)
    last_transition: float = field(default_factory=time.time)
    transition_count: int = 0
    messages_since_transition: int = 0
    locked: bool = False
    locked_by: Optional[str] = None


class PersonaFlowEngine:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.personas = self._load_personas()
        self.transition_graph = self._load_transition_graph()
        self.transition_rules, self.sentiment_keywords, self.stream_keywords = self._load_transition_rules()
        self.cooldowns = self._load_cooldowns()
        self.states: Dict[str, PersonaState] = {}

        self.time_period_weights = {
            "morning": 1.0, "afternoon": 0.8,
            "evening": 0.6, "night": 0.4
        }

    def _load_personas(self) -> Dict[PersonaName, Persona]:
        path = self.config_dir / "personas.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        personas = {}
        for key, p in data["personas"].items():
            personas[PersonaName(key)] = Persona(
                name=PersonaName(key),
                display_name=p["name"],
                emoji=p["emoji"],
                style=p["style"],
                triggers=[t.lower() for t in p["triggers"]],
                time_weights=p["time_weight"],
                transition_to=p["transition_phrases"]["to"],
                transition_from=p["transition_phrases"]["from"],
            )
        return personas

    def _load_transition_graph(self) -> Dict[PersonaName, Dict[PersonaName, float]]:
        path = self.config_dir / "personas.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        graph = {}
        for from_p, edges in data.get("transition_graph", {}).items():
            graph[PersonaName(from_p)] = {
                PersonaName(k): v for k, v in edges.items()
            }
        return graph

    def _load_transition_rules(self):
        path = self.config_dir / "transitions.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        analyzers = data.get("context_analyzers", {})
        return (
            data.get("transition_rules", []),
            analyzers.get("sentiment_keywords", {}),
            analyzers.get("stream_segments", {}),
        )

    def _load_cooldowns(self):
        path = self.config_dir / "transitions.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("cooldowns", {
            "min_transition_interval": 30,
            "min_seconds_between_same_persona": 120,
            "min_messages_before_transition": 3,
        })

    def _state_key(self, platform: str, chat_id: str, user_id: str) -> str:
        return f"{platform}:{chat_id}:{user_id}"

    def get_state(self, platform: str, chat_id: str, user_id: str) -> PersonaState:
        key = self._state_key(platform, chat_id, user_id)
        if key not in self.states:
            period = self._get_time_period()
            best = max(
                self.personas.values(),
                key=lambda p: p.time_weights.get(period, 0)
            )
            self.states[key] = PersonaState(current=best.name)
        return self.states[key]

    def _get_time_period(self) -> str:
        hour = datetime.now().hour
        if 6 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        return "night"

    def analyze_context(self, message: str, platform: str, chat_id: str,
                        user_id: str, stream_segment: Optional[str] = None) -> ContextVector:
        msg_lower = message.lower()
        time_period = self._get_time_period()

        sentiment = {cat: 0 for cat in self.sentiment_keywords}
        for cat, keywords in self.sentiment_keywords.items():
            for kw in keywords:
                if kw in msg_lower:
                    sentiment[cat] += 1

        total = sum(sentiment.values()) or 1
        sentiment = {k: v / total for k, v in sentiment.items()}

        if stream_segment is None:
            for seg, keywords in self.stream_keywords.items():
                if any(kw in msg_lower for kw in keywords):
                    stream_segment = seg
                    break

        all_triggers = set()
        for p in self.personas.values():
            all_triggers.update(p.triggers)
        found_keywords = [kw for kw in all_triggers if kw in msg_lower]

        return ContextVector(
            time_of_day=time_period,
            sentiment=sentiment,
            stream_segment=stream_segment,
            keywords=found_keywords,
            platform=platform,
            user_id=user_id,
            chat_id=chat_id,
        )

    def compute_weights(self, state: PersonaState, context: ContextVector) -> Dict[PersonaName, float]:
        weights: Dict[PersonaName, float] = {p: 0.0 for p in PersonaName}

        if state.locked and state.locked_by:
            if state.locked_by in ("admin", context.user_id):
                return {state.current: 1.0}

        for target, weight in self.transition_graph.get(state.current, {}).items():
            weights[target] = weight

        current_stickiness = 0.2 + (0.1 if state.messages_since_transition < 5 else 0)
        weights[state.current] = weights.get(state.current, 0) + current_stickiness

        for pname, pdata in self.personas.items():
            tw = pdata.time_weights.get(context.time_of_day, 0)
            weights[pname] = weights.get(pname, 0) + tw * 0.15

        for scat, score in context.sentiment.items():
            if score > 0.2:
                smap = {
                    "hype": [PersonaName.CHOOM, PersonaName.BAKI],
                    "deep": [PersonaName.NOVA, PersonaName.PUNK_PHILOSOPHER],
                    "chill": [PersonaName.VAPOR_FOSS, PersonaName.TROPICAL_INFINITY],
                    "frustrated": [PersonaName.PUNK_PHILOSOPHER, PersonaName.BAKI],
                    "creative": [PersonaName.MONKEY_MIND, PersonaName.TROPICAL_INFINITY],
                    "technical": [PersonaName.CYBER_ZEN, PersonaName.CHOOM],
                    "intense": [PersonaName.BAKI, PersonaName.SAMURAI],
                }
                for p in smap.get(scat, []):
                    weights[p] = weights.get(p, 0) + score * 0.4

        for kw in context.keywords:
            for pname, pdata in self.personas.items():
                if kw in pdata.triggers:
                    weights[pname] = weights.get(pname, 0) + 0.3

        for pname, affinity in state.affinity.items():
            weights[pname] = weights.get(pname, 0) + affinity * 0.2

        for rule in self.transition_rules:
            cond = rule.get("condition", "")
            if self._eval_condition(cond, context):
                target = PersonaName(rule["target"])
                weights[target] = weights.get(target, 0) + rule.get("weight_boost", 0.5)

        min_val = min(weights.values()) or 0
        weights = {k: max(v, 0) for k, v in weights.items()}
        total = sum(weights.values()) or 1
        return {k: v / total for k, v in weights.items()}

    def _eval_condition(self, condition: str, context: ContextVector) -> bool:
        condition = condition.replace(" AND ", " & ").replace(" OR ", " | ")
        tokens = condition.split()
        results = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == "&":
                i += 1
                continue
            elif token == "|":
                i += 1
                continue
            elif ":" in token:
                key, value = token.split(":", 1)
                if key == "sentiment":
                    results.append(context.sentiment.get(value, 0) > 0.2)
                elif key == "time":
                    results.append(context.time_of_day == value)
                elif key == "stream_segment":
                    results.append(context.stream_segment == value)
                elif key == "keywords":
                    parts = value.replace("(", "").replace(")", "")
                    kw_list = [k.strip() for k in parts.split(",")]
                    results.append(any(kw in context.keywords for kw in kw_list))
            i += 1

        if "|" in tokens:
            return any(results)
        return all(results) if results else False

    def select_next(self, platform: str, chat_id: str, user_id: str,
                    message: str, stream_segment: Optional[str] = None) -> Tuple[PersonaName, bool]:
        state = self.get_state(platform, chat_id, user_id)
        state.messages_since_transition += 1

        now = time.time()
        if now - state.last_transition < self.cooldowns.get("min_transition_interval", 30):
            return state.current, False

        if state.messages_since_transition < self.cooldowns.get("min_messages_before_transition", 3):
            return state.current, False

        context = self.analyze_context(message, platform, chat_id, user_id, stream_segment)
        weights = self.compute_weights(state, context)

        candidates = [(p, w) for p, w in weights.items() if w > 0]
        if not candidates:
            return state.current, False

        candidates.sort(key=lambda x: x[1], reverse=True)
        top = candidates[0]

        if top[0] == state.current:
            if state.previous and random.random() < 0.1:
                back_weight = weights.get(state.previous, 0)
                if back_weight > 0.1:
                    self._apply_transition(state, state.previous)
                    return state.previous, True
            return state.current, False

        if top[1] < 0.15:
            return state.current, False

        if random.random() > top[1]:
            return state.current, False

        same_persona_cooldown = self.cooldowns.get("min_seconds_between_same_persona", 120)
        if top[0] == state.previous and (now - state.last_transition) < same_persona_cooldown:
            return state.current, False

        self._apply_transition(state, top[0])
        return state.current, True

    def _apply_transition(self, state: PersonaState, target: PersonaName):
        state.previous = state.current
        state.current = target
        state.last_transition = time.time()
        state.transition_count += 1
        state.messages_since_transition = 0

        if target not in state.affinity:
            state.affinity[target] = 0.0
        state.affinity[target] = min(state.affinity[target] + 0.05, 1.0)

        if state.previous in state.affinity:
            state.affinity[state.previous] = max(state.affinity[state.previous] - 0.02, 0)

    def force_persona(self, platform: str, chat_id: str, user_id: str,
                      target: PersonaName, lock: bool = False) -> Tuple[str, bool]:
        state = self.get_state(platform, chat_id, user_id)
        old = state.current
        if old == target and not lock:
            return f"Already in {target} mode!", False

        self._apply_transition(state, target)
        if lock:
            state.locked = True
            state.locked_by = user_id

        pdata = self.personas[target]
        msg = pdata.transition_to if old != target else f"Staying in {pdata.display_name} mode."
        return msg, True

    def set_vibe(self, platform: str, chat_id: str, user_id: str,
                 vibe: str) -> Tuple[Optional[PersonaName], str]:
        vibe_map = {
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
        target = vibe_map.get(vibe.lower())
        if not target:
            available = ", ".join(vibe_map.keys())
            return None, f"Unknown vibe '{vibe}'. Try: {available}"

        state = self.get_state(platform, chat_id, user_id)
        self._apply_transition(state, target)
        pdata = self.personas[target]
        return target, pdata.transition_to

    def get_transition_message(self, pname: PersonaName, incoming: bool = True) -> str:
        pdata = self.personas[pname]
        return pdata.transition_to if incoming else pdata.transition_from

    def get_persona_info(self, pname: PersonaName) -> Persona:
        return self.personas[pname]

    def list_personas(self) -> List[Tuple[PersonaName, str, str]]:
        return [(p.name, p.display_name, p.emoji) for p in self.personas.values()]

    def get_all_persona_data(self) -> Dict[str, Dict]:
        return {
            p.name.value: {
                "display": p.display_name,
                "emoji": p.emoji,
                "style": p.style,
                "triggers": p.triggers,
                "time_weights": p.time_weights,
            }
            for p in self.personas.values()
        }
