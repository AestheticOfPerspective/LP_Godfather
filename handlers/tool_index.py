"""Tool Registry mit RAG-basierter Tool-Auswahl.

Statt alle Skills + Intents in jeden Prompt zu stampfen, embedden wir
die Tool-Beschreibungen und retrieven nur die top-K relevanten per Query.

Embedding via Ollama /api/embeddings, Fallback auf Keyword-Matching.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tools die IMMER in den Prompt kommen (Basis-Kompetenz) ──────────
ALWAYS_AVAILABLE = frozenset({
    "persona_switch", "help", "contribution",
})

# ── Tool Registry ───────────────────────────────────────────────────
BUILTIN_TOOLS: dict[str, dict] = {
    # ── Memory / User Facts ──
    "memory_add": {
        "category": "memory",
        "description": "Speichere eine Information ueber den User (Fakt, Vorliebe, Kontext)",
        "when_to_use": "Wenn der User sagt 'merk dir ...', 'merke ...', 'speicher ...', 'notier ...', oder eine persoenliche Information teilt die gemerkt werden soll.",
        "keywords": ["merk dir", "merke", "speicher", "notier", "fuer spaeter", "fakt", "vorliebe"],
    },
    "memory_recall": {
        "category": "memory",
        "description": "Rufe gespeicherte Fakten ueber den User ab",
        "when_to_use": "Wenn der User fragt 'was weisst du ueber mich', 'erinnere mich', 'was hab ich dir gesagt'.",
        "keywords": ["erinner", "weisst du", "was weisst", "was hab ich", "fakten", "meine daten"],
    },
    "memory_forget": {
        "category": "memory",
        "description": "Loesche einen gespeicherten Fakt ueber den User",
        "when_to_use": "Wenn der User sagt 'vergiss ...', 'loesch ...', 'entfern ... fakt'.",
        "keywords": ["vergiss", "loesch", "entfern", "delete fact"],
    },
    # ── Knowledge Base / Training ──
    "knowledge_add": {
        "category": "knowledge",
        "description": "Trainiere den Bot mit neuem Wissen (Topic | Content)",
        "when_to_use": "Wenn der User sagt 'lern: ...', 'trainier mich: ...', 'hier ist ein Fakt: ...'.",
        "keywords": ["lern:", "lerne:", "trainier", "trainiere", "wissen", "beibringen"],
    },
    "knowledge_query": {
        "category": "knowledge",
        "description": "Suche in der Wissensdatenbank nach Informationen",
        "when_to_use": "Wenn der User nach spezifischem Wissen fragt, das in der Wissensdatenbank sein koennte.",
        "keywords": ["was ist", "erklaer", "definier", "wissen zu", "info ueber"],
    },
    # ── Persona ──
    "persona_switch": {
        "category": "persona",
        "description": "Wechsle die aktive Persona (GodFather, Nyx, Cyber-Zen, etc.)",
        "when_to_use": "Wenn der User die Persona wechseln will, oder eine andere Sprechweise fordert.",
        "keywords": ["persona", "wechsel", "switch", "werde zu", "sprich wie", "character", "stimme"],
    },
    "orchestrate": {
        "category": "persona",
        "description": "Befrage mehrere Personas gleichzeitig zu einer Frage",
        "when_to_use": "Wenn der User will dass mehrere Perspektiven auf eine Frage antworten.",
        "keywords": ["alle personen", "alle perspektiven", "mehrere meinungen", "orchestrier"],
    },
    # ── Clip / Highlight ──
    "clip_submit": {
        "category": "clip",
        "description": "Markiere eine Stelle im Stream/Text als Clip-wuerdig",
        "when_to_use": "Wenn der User sagt 'clip das', 'clip wuerdig', 'das war ein clip'.",
        "keywords": ["clip das", "clippen", "clip wuerdig", "das war ein clip", "clip würdig"],
    },
    # ── Stream ──
    "stream_schedule": {
        "category": "stream",
        "description": "Zeige den Live-Stream Zeitplan",
        "when_to_use": "Wenn der User fragt 'wann stream', 'wann bist du live', 'stream plan'.",
        "keywords": ["wann stream", "wann live", "stream plan", "stream heute", "live geplant"],
    },
    "stream_recap": {
        "category": "stream",
        "description": "Fasse einen Stream oder ein Event zusammen",
        "when_to_use": "Wenn der User sagt 'recap: ...', 'zusammenfassung von ...', 'stream recap'.",
        "keywords": ["recap:", "zusammenfassung", "stream recap", "zusammenfassen"],
    },
    "stream_follow": {
        "category": "stream",
        "description": "Informationen zum Folgen des Streams",
        "when_to_use": "Wenn der User fragt 'wie kann ich folgen', 'wo seid ihr live', 'folgen'.",
        "keywords": ["folgen", "wo live", "wie folgen", "folge", "abonnier"],
    },
    # ── Feedback / Emotion ──
    "feedback_win": {
        "category": "feedback",
        "description": "User hat einen Win/Erfolg erzielt und teilt ihn",
        "when_to_use": "Wenn der User sagt 'geschafft', 'done', 'fertig', 'win', 'erledigt'.",
        "keywords": ["geschafft", "done", "fertig", "win", "erledigt", "abgeliefert"],
    },
    "feedback_stress": {
        "category": "feedback",
        "description": "User ist gestresst, ueberfordert oder braucht Motivation",
        "when_to_use": "Wenn der User sagt 'bin kaputt', 'stress', 'ich kann nicht mehr', 'push mich', 'motivier mich'.",
        "keywords": ["bin kaputt", "stress", "ich kann nicht", "push mich", "motivier", "brauch energie"],
    },
    # ── Chat / Group Context ──
    "chat_context_set": {
        "category": "chat_context",
        "description": "Setze den Kontext/Zweck einer Gruppe (Purpose + Needs)",
        "when_to_use": "Wenn der User sagt 'lern diese Gruppe', 'gruppen Kontext', 'read the room'.",
        "keywords": ["lern diese gruppe", "gruppen kontext", "read the room", "gruppen zweck"],
    },
    "chat_context_show": {
        "category": "chat_context",
        "description": "Zeige den gespeicherten Gruppen-Kontext",
        "when_to_use": "Wenn der User fragt 'was ist der Gruppen Kontext', 'zeig Gruppen Infos'.",
        "keywords": ["gruppen kontext zeigen", "was ist diese gruppe", "group context", "chat kontext"],
    },
    # ── Skills ──
    "skill_create": {
        "category": "skill",
        "description": "Erstelle einen neuen Skill per KI-Draft",
        "when_to_use": "Wenn der User sagt 'bau mir einen Skill fuer ...', 'erstell einen Skill', 'neuer Skill'.",
        "keywords": ["bau mir einen skill", "skill fuer", "neuer skill", "skill erstellen"],
    },
    "skill_manage": {
        "category": "skill",
        "description": "Liste, aktiviere, deaktiviere oder zeige Skills an",
        "when_to_use": "Wenn der User sagt 'skills', 'zeig skills', 'skill aktivieren', 'skill loeschen'.",
        "keywords": ["skills", "skill aktivieren", "skill deaktivieren", "skill loeschen", "skill anzeigen"],
    },
    # ── Antigravity CLI Agent ──
    "antigravity": {
        "category": "agent",
        "description": "Fuehre eine komplexe Aufgabe mit dem Google Antigravity CLI Agenten aus (Multi-Step Reasoning, Code, Web-Suche)",
        "when_to_use": "Wenn der User eine komplexe Aufgabe hat die Multi-Step Reasoning, Code-Ausfuehrung, Datei-Operationen oder Web-Recherche braucht.",
        "keywords": ["antigravity", "agent", "komplex", "multi-step", "recherchier", "code ausfuehren", "web suche", "agy"],
    },
    # ── Help ──
    "help": {
        "category": "help",
        "description": "Zeige die Hilfe / Command-Uebersicht",
        "when_to_use": "Wenn der User sagt 'hilfe', 'help', 'was kannst du', 'commands', 'befehle'.",
        "keywords": ["hilfe", "help", "was kannst du", "commands", "befehle", "/help"],
    },
    "contribution": {
        "category": "help",
        "description": "Zeige was der Bot kann (Capabilities / Contribution-List)",
        "when_to_use": "Wenn der User fragt 'was machst du hier', 'was sind deine Faehigkeiten', 'contribution'.",
        "keywords": ["was machst du", "faehigkeiten", "capabilities", "contribution", "was kannst"],
    },
}

# Build keyword index for fast lookup
_KEYWORD_INDEX: dict[str, str] = {}
for _name, _tool in BUILTIN_TOOLS.items():
    for _kw in _tool.get("keywords", []):
        _KEYWORD_INDEX[_kw] = _name


class ToolIndex:
    """Tool Registry mit Embedding-basierter + Keyword-basierter Retrieval.

    Embedding via Ollama /api/embeddings. Fallback auf Keyword-Matching
    wenn Embedding-Modell nicht verfuegbar oder fehlschlaegt.
    """

    def __init__(self):
        self._ollama_host: str = ""
        self._embed_model: str = ""
        self._healthy: bool = True
        self._embedding_cache: dict[str, list[float]] = {}
        self._builtin_embeddings: dict[str, list[float]] = {}
        self._skills_dir: Path = Path(__file__).resolve().parent.parent / "skills"
        self._embedding_available: Optional[bool] = None
        self._last_skill_fingerprint: str = ""

    def configure(self, ollama_host: str, embed_model: str = "nomic-embed-text") -> None:
        self._ollama_host = ollama_host
        self._embed_model = embed_model

    async def _check_embedding_model(self) -> bool:
        if self._embedding_available is not None:
            return self._embedding_available
        if not self._ollama_host:
            self._embedding_available = False
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._ollama_host}/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
                available = any(self._embed_model in m.get("name", "") for m in models)
                self._embedding_available = available
                if available:
                    logger.info("[tool-index] Embedding model %s available", self._embed_model)
                else:
                    logger.info("[tool-index] Embedding model %s NOT found, using keyword fallback", self._embed_model)
                return available
        except Exception as e:
            logger.warning("[tool-index] Embedding check failed: %s", e)
            self._embedding_available = False
            return False

    async def _embed(self, text: str) -> Optional[list[float]]:
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        if not self._ollama_host:
            return None
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._ollama_host}/api/embeddings",
                    json={"model": self._embed_model, "prompt": text},
                )
                resp.raise_for_status()
                vec = resp.json().get("embedding")
                if vec:
                    self._embedding_cache[text] = vec
                return vec
        except Exception as e:
            logger.debug("[tool-index] Embedding failed: %s", e)
            return None

    def _cosine_sim(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if not na or not nb:
            return 0.0
        return dot / (na * nb)

    async def index_builtin_tools(self) -> None:
        if not await self._check_embedding_model():
            return
        texts = []
        names = []
        for name, tool in BUILTIN_TOOLS.items():
            text = f"{name}: {tool['description']}. when_to_use: {tool['when_to_use']}. keywords: {', '.join(tool['keywords'])}"
            texts.append(text)
            names.append(name)
        import asyncio
        results = await asyncio.gather(*[self._embed(t) for t in texts], return_exceptions=True)
        for name, vec in zip(names, results):
            if isinstance(vec, list) and vec:
                self._builtin_embeddings[name] = vec
        logger.info("[tool-index] Indexed %d/%d built-in tools", len(self._builtin_embeddings), len(texts))

    def _get_skill_fingerprint(self) -> str:
        from utils.skill_store import list_active_skills
        skills = list_active_skills()
        return "|".join(sorted(s["name"] for s in skills))

    def _get_keyword_score(self, text: str, tool: dict) -> int:
        text_lower = text.lower()
        return sum(1 for kw in tool.get("keywords", []) if kw in text_lower)

    def _keyword_retrieve(self, text: str, top_k: int = 5, exclude: set = None) -> list[tuple[str, float]]:
        scored: list[tuple[str, int]] = []
        for name, tool in BUILTIN_TOOLS.items():
            if exclude and name in exclude:
                continue
            score = self._get_keyword_score(text, tool)
            if score > 0:
                scored.append((name, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        max_score = scored[0][1] if scored else 1
        return [(name, s / max_score) for name, s in scored[:top_k]]

    async def _embedding_retrieve(self, text: str, top_k: int = 5, exclude: set = None) -> list[tuple[str, float]]:
        if not self._builtin_embeddings:
            return []
        query_vec = await self._embed(text)
        if not query_vec:
            return []
        scored: list[tuple[str, float]] = []
        for name, vec in self._builtin_embeddings.items():
            if exclude and name in exclude:
                continue
            sim = self._cosine_sim(query_vec, vec)
            if sim > 0.3:
                scored.append((name, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def retrieve_tools(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        exclude = set(ALWAYS_AVAILABLE)
        embedding_results = await self._embedding_retrieve(text, top_k=top_k, exclude=exclude)
        if embedding_results:
            names = {n for n, _ in embedding_results}
            remaining = top_k - len(names)
            if remaining > 0:
                kw = self._keyword_retrieve(text, top_k=remaining, exclude=exclude | names)
                embedding_results.extend(kw)
            return embedding_results[:top_k]
        return self._keyword_retrieve(text, top_k=top_k, exclude=exclude)

    def get_relevant_skills(self, text: str, max_items: int = 2) -> list[tuple[str, str, float]]:
        from utils.skill_store import list_active_skills, read_skill
        text_lower = text.lower()
        scored: list[tuple[int, str, str]] = []
        for skill in list_active_skills():
            name = skill["name"]
            content = read_skill(name)
            if not content:
                continue
            signals = self._extract_skill_signals(content)
            if not signals:
                continue
            score = sum(1 for signal in signals if signal in text_lower)
            if score > 0:
                scored.append((score, name, content))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(name, content[:500], s / max(scored[0][0], 1)) for s, name, content in scored[:max_items]]

    def _extract_skill_signals(self, content: str) -> list[str]:
        match = re.search(r"^## Signals\s*\n(.+?)(?:\n##|\Z)", content, re.MULTILINE | re.DOTALL)
        if not match:
            return []
        raw = match.group(1)
        return [kw.strip().lower() for kw in re.split(r"[,;]\s*", raw) if kw.strip()]


# Singleton
_tool_index: Optional[ToolIndex] = None


def get_tool_index() -> ToolIndex:
    global _tool_index
    if _tool_index is None:
        _tool_index = ToolIndex()
    return _tool_index


async def init_tool_index(ollama_host: str = "http://localhost:11434") -> ToolIndex:
    idx = get_tool_index()
    idx.configure(ollama_host=ollama_host)
    await idx.index_builtin_tools()
    return idx


def format_tool_injection(relevant_tools: list[tuple[str, float]], relevant_skills: list[tuple[str, str, float]]) -> str:
    block = ""
    if relevant_tools:
        lines = ["\nVERFUEGBARE WERKZEUGE (nur wenn anwendbar):"]
        for name, score in relevant_tools:
            tool = BUILTIN_TOOLS.get(name)
            if not tool:
                continue
            pct = int(score * 100)
            lines.append(f"- {name} ({pct}% passend): {tool['description']}")
        block += "\n".join(lines)
    if relevant_skills:
        lines = ["\nRELEVANTE SKILLS:"]
        for name, content, score in relevant_skills:
            pct = int(score * 100)
            lines.append(f"\n--- {name} ({pct}% passend) ---\n{content}")
        block += "\n".join(lines)
    return block
