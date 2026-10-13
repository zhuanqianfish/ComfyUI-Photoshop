"""Protocol tests: WS messages, path traversal, token checks. unittest only."""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from py.backend import (  # noqa: E402
    ClientRegistry,
    build_message,
    extract_bearer_token,
    is_loopback,
    parse_message,
    safe_inputs_path,
    validate_bearer_token,
)
from py.config import PluginConfig, is_within_root, resolve_safe_path  # noqa: E402


class TestMessages(unittest.TestCase):
    def test_build_message(self):
        msg = build_message("progress", {"value": 3, "max": 10})
        self.assertEqual(msg, {"type": "progress", "value": 3, "max": 10})

    def test_parse_message_ok(self):
        self.assertEqual(parse_message('{"type": "queue", "x": 1}'), {"type": "queue", "x": 1})

    def test_parse_message_rejects_bad_json(self):
        with self.assertRaises(ValueError):
            parse_message("not json")

    def test_parse_message_rejects_missing_type(self):
        with self.assertRaises(ValueError):
            parse_message('{"x": 1}')

    def test_all_message_types_constructible(self):
        for t in ("canvasBase64", "maskBase64", "configdata", "workspace", "queue",
                  "progress", "render", "photocraftConnected", "alert"):
            self.assertEqual(build_message(t)["type"], t)


class TestTokens(unittest.TestCase):
    def test_validate_ok_and_wrong(self):
        self.assertTrue(validate_bearer_token("secret", "secret"))
        self.assertFalse(validate_bearer_token("wrong", "secret"))
        self.assertFalse(validate_bearer_token(None, "secret"))

    def test_empty_expected_never_matches(self):
        self.assertFalse(validate_bearer_token("anything", ""))
        self.assertFalse(validate_bearer_token("", ""))

    def test_extract_bearer(self):
        self.assertEqual(extract_bearer_token({"Authorization": "Bearer abc"}), "abc")
        self.assertIsNone(extract_bearer_token({"Authorization": "Basic abc"}))
        self.assertIsNone(extract_bearer_token({}))


class TestPaths(unittest.TestCase):
    def test_safe_path_inside(self):
        cfg = PluginConfig(inputs_dir="/tmp/pc_test_inputs")
        # safe_inputs_path joins inside the root; traversal must raise.
        with self.assertRaises(ValueError):
            safe_inputs_path(cfg, "../escape.png")
        with self.assertRaises(ValueError):
            safe_inputs_path(cfg, "sub/../../../escape.png")

    def test_resolve_safe_path(self):
        root = Path("/tmp/pc_test_root")
        self.assertEqual(resolve_safe_path(root, "a/b.png"), (root / "a/b.png").resolve())
        with self.assertRaises(ValueError):
            resolve_safe_path(root, "../../etc/passwd")

    def test_is_within_root(self):
        self.assertTrue(is_within_root("/tmp/a", "/tmp/a/b.png"))
        self.assertFalse(is_within_root("/tmp/a", "/tmp/other/b.png"))
        self.assertFalse(is_within_root("/tmp/a", "../escape"))


class TestRegistry(unittest.TestCase):
    def test_pc_and_cm_tracked_separately(self):
        reg = ClientRegistry()
        reg.register("pc", "pc-1", object())
        reg.register("cm", "cm-1", object())
        reg.register("pc", "pc-2", object())
        self.assertEqual(reg.pc_ids(), ["pc-1", "pc-2"])
        self.assertEqual(reg.cm_ids(), ["cm-1"])
        # Unregistering one platform must not disturb the other.
        reg.unregister("pc", "pc-1")
        self.assertEqual(reg.pc_ids(), ["pc-2"])
        self.assertEqual(reg.cm_ids(), ["cm-1"])

    def test_unknown_platform_rejected(self):
        reg = ClientRegistry()
        with self.assertRaises(ValueError):
            reg.register("xx", "x-1", object())

    def test_loopback(self):
        self.assertTrue(is_loopback("127.0.0.1"))
        self.assertFalse(is_loopback("192.168.1.5"))


if __name__ == "__main__":
    unittest.main()
