"""PhotoCraft adapter (original code).

Two modes, no PhotoCraft source changes required:

* ``file`` mode -- drive ``photocraft-cli`` via subprocess with a timeout,
  and move files only inside the configured automation roots.
* ``live`` mode -- talk to a running PhotoCraft instance over its JSON
  control channel (TCP, JSON-lines, auth first). The user must start
  PhotoCraft themselves, e.g.::

      photocraft --control 7878 \
          --control-token-file <private-path> \
          --automation-read-root <dir> --automation-write-root <dir>

No ExtendScript, no ``photoshop-connection``, no admin rights, no git,
no pip. All paths are validated with ``commonpath`` checks.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from .config import PluginConfig, is_within_root, load_config, read_token, resolve_safe_path

CONTROL_TIMEOUT = 60.0


class AdapterError(RuntimeError):
    """Raised for adapter-level failures (timeout, protocol, CLI)."""


class PhotoCraftAdapter:
    """Bridge between ComfyUI outputs and PhotoCraft (file or live)."""

    def __init__(self, config: PluginConfig | None = None, mode: str | None = None):
        self.config = config or load_config()
        self.mode = mode or self.config.mode
        if self.mode not in ("file", "live"):
            raise ValueError(f"mode must be 'file' or 'live', got {self.mode!r}")

    # -- helpers ---------------------------------------------------------
    def _check_root(self, root: str, path: str | Path) -> Path:
        if not root:
            raise AdapterError("automation root is not configured; set it in config.json")
        if not is_within_root(root, path):
            raise AdapterError(f"path outside automation root: {path!r}")
        return Path(path).resolve() if Path(path).is_absolute() else (Path(root).resolve() / Path(path)).resolve()

    def _run_cli(self, args: list[str], timeout: float = 120.0) -> subprocess.CompletedProcess:
        cli = self.config.photocraft_cli
        if not shutil.which(cli) and not Path(cli).exists():
            raise AdapterError(f"photocraft-cli not found: {cli!r}")
        try:
            return subprocess.run(
                [cli, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"photocraft-cli timed out after {timeout}s: {args}") from exc

    # -- file mode -------------------------------------------------------
    def export_canvas_mask(
        self,
        source_path: str | Path,
        canvas_out: str | Path | None = None,
        mask_out: str | Path | None = None,
    ) -> dict:
        """Export canvas (+ optional mask) from a PhotoCraft document.

        ``source_path`` may be a .pcraft / .psd / .psb / .png file inside the
        read root. The canvas is written as PNG inside the write root (or the
        inputs dir when no write root is configured). Returns paths + status.
        """
        read_root = self.config.automation_read_root or str(Path(self.config.inputs_dir).parent)
        src = self._check_root(read_root, source_path)
        if not src.exists():
            raise AdapterError(f"source document not found: {src}")
        out_dir = Path(self.config.automation_write_root) if self.config.automation_write_root else Path(self.config.inputs_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        canvas_path = Path(canvas_out) if canvas_out else out_dir / "PC_canvas.png"
        if not is_within_root(out_dir, canvas_path):
            raise AdapterError(f"canvas output outside root: {canvas_path!r}")
        suffix = src.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".webp"):
            shutil.copyfile(src, canvas_path)
        else:
            # PSD / PSB / .pcraft / TIFF etc: ask photocraft-cli to convert.
            result = self._run_cli(["convert", str(src), "--out", str(canvas_path)])
            if result.returncode != 0:
                raise AdapterError(f"photocraft-cli convert failed: {result.stderr.strip()}")
            if not canvas_path.exists():
                raise AdapterError("photocraft-cli convert reported success but no output file appeared")
        payload: dict[str, Any] = {"canvas": str(canvas_path), "status": "ok"}
        if mask_out is not None:
            mask_path = Path(mask_out)
            if not is_within_root(out_dir, mask_path):
                raise AdapterError(f"mask output outside root: {mask_path!r}")
            # No separate mask source in file mode: create a blank (white)
            # mask with the same size as the canvas, via Pillow when present.
            try:
                from PIL import Image

                with Image.open(canvas_path) as im:
                    mask = Image.new("L", im.size, 255)
                    mask.save(mask_path)
                payload["mask"] = str(mask_path)
            except Exception:
                # Pillow is optional in minimal environments; caller may
                # supply its own mask file instead.
                payload["mask"] = None
                payload["mask_note"] = "Pillow unavailable; no mask generated"
        return payload

    def import_result(
        self,
        result_image_path: str | Path,
        target_document: str | Path | None = None,
        as_new_layer: bool = True,
        layer_name: str = "ComfyUI Result",
    ) -> dict:
        """Import a rendered image back into PhotoCraft (file mode).

        File mode cannot mutate a live document; it stages the result as a
        new file inside the write root and, when ``target_document`` names
        an existing document, asks ``photocraft-cli run`` to place it.
        Live mode callers should use :meth:`execute_command` instead for
        in-app placement.
        """
        write_root = self.config.automation_write_root or str(Path(self.config.inputs_dir).parent)
        src = self._check_root(write_root, result_image_path) if Path(result_image_path).exists() else None
        # Also allow reading the result from the plugin outputs dir.
        if src is None:
            outputs = Path(self.config.outputs_dir)
            candidate = (outputs / Path(result_image_path).name).resolve() if not Path(result_image_path).is_absolute() else Path(result_image_path).resolve()
            if not candidate.exists():
                raise AdapterError(f"result image not found: {result_image_path!r}")
            src = candidate
        out_dir = Path(write_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        staged = out_dir / f"pc_import_{Path(src).name}"
        if staged.resolve() != src.resolve():
            shutil.copyfile(src, staged)
        result: dict[str, Any] = {
            "staged": str(staged),
            "as_new_layer": as_new_layer,
            "layer_name": layer_name,
            "status": "staged",
        }
        if target_document is not None:
            target = self._check_root(self.config.automation_read_root or write_root, target_document)
            if not target.exists():
                raise AdapterError(f"target document not found: {target!r}")
            cli_result = self._run_cli(
                ["run", str(target), "--place", str(staged), "--layer-name", layer_name]
            )
            result["cli_returncode"] = cli_result.returncode
            result["cli_stdout"] = cli_result.stdout.strip()
            result["cli_stderr"] = cli_result.stderr.strip()
            result["status"] = "placed" if cli_result.returncode == 0 else "cli_failed"
        return result

    def get_layer_tree(self, document_path: str | Path | None = None) -> dict:
        """Return the layer tree for a document.

        Live mode: ``engine.execute`` with ``doc.info``. File mode: use
        ``photocraft-cli info`` on the given document.
        """
        if self.mode == "live":
            return self.execute_command("doc.info", {"document": str(document_path) if document_path else None})
        if document_path is None:
            raise AdapterError("file mode get_layer_tree requires document_path")
        read_root = self.config.automation_read_root or str(Path(document_path).parent)
        doc = self._check_root(read_root, document_path)
        cli_result = self._run_cli(["info", str(doc)])
        if cli_result.returncode != 0:
            raise AdapterError(f"photocraft-cli info failed: {cli_result.stderr.strip()}")
        try:
            return json.loads(cli_result.stdout) if cli_result.stdout.strip() else {"raw": cli_result.stdout}
        except json.JSONDecodeError:
            return {"raw": cli_result.stdout}

    # -- live mode: JSON-lines control channel ---------------------------
    def _live_request(self, payload: dict, timeout: float = CONTROL_TIMEOUT) -> dict:
        """Send one request over the control channel and return the reply.

        Protocol (JSON-lines, one JSON object per line):
          client -> {"type": "auth", "token": "<token>"}
          server -> {"ok": true}   (or {"ok": false, "error": ...})
          client -> <payload>      (e.g. {"method": "engine.execute", ...})
          server -> {"ok": true, "result": ...} | {"ok": false, "error": ...}

        Timeout semantics: a timeout before any reply to the request means
        the request was *not confirmed run*; a timeout after the server
        acknowledged dispatch is reported as *dispatched, result unknown*.
        """
        if not self.config.control_token_file:
            raise AdapterError("live mode requires control_token_file in config.json")
        token = read_token(self.config.control_token_file)
        sock = socket.create_connection(
            (self.config.control_host, self.config.control_port), timeout=timeout
        )
        try:
            stream = sock.makefile("rwb", buffering=0)
            try:
                stream.write((json.dumps({"type": "auth", "token": token}) + "\n").encode("utf-8"))
                ack_raw = self._read_line(stream, timeout)
                ack = json.loads(ack_raw)
                if not ack.get("ok"):
                    raise AdapterError(f"control-channel auth rejected: {ack.get('error', 'unknown')}")
                stream.write((json.dumps(payload) + "\n").encode("utf-8"))
                try:
                    reply_raw = self._read_line(stream, timeout)
                except TimeoutError:
                    raise TimeoutError(
                        "timeout: request dispatched, result unknown - check PhotoCraft manually"
                    ) from None
                reply = json.loads(reply_raw)
                if not reply.get("ok", True):
                    raise AdapterError(f"control-channel error: {reply.get('error', 'unknown')}")
                return reply
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
        except socket.timeout as exc:
            raise TimeoutError("timeout: request not confirmed run") from exc
        finally:
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _read_line(stream, timeout: float) -> str:
        """Read one line, converting a socket timeout to TimeoutError."""
        import select

        # makefile objects from a socket support readline with timeout via
        # the socket timeout; wrap any timeout into TimeoutError.
        try:
            raw = stream.readline()
        except socket.timeout as exc:
            raise TimeoutError("timeout waiting for control-channel reply") from exc
        except OSError as exc:
            raise AdapterError(f"control-channel read failed: {exc}") from exc
        if not raw:
            raise AdapterError("control-channel closed the connection")
        return raw.decode("utf-8").strip()

    def execute_command(self, command: str, params: dict | None = None) -> dict:
        """Execute a PhotoCraft engine command (live mode only).

        ``command`` is e.g. ``"layer.new.layer"``; ``params`` is a JSON
        object. Returns the decoded reply dict.
        """
        if self.mode != "live":
            raise AdapterError("execute_command requires live mode (start PhotoCraft with --control)")
        if not isinstance(command, str) or not command.strip():
            raise AdapterError("command must be a non-empty string")
        payload = {
            "method": "engine.execute",
            "command": command,
            "params": params or {},
        }
        return self._live_request(payload)

    def inspect_ui(self) -> dict:
        """Return ``ui.inspect`` output (live mode)."""
        if self.mode != "live":
            raise AdapterError("inspect_ui requires live mode")
        return self._live_request({"method": "ui.inspect"})

    def screenshot(self) -> dict:
        """Return ``ui.screenshot`` output (live mode)."""
        if self.mode != "live":
            raise AdapterError("screenshot requires live mode")
        return self._live_request({"method": "ui.screenshot"})
