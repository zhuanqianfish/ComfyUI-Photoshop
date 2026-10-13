"""ComfyUI-PhotoCraft: bridge PhotoCraft <-> ComfyUI (original code).

ComfyUI entry point. Registers the custom nodes and exposes the frontend
extension directory. No PhotoCraft source changes are required.
"""
try:
    from .py.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
except ImportError:  # top-level import (e.g. `import __init__` in tests)
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from py.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
