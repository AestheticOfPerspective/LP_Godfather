from __future__ import annotations
import os
import sys
import shlex
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("copilot.tasks")

ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "echo", "pwd", "whoami", "date", "uptime",
    "ps", "free", "df", "du", "uname", "hostname", "id", "which",
    "git", "pip", "python3", "python",
    "mkdir", "touch", "cp", "mv", "rm", "chmod", "chown",
    "tar", "gzip", "gunzip", "zip", "unzip",
    "grep", "find", "sort", "uniq", "cut", "tr", "tee",
    "curl", "wget", "ping", "nslookup",
    "docker", "docker-compose",
    "systemctl", "journalctl",
    "nproc", "lscpu", "lsblk", "lspci", "lsusb",
}

DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -rf ~", "mkfs", "dd if=", "> /dev/", ":(){ :|:& };:",
    "chmod 777 /", "sudo", "su ", "passwd", "shutdown", "reboot", "halt",
    "wget -O /", "curl -o /", "mv /* ", "cp /* ",
]


def is_safe(command: str) -> tuple[bool, str]:
    cmd_name = shlex.split(command)[0] if shlex.split(command) else ""
    if cmd_name not in ALLOWED_COMMANDS:
        return False, f"Command not allowed: {cmd_name}"

    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return False, f"Blocked dangerous pattern: {pattern}"

    return True, ""


def run(command: str, timeout: int = 30, workdir: Optional[str] = None) -> str:
    safe, msg = is_safe(command)
    if not safe:
        return f"⛔ {msg}"

    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or os.getcwd(),
        )
        out = r.stdout.strip()
        err = r.stderr.strip()
        result = ""
        if out:
            result += out
        if err:
            if result:
                result += "\n"
            result += f"Stderr: {err}"
        if not result:
            result = f"Exit code: {r.returncode}"
        return result[:10000]
    except subprocess.TimeoutExpired:
        return f"⏳ Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def list_allowed() -> str:
    return ", ".join(sorted(ALLOWED_COMMANDS))
