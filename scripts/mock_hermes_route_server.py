#!/usr/bin/env python3
"""
Tiny local mock endpoint for LP_Godfather Hermes forwarding tests.

Usage:
  python scripts/mock_hermes_route_server.py --host 127.0.0.1 --port 8088
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockHermesHandler(BaseHTTPRequestHandler):
    server_version = "MockHermes/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/route":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return

        namespace = payload.get("namespace", "?")
        subcommand = payload.get("subcommand", "?")
        phase = payload.get("phase", "?")

        print(
            f"[{datetime.now(timezone.utc).isoformat()}] "
            f"route namespace={namespace} subcommand={subcommand} phase={phase}",
            flush=True,
        )

        self._send_json(
            200,
            {
                "ok": True,
                "message": f"mock accepted: {namespace}.{subcommand}",
                "echo": payload,
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local mock Hermes route endpoint.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), MockHermesHandler)
    print(f"Mock Hermes route server listening on http://{args.host}:{args.port}/route", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
