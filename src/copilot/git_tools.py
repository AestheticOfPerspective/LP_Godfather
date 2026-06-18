from __future__ import annotations
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("copilot.git")


def git_run(*args: str, cwd: Optional[str] = None) -> str:
    try:
        r = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=30,
            cwd=cwd or os.getcwd(),
        )
        if r.returncode != 0:
            return f"Error: {r.stderr.strip()}"
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "Error: git command timed out"
    except FileNotFoundError:
        return "Error: git not found"
    except Exception as e:
        return f"Error: {e}"


def status(cwd: Optional[str] = None) -> str:
    return git_run("status", cwd=cwd)


def diff(staged: bool = False, cwd: Optional[str] = None) -> str:
    args = ["diff", "--cached"] if staged else ["diff"]
    return git_run(*args, cwd=cwd)


def log(count: int = 10, cwd: Optional[str] = None) -> str:
    return git_run("log", f"-{count}", "--oneline", cwd=cwd)


def branch(cwd: Optional[str] = None) -> str:
    return git_run("branch", "-a", cwd=cwd)


def commit_preview(cwd: Optional[str] = None) -> str:
    s = status(cwd)
    d = diff(staged=True, cwd=cwd)
    if not d:
        d = diff(cwd=cwd)
    return f"Status:\n{s}\n\nDiff:\n{d[:4000]}"


async def review_diff(diff_text: str, ollama_client=None) -> str:
    if not diff_text or diff_text.startswith("Error"):
        return diff_text or "Nothing to review"
    if ollama_client is None:
        return diff_text
    prompt = (
        "Review this git diff. Identify bugs, security issues, "
        "code quality problems, and suggest improvements in 3-5 sentences:\n\n"
        f"{diff_text[:6000]}"
    )
    try:
        resp = await ollama_client.chat(
            user_id="git_review",
            user_message=prompt,
            system_prompt="You are a senior code reviewer. Be critical, precise, helpful.",
        )
        return resp.content
    except Exception as e:
        return f"Review failed: {e}"
