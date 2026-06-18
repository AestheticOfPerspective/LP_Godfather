from __future__ import annotations
import os
import sys
import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.ai.ollama_client import OllamaClient
from src.core.persona_engine import PersonaFlowEngine, PersonaName
from src.storage.database import Database
from src.copilot import git_tools, task_exec

logger = logging.getLogger("copilot.mcp")

mcp = FastMCP("LP_GodFather CO Pilot", port=int(os.getenv("MCP_PORT", "8921")))

_ollama: OllamaClient | None = None
_engine: PersonaFlowEngine | None = None
_db: Database | None = None


def init(ollama: OllamaClient, engine: PersonaFlowEngine, db: Database):
    global _ollama, _engine, _db
    _ollama = ollama
    _engine = engine
    _db = db


@mcp.tool()
async def chat(message: str, persona: str = "godfather") -> str:
    if _ollama is None:
        return "Error: CO Pilot not initialized"
    pdata = _engine.get_persona_info(PersonaName(persona)) if _engine else None
    system = (
        f"You are {pdata.display_name} {pdata.emoji}\nStyle: {pdata.style}\n\n"
        f"Answer concisely with personality. Antworte auf Deutsch. Keep it under 2000 chars."
        if pdata else
        "You are the CO Pilot for Beast Tower. Concise, helpful, German."
    )
    try:
        resp = await _ollama.chat(
            user_id="mcp_user",
            user_message=message,
            system_prompt=system,
        )
        return resp.content
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def git_status(path: str = "") -> str:
    cwd = path if path else None
    return git_tools.status(cwd=cwd)


@mcp.tool()
def git_diff(staged: bool = False, path: str = "") -> str:
    cwd = path if path else None
    return git_tools.diff(staged=staged, cwd=cwd)


@mcp.tool()
async def git_review(path: str = "") -> str:
    cwd = path if path else None
    preview = git_tools.commit_preview(cwd=cwd)
    if _ollama:
        return await git_tools.review_diff(preview, _ollama)
    return preview


@mcp.tool()
def git_log(count: int = 10, path: str = "") -> str:
    cwd = path if path else None
    return git_tools.log(count=count, cwd=cwd)


@mcp.tool()
def task_run(command: str, timeout: int = 30, workdir: str = "") -> str:
    wd = workdir if workdir else None
    return task_exec.run(command, timeout=timeout, workdir=wd)


@mcp.tool()
def task_allowed() -> str:
    return task_exec.list_allowed()


@mcp.tool()
def system_info() -> str:
    import subprocess, time as tmod

    uptime_sec = tmod.time() - _start_time
    days, rem = divmod(int(uptime_sec), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60

    def sh(cmd: str) -> str:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "N/A"

    host = sh("hostname")
    kernel = sh("uname -r")
    load = sh("cat /proc/loadavg | awk '{print $1, $2, $3}'")
    ram = sh("free -h | awk '/^Mem:/{print $3 \"/\" $2}'")
    disk = sh("df -h / | awk 'NR==2{print $3 \"/\" $2}'")

    return (
        f"Bot PID: {os.getpid()}\n"
        f"Uptime: {days}d {hours:02d}:{minutes:02d}\n"
        f"Host: {host}\n"
        f"Kernel: {kernel}\n"
        f"CPU Load: {load}\n"
        f"RAM: {ram}\n"
        f"Disk: {disk}\n"
    )


@mcp.tool()
def list_personas() -> str:
    if _engine is None:
        return "Not initialized"
    lines = []
    for pname, pdata in sorted(_engine.personas.items(), key=lambda x: x[0].value):
        lines.append(f"{pdata.emoji} {pdata.display_name} ({pname.value}) — {pdata.style}")
    return "\n".join(lines)


@mcp.tool()
async def ollama_status() -> str:
    if _ollama is None:
        return "Not initialized"
    servers = await _ollama.check_all_servers()
    lines = []
    for s in servers:
        status = "ONLINE" if s.get("ok") else "OFFLINE"
        lines.append(f"{s.get('name', '?')}: {status} ({s.get('url', '?')})")
        models = s.get("models", [])
        if models:
            for m in models:
                lines.append(f"  - {m.get('name', m) if isinstance(m, dict) else m}")
    return "\n".join(lines)


@mcp.tool()
def export_html(text: str, title: str = "CO Pilot Export") -> str:
    ts = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
    safe = __import__("html").escape(text)
    safe = safe.replace("&#x27;", "'").replace("&quot;", '"')
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<title>{__import__('html').escape(title)}</title>
<style>
body {{ background:#0a0a0f; color:#e0e0e0; font-family:'Inter',sans-serif; max-width:800px; margin:auto; padding:2rem; }}
h1 {{ font-family:'Orbitron',monospace; color:#ff6600; text-transform:uppercase; letter-spacing:3px; }}
.content {{ background:#12121a; border:1px solid #222; border-radius:8px; padding:2rem; white-space:pre-wrap; }}
.content b {{ color:#ff6600; }}
.content code {{ background:#1a1a2e; color:#00ff88; padding:0.2em 0.4em; border-radius:4px; }}
footer {{ text-align:center; color:#555; margin-top:2rem; font-size:0.8rem; }}
</style></head><body>
<h1>{__import__('html').escape(title)}</h1>
<div class="content">{safe}</div>
<footer>LP_GodFather CO Pilot · {ts}</footer>
</body></html>"""


def run():
    logger.info("Starting CO Pilot MCP server...")
    mcp.run(transport="stdio")


_start_time: float = 0.0
