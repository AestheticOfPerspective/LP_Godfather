#!/usr/bin/env python3
"""Copy non-token runtime settings and Twitch client secret without printing values."""

from __future__ import annotations

import argparse
import stat
from pathlib import Path


KEYS = {
    "TWITCH_CLIENT_ID",
    "TWITCH_CLIENT_SECRET",
    "TWITCH_CHANNEL",
    "TWITCH_BOT_NICK",
    "TWITCH_OWNER",
    "TWITCH_ADMIN_USERS",
    "STREAM_SCHEDULE",
    "STREAM_TODAY_FALLBACK",
    "TWITCH_CHANNEL_URL",
    "YOUTUBE_URL",
    "CLIP_INTAKE_URL",
}


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in KEYS and value:
            result[key] = value
    return result


def update(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(values)
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    if output and output[-1]:
        output.append("")
    output.extend(f"{key}={value}" for key, value in sorted(remaining.items()))
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(output) + "\n")
    temp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    update(args.target, read_env(args.source))
    print("Legacy non-token settings migrated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

