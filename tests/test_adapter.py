"""Adapter tests: fake TCP control channel + file-mode staging. unittest only."""
import json
import socket
import sys
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from py.config import PluginConfig  # noqa: E402
from py.photocraft_adapter import PhotoCraftAdapter  # noqa: E402


class FakeControlServer(threading.Thread):
    """Minimal JSON-lines server: auth -> {"ok": true}, then one request."""

    def __init__(self, token: str):
        super().__init__(daemon=True)
        self.token = token
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.received: list[dict] = []

    def run(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                f = conn.makefile("rwb", buffering=0)
                auth_line = f.readline().decode("utf-8")
                auth = json.loads(auth_line)
                ok = auth.get("token") == self.token
                f.write((json.dumps({"ok": ok}) + "\n").encode("utf-8"))
                if not ok:
                    return
                req_line = f.readline().decode("utf-8")
                req = json.loads(req_line)
                self.received.append(req)
                f.write((json.dumps({"ok": True, "result": {"echo": req, "layers": []}}) + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                self.sock.close()
            except Exception:
                pass


class TestLiveAdapter(unittest.TestCase):
    def test_auth_and_engine_execute(self):
        token_file = Path(__file__).resolve().parent / ".test_token"
        token_file.write_text("test-token-abc\n", encoding="utf-8")
        try:
            server = FakeControlServer("test-token-abc")
            server.start()
            cfg = PluginConfig(
                control_host="127.0.0.1",
                control_port=server.port,
                control_token_file=str(token_file),
                mode="live",
            )
            adapter = PhotoCraftAdapter(cfg, mode="live")
            reply = adapter.execute_command("layer.new.layer", {"name": "Test"})
            self.assertTrue(reply.get("ok"))
            self.assertEqual(server.received[0]["method"], "engine.execute")
            self.assertEqual(server.received[0]["command"], "layer.new.layer")
        finally:
            if token_file.exists():
                token_file.unlink()

    def test_auth_rejected(self):
        token_file = Path(__file__).resolve().parent / ".test_token_bad"
        token_file.write_text("wrong-token\n", encoding="utf-8")
        try:
            server = FakeControlServer("expected-token")
            server.start()
            cfg = PluginConfig(
                control_host="127.0.0.1",
                control_port=server.port,
                control_token_file=str(token_file),
                mode="live",
            )
            adapter = PhotoCraftAdapter(cfg, mode="live")
            with self.assertRaises(Exception):
                adapter.execute_command("layer.new.layer", {})
        finally:
            if token_file.exists():
                token_file.unlink()

    def test_file_mode_execute_rejected(self):
        adapter = PhotoCraftAdapter(PluginConfig(mode="file"), mode="file")
        with self.assertRaises(Exception):
            adapter.execute_command("layer.new.layer", {})


class TestFileAdapter(unittest.TestCase):
    def test_export_png_copy(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            read_root = Path(tmp) / "read"
            write_root = Path(tmp) / "write"
            read_root.mkdir()
            write_root.mkdir()
            src = read_root / "doc.png"
            # Minimal 1x1 PNG.
            from PIL import Image

            Image.new("RGB", (4, 3), (255, 0, 0)).save(src)
            cfg = PluginConfig(
                automation_read_root=str(read_root),
                automation_write_root=str(write_root),
                inputs_dir=str(Path(tmp) / "inputs"),
                outputs_dir=str(Path(tmp) / "outputs"),
                mode="file",
            )
            adapter = PhotoCraftAdapter(cfg, mode="file")
            out = adapter.export_canvas_mask(src, write_root / "PC_canvas.png", write_root / "PC_mask.png")
            self.assertEqual(out["status"], "ok")
            self.assertTrue(Path(out["canvas"]).exists())
            self.assertTrue(Path(out["mask"]).exists())

    def test_path_outside_root_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cfg = PluginConfig(
                automation_read_root=str(Path(tmp) / "read"),
                automation_write_root=str(Path(tmp) / "write"),
                mode="file",
            )
            adapter = PhotoCraftAdapter(cfg, mode="file")
            with self.assertRaises(Exception):
                adapter.export_canvas_mask("/etc/passwd")


if __name__ == "__main__":
    unittest.main()
