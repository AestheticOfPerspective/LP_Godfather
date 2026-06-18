from __future__ import annotations
import os
import time
import logging
import asyncio
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OllamaServer:
    url: str
    model: str
    name: str
    priority: int
    is_primary: bool


@dataclass
class OllamaResponse:
    content: str
    model: str
    server: str
    tokens: int
    latency_ms: float
    success: bool


class OllamaClient:
    def __init__(self):
        self.primary_url = os.getenv("OLLAMA_PRIMARY_URL", "http://127.0.0.1:11434")
        self.secondary_url = os.getenv("OLLAMA_SECONDARY_URL", "")
        self.fallback_url = os.getenv("OLLAMA_FALLBACK_URL", "http://127.0.0.1:11434")

        self.primary_model = os.getenv("OLLAMA_MODEL", "gemma4")
        self.fallback_model = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.1:8b")

        self.max_history = int(os.getenv("MAX_HISTORY", "20"))
        self.client_timeout = float(os.getenv("OLLAMA_TIMEOUT", "60.0"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "400"))
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))

        self._servers: List[OllamaServer] = []
        self._active_server: Tuple[str, str, str] = ("", "", "")
        self._cache_expires: float = 0
        self.cache_ttl: float = 30.0
        self._server_lock = asyncio.Lock()

        self._init_servers()

    def _init_servers(self):
        servers = []
        if self.primary_url:
            servers.append(OllamaServer(
                url=self.primary_url,
                model=self.primary_model,
                name="Beast Tower (GPU)",
                priority=0,
                is_primary=True,
            ))
        if self.secondary_url:
            servers.append(OllamaServer(
                url=self.secondary_url,
                model=self.fallback_model,
                name="Pink Tiger (CPU)",
                priority=1,
                is_primary=False,
            ))
        if self.fallback_url and self.fallback_url not in (self.primary_url, self.secondary_url):
            servers.append(OllamaServer(
                url=self.fallback_url,
                model=self.fallback_model,
                name="Local (CPU)",
                priority=2,
                is_primary=False,
            ))
        self._servers = servers

    async def check_server(self, url: str, timeout: float = 3.0) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_active_server(self) -> Tuple[str, str, str]:
        async with self._server_lock:
            now = time.time()
            if now < self._cache_expires and self._active_server[0]:
                return self._active_server

            for server in sorted(self._servers, key=lambda s: s.priority):
                if await self.check_server(server.url):
                    self._active_server = (server.url, server.model, server.name)
                    self._cache_expires = now + self.cache_ttl
                    return self._active_server

            self._active_server = ("", "", "OFFLINE")
            self._cache_expires = now + 5
            return self._active_server

    async def list_models(self, url: Optional[str] = None) -> List[Dict]:
        if not url:
            url, _, _ = await self.get_active_server()
        if not url:
            return []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{url}/api/tags")
                resp.raise_for_status()
                return resp.json().get("models", [])
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def pull_model(self, model_name: str, url: Optional[str] = None) -> str:
        if not url:
            url, _, _ = await self.get_active_server()
        if not url:
            return "No Ollama server available."
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(
                    f"{url}/api/pull",
                    json={"name": model_name, "stream": False},
                )
                resp.raise_for_status()
            return f"Model '{model_name}' pulled successfully!"
        except Exception as e:
            return f"Failed to pull '{model_name}': {e}"

    async def chat(self, user_id: str, user_message: str,
                   system_prompt: str, history: Optional[List[Dict]] = None,
                   images: Optional[List[str]] = None,
                   model: Optional[str] = None) -> OllamaResponse:
        url, default_model, server_name = await self.get_active_server()
        if not url:
            return OllamaResponse(
                content="All Ollama servers are offline.",
                model="", server="OFFLINE",
                tokens=0, latency_ms=0, success=False,
            )

        active_model = model or default_model
        if images:
            active_model = "llava"

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-self.max_history:])
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": active_model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
                "top_p": 0.9,
                "top_k": 40,
            },
        }
        if images:
            payload["images"] = images
            del payload["messages"][0]["content"]
            payload["messages"][0]["content"] = system_prompt

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.client_timeout) as client:
                response = await client.post(
                    f"{url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            elapsed = (time.time() - start) * 1000
            content = data["message"]["content"]
            eval_count = data.get("eval_count", 0)

            return OllamaResponse(
                content=content,
                model=active_model,
                server=server_name,
                tokens=eval_count,
                latency_ms=round(elapsed, 1),
                success=True,
            )

        except httpx.TimeoutException:
            logger.error("Ollama timeout on %s", url)
            return OllamaResponse(
                content="Request timed out. Try a shorter message.",
                model=active_model, server=server_name,
                tokens=0, latency_ms=0, success=False,
            )
        except httpx.ConnectError:
            logger.error("Ollama connection error on %s", url)
            self._cache_expires = 0
            return OllamaResponse(
                content="Lost connection to Ollama. Retrying...",
                model=active_model, server=server_name,
                tokens=0, latency_ms=0, success=False,
            )
        except Exception as e:
            logger.error("Ollama error: %s", e)
            return OllamaResponse(
                content=f"Error: {e}",
                model=active_model, server=server_name,
                tokens=0, latency_ms=0, success=False,
            )

    async def check_all_servers(self) -> List[dict]:
        results = []
        for server in self._servers:
            ok = await self.check_server(server.url)
            models = await self.list_models(server.url) if ok else []
            results.append({
                "name": server.name,
                "url": server.url,
                "online": ok,
                "models": len(models),
                "model_list": [m["name"] for m in models[:5]],
            })
        return results
