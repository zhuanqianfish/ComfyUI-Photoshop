"""Import tests: the plugin must import without a real ComfyUI.

Stubs for folder_paths / server / nodes / comfy are installed into
sys.modules before importing the plugin package, mirroring what ComfyUI
provides. Uses unittest so it runs without pytest.
"""
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_stubs():
    for name in ("folder_paths", "server", "nodes", "comfy"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)


class TestImports(unittest.TestCase):
    def test_nodes_import_and_mappings(self):
        _install_stubs()
        import py.nodes as nodes_mod

        self.assertIn("PhotoCraftToComfyUI", nodes_mod.NODE_CLASS_MAPPINGS)
        self.assertIn("ComfyUIToPhotoCraft", nodes_mod.NODE_CLASS_MAPPINGS)
        self.assertIn("ClipPass", nodes_mod.NODE_CLASS_MAPPINGS)
        self.assertIn("ModelPass", nodes_mod.NODE_CLASS_MAPPINGS)
        self.assertIn("PhotoCraftControl", nodes_mod.NODE_CLASS_MAPPINGS)
        for name in nodes_mod.NODE_CLASS_MAPPINGS:
            self.assertIn(name, nodes_mod.NODE_DISPLAY_NAME_MAPPINGS)

    def test_package_import(self):
        _install_stubs()
        import __init__ as pkg  # noqa: F401 - repo-root package entry

        self.assertEqual(pkg.WEB_DIRECTORY, "js")
        self.assertIn("PhotoCraftToComfyUI", pkg.NODE_CLASS_MAPPINGS)

    def test_backend_helpers_import_without_aiohttp(self):
        import py.backend as backend_mod

        self.assertTrue(hasattr(backend_mod, "build_message"))
        self.assertTrue(hasattr(backend_mod, "ClientRegistry"))

    def test_adapter_import(self):
        import py.photocraft_adapter as adapter_mod

        self.assertTrue(hasattr(adapter_mod, "PhotoCraftAdapter"))

    def test_clip_model_pass_through(self):
        _install_stubs()
        from py.nodes import ClipPass, ModelPass

        sentinel = object()
        self.assertIs(ClipPass().pass_clip(sentinel)[0], sentinel)
        self.assertIs(ModelPass().pass_model(sentinel)[0], sentinel)


if __name__ == "__main__":
    unittest.main()
