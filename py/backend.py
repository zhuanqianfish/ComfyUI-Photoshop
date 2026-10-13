"""Bridge backend (original code).

HTTP + WebSocket bridge between the standalone PhotoCraft side panel and
ComfyUI. Security rules (deliberate fixes for the flaws found in the
reference Photoshop bridge):

* Binds only to 127.0.0.1 (loopback). Never expose to a LAN / public IP.
* Every ``/pc/*`` route requires a Bearer token read from a private token
  file. There is no default password and no unauthenticated route.
* No ``git`` operations, no automatic ``pip install``, no installer that
  requests admin rights, no code execution from strings.
* File names are validated with ``commonpath`` checks; reads/writes stay
  inside the configured automation roots / inputs / outputs dirs.
* Clients are tracked in two explicit dicts (``pc_clients`` / ``cm_clients``),
  never ``users[-1]`` style last-client routing.

Pure helpers in this module are importable without aiohttp so the protocol
can be unit-tested. ``create_app()`` imports aiohttp lazily and is only
used when actually serving.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .config import PluginConfig, load_config, read_token, resolve_safe_path

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


# -- pure helpers (no aiohttp) -------------------------------------------

def validate_bearer_token(provided: str | None, expected: str) -> bool:
    """Constant-time-ish bearer comparison; empty expected never matches."""
    if not provided or not expected:
        return False
    # Use hmac.compare_digest to avoid timing leaks.
    import hmac

    return hmac.compare_digest(provided.strip(), expected.strip())


def extract_bearer_token(headers: dict) -> str | None:
    """Extract a Bearer token from an Authorization header dict."""
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return auth[7:].strip() or None


def build_message(msg_type: str, payload: dict | None = None, **extra: Any) -> dict:
    """Build a wire message: {"type": ..., ...payload, ...extra}."""
    msg: dict[str, Any] = {"type": msg_type}
    if payload:
        msg.update(payload)
    msg.update(extra)
    return msg


def parse_message(raw: str) -> dict:
    """Parse one inbound JSON message; raises ValueError on bad input."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON message: {exc}") from exc
    if not isinstance(data, dict) or "type" not in data:
        raise ValueError("message must be a JSON object with a 'type' field")
    return data


def is_loopback(remote: str | None) -> bool:
    return (remote or "") in LOOPBACK_HOSTS


class ClientRegistry:
    """Explicit per-platform client tracking (no last-client guessing)."""

    def __init__(self) -> None:
        self.pc_clients: dict[str, Any] = {}
        self.cm_clients: dict[str, Any] = {}

    def register(self, platform: str, client_id: str, conn: Any) -> None:
        if platform == "pc":
            self.pc_clients[client_id] = conn
        elif platform == "cm":
            self.cm_clients[client_id] = conn
        else:
            raise ValueError(f"unknown platform: {platform!r}")

    def unregister(self, platform: str, client_id: str) -> None:
        table = self.pc_clients if platform == "pc" else self.cm_clients if platform == "cm" else None
        if table is not None:
            table.pop(client_id, None)

    def pc_ids(self) -> list[str]:
        return sorted(self.pc_clients)

    def cm_ids(self) -> list[str]:
        return sorted(self.cm_clients)

    def get_pc(self, client_id: str) -> Any | None:
        return self.pc_clients.get(client_id)

    def get_cm(self, client_id: str) -> Any | None:
        return self.cm_clients.get(client_id)


def md5_of_files(paths: list[Path]) -> str:
    """MD5 over the concatenated bytes of the given files (missing = skip)."""
    h = hashlib.md5()
    for path in paths:
        if Path(path).exists():
            h.update(Path(path).read_bytes())
    return h.hexdigest()


def safe_inputs_path(config: PluginConfig, filename: str) -> Path:
    """Resolve an inputs filename inside the inputs dir (traversal-safe)."""
    return resolve_safe_path(config.inputs_dir, filename)


def safe_output_path(config: PluginConfig, filename: str) -> Path:
    """Resolve an outputs filename inside the outputs dir (traversal-safe)."""
    return resolve_safe_path(config.outputs_dir, filename)


# -- aiohttp app (lazy import) -------------------------------------------

def create_app(config: PluginConfig | None = None):
    """Create the aiohttp application. Requires aiohttp at runtime."""
    try:
        from aiohttp import web
    except ImportError as exc:
        raise RuntimeError("aiohttp is required to serve the bridge backend; install it in your ComfyUI environment") from exc

    cfg = config or load_config()
    registry = ClientRegistry()

    def _expected_token() -> str:
        if not cfg.backend_token_file:
            raise RuntimeError("backend_token_file is not configured; refusing to serve without a token")
        return read_token(cfg.backend_token_file)

    def _require_auth(request) -> bool:
        token = extract_bearer_token(request.headers)
        if token is None:
            token = request.query.get("token")
        try:
            expected = _expected_token()
        except Exception:
            return False
        return validate_bearer_token(token, expected)

    def _require_loopback(request) -> bool:
        return is_loopback(request.remote)

    app = web.Application()
    app["registry"] = registry
    app["config"] = cfg

    async def status_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return web.json_response(
            {
                "ok": True,
                "mode": cfg.mode,
                "pc_clients": registry.pc_ids(),
                "cm_clients": registry.cm_ids(),
                "inputs_dir": cfg.inputs_dir,
            }
        )

    async def workflows_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        name = request.match_info["name"]
        workflows_dir = Path(__file__).resolve().parent.parent / "data" / "workflows"
        try:
            path = resolve_safe_path(workflows_dir, name)
        except ValueError:
            return web.json_response({"error": "invalid workflow name"}, status=400)
        if not path.exists():
            return web.json_response({"error": "workflow not found"}, status=404)
        return web.json_response(json.loads(path.read_text(encoding="utf-8")))

    async def inputs_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        filename = request.match_info["filename"]
        try:
            path = safe_inputs_path(cfg, filename)
        except ValueError:
            return web.json_response({"error": "invalid filename"}, status=400)
        if not path.exists():
            return web.json_response({"error": "file not found"}, status=404)
        return web.FileResponse(path)

    async def renderdone_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        filename = request.query.get("filename", "")
        if not filename:
            return web.json_response({"error": "filename is required"}, status=400)
        try:
            path = safe_output_path(cfg, filename)
        except ValueError:
            return web.json_response({"error": "invalid filename"}, status=400)
        if not path.exists():
            return web.json_response({"error": "file not found"}, status=404)
        blob = base64.b64encode(path.read_bytes()).decode("ascii")
        msg = build_message("render", {"filename": path.name, "imageBase64": blob})
        # Fan out to every registered PhotoCraft-side client.
        for conn in list(registry.pc_clients.values()):
            try:
                await conn.send_str(json.dumps(msg))
            except Exception:
                continue
        return web.json_response({"ok": True, "filename": path.name, "bytes": len(blob)})

    async def command_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON body"}, status=400)
        command = body.get("command", "")
        params = body.get("params", {})
        if not isinstance(command, str) or not command.strip():
            return web.json_response({"error": "command is required"}, status=400)
        if not isinstance(params, dict):
            return web.json_response({"error": "params must be an object"}, status=400)
        # Only allowlist-safe delegation: live adapter executes the command.
        # File-mode requests that only stage files are handled by the panel
        # via the adapter's import path, not by executing arbitrary code.
        if cfg.mode != "live":
            return web.json_response(
                {"ok": False, "error": "command execution requires live mode (start PhotoCraft with --control)"},
                status=409,
            )
        from .photocraft_adapter import PhotoCraftAdapter

        adapter = PhotoCraftAdapter(cfg, mode="live")
        try:
            result = adapter.execute_command(command, params)
        except TimeoutError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=504)
        except Exception as exc:  # noqa: BLE001 - surface adapter errors as JSON
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
        return web.json_response({"ok": True, "result": result})

    async def ws_handler(request):
        if not _require_loopback(request):
            return web.json_response({"error": "loopback only"}, status=403)
        if not _require_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        platform = request.query.get("platform", "")
        if platform not in ("pc", "cm"):
            return web.json_response({"error": "platform must be 'pc' or 'cm'"}, status=400)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        client_id = f"{platform}-{id(ws)}"
        registry.register(platform, client_id, ws)
        await ws.send_str(json.dumps(build_message("photocraftConnected" if platform == "pc" else "comfyConnected", {"client_id": client_id})))
        try:
            async for raw in ws:
                try:
                    msg = parse_message(raw.data)
                except ValueError as exc:
                    await ws.send_str(json.dumps(build_message("alert", {"message": str(exc)})))
                    continue
                mtype = msg.get("type")
                # Forward canvas / mask / config / workspace / queue /
                # progress messages to the *other* platform's clients.
                if mtype in ("canvasBase64", "maskBase64", "configdata", "workspace", "queue", "progress"):
                    targets = registry.cm_clients if platform == "pc" else registry.pc_clients
                    for conn in list(targets.values()):
                        try:
                            await conn.send_str(json.dumps(msg))
                        except Exception:
                            continue
                elif mtype == "alert":
                    await ws.send_str(json.dumps(build_message("alert", {"message": "received"})))
                else:
                    await ws.send_str(json.dumps(build_message("alert", {"message": f"unknown message type: {mtype}"})))
        finally:
            registry.unregister(platform, client_id)
        return ws

    app.router.add_get("/pc/status", status_handler)
    app.router.add_get("/pc/workflows/{name}", workflows_handler)
    app.router.add_get("/pc/inputs/{filename}", inputs_handler)
    app.router.add_get("/pc/renderdone", renderdone_handler)
    app.router.add_post("/pc/command", command_handler)
    app.router.add_get("/pc/ws", ws_handler)
    return app


def main() -> None:
    """Serve the backend on loopback only. Run: python -m py.backend."""
    import argparse

    parser = argparse.ArgumentParser(description="ComfyUI-PhotoCraft bridge backend (loopback only)")
    parser.add_argument("--host", default="127.0.0.1", help="must stay 127.0.0.1")
    parser.add_argument("--port", type=int, default=8190)
    args = parser.parse_args()
    if args.host not in LOOPBACK_HOSTS:
        raise SystemExit("refusing to bind to a non-loopback host")
    from aiohttp import web

    cfg = load_config()
    cfg.backend_host = args.host
    cfg.backend_port = args.port
    web.run_app(create_app(cfg), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
