from __future__ import annotations
import os

import pytest
import httpx

from src.ai.ollama_client import OllamaClient, OllamaResponse


@pytest.fixture(autouse=True)
def _clean_ollama_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OLLAMA_PRIMARY_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_SECONDARY_URL", "")
    monkeypatch.setenv("OLLAMA_FALLBACK_URL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "llama3.1:8b")


class TestOllamaClient:
    def test_init_default_servers(self):
        client = OllamaClient()
        assert len(client._servers) == 1
        primary = client._servers[0]
        assert primary.priority == 0
        assert primary.is_primary is True
        assert "11434" in primary.url

    def test_init_with_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_PRIMARY_URL", "http://10.0.0.1:11434")
        monkeypatch.setenv("OLLAMA_SECONDARY_URL", "http://10.0.0.2:11434")
        monkeypatch.setenv("OLLAMA_FALLBACK_URL", "http://127.0.0.1:11434")
        client = OllamaClient()
        urls = [s.url for s in client._servers]
        assert "http://10.0.0.1:11434" in urls
        assert "http://10.0.0.2:11434" in urls
        assert len(client._servers) == 3

    def test_servers_ordered_by_priority(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_PRIMARY_URL", "http://primary:11434")
        monkeypatch.setenv("OLLAMA_SECONDARY_URL", "http://secondary:11434")
        monkeypatch.setenv("OLLAMA_FALLBACK_URL", "http://fallback:11434")
        client = OllamaClient()
        assert client._servers[0].priority == 0
        assert client._servers[1].priority == 1
        assert client._servers[2].priority == 2

    def test_servers_dedup_urls(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_PRIMARY_URL", "http://same:11434")
        monkeypatch.setenv("OLLAMA_FALLBACK_URL", "http://same:11434")
        client = OllamaClient()
        urls = [s.url for s in client._servers]
        assert len(urls) == len(set(urls))

    @pytest.mark.asyncio
    async def test_get_active_server_offline(self):
        client = OllamaClient()
        url, model, name = await client.get_active_server()
        assert url == ""
        assert name == "OFFLINE"

    @pytest.mark.asyncio
    async def test_chat_returns_error_on_offline(self):
        client = OllamaClient()
        resp = await client.chat("user1", "hello", "system", None)
        assert resp.success is False
        assert "offline" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_check_server_returns_false_on_bad_url(self):
        client = OllamaClient()
        result = await client.check_server("http://127.0.0.1:19999", timeout=0.5)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_models_offline(self):
        client = OllamaClient()
        models = await client.list_models("http://127.0.0.1:19999")
        assert models == []

    @pytest.mark.asyncio
    async def test_pull_model_offline(self):
        client = OllamaClient()
        result = await client.pull_model("llama3", "http://127.0.0.1:19999")
        assert "Failed" in result

    @pytest.mark.asyncio
    async def test_check_all_servers_offline(self):
        client = OllamaClient()
        results = await client.check_all_servers()
        assert len(results) == 1
        assert results[0]["online"] is False
        assert results[0]["name"] == "Beast Tower (GPU)"

    @pytest.mark.asyncio
    async def test_chat_builds_payload(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/chat",
            json={
                "message": {"content": "Hello there!"},
                "eval_count": 10,
            },
        )
        client = OllamaClient()
        resp = await client.chat("user1", "hi", "you are a bot", None)
        assert resp.success is True
        assert resp.content == "Hello there!"
        assert resp.tokens == 10
        assert resp.model == "gemma4"

    @pytest.mark.asyncio
    async def test_chat_with_history(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/chat",
            json={
                "message": {"content": "Based on history..."},
                "eval_count": 5,
            },
        )
        client = OllamaClient()
        history = [{"role": "user", "content": "previous msg"}]
        resp = await client.chat("user1", "continue", "be helpful", history)
        assert resp.success is True

    @pytest.mark.asyncio
    async def test_chat_with_images_sets_llava_model(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/chat",
            json={
                "message": {"content": "I see an image"},
                "eval_count": 5,
            },
        )
        client = OllamaClient()
        resp = await client.chat("user1", "what is this?", "system", None, images=["base64data"])
        assert resp.model == "llava"

    @pytest.mark.asyncio
    async def test_chat_timeout(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        httpx_mock.add_exception(
            httpx.TimeoutException("Timed out"),
            url="http://127.0.0.1:11434/api/chat",
        )
        client = OllamaClient()
        resp = await client.chat("user1", "hi", "system", None)
        assert resp.success is False
        assert "timed out" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_chat_with_explicit_model(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        request_snap = {}

        def capture_and_respond(request: httpx.Request) -> httpx.Response:
            import json
            request_snap["body"] = json.loads(request.read())
            return httpx.Response(
                200,
                json={"message": {"content": "custom response"}, "eval_count": 3},
            )

        httpx_mock.add_callback(
            capture_and_respond,
            url="http://127.0.0.1:11434/api/chat",
        )
        client = OllamaClient()
        await client.chat("user1", "hi", "system", None, model="llama3.1:8b")
        assert request_snap["body"]["model"] == "llama3.1:8b"

    @pytest.mark.asyncio
    async def test_get_active_server_caches(self, httpx_mock):
        httpx_mock.add_response(
            url="http://127.0.0.1:11434/api/tags",
            json={"models": [{"name": "gemma4"}]},
        )
        client = OllamaClient()
        assert client._cache_expires == 0
        r1 = await client.get_active_server()
        assert r1[0] == "http://127.0.0.1:11434"
        assert client._cache_expires > 0
        r2 = await client.get_active_server()
        assert r1 == r2

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_connect_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_PRIMARY_URL", "http://127.0.0.1:19999")
        client = OllamaClient()
        url, model, name = await client.get_active_server()
        assert url == ""

        client._active_server = ("http://127.0.0.1:19999", "llama3.1:8b", "Test")
        client._cache_expires = 9999999999

        resp = await client.chat("user1", "hi", "system", None)
        assert resp.success is False
        assert client._cache_expires == 0
