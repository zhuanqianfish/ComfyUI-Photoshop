"""ComfyUI custom nodes for PhotoCraft (original code).

Import-safe: torch / folder_paths / server are optional here so the module
can be imported (and unit-tested) without a running ComfyUI. In a real
ComfyUI environment the real implementations are used.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

try:
    import torch  # type: ignore
except Exception:  # noqa: BLE001
    torch = None  # type: ignore

try:
    import folder_paths  # type: ignore
except Exception:  # noqa: BLE001
    folder_paths = None  # type: ignore

try:
    from PIL import Image
    import numpy as np
except Exception:  # noqa: BLE001
    Image = None  # type: ignore
    np = None  # type: ignore

from .config import REPO_ROOT, load_config, resolve_safe_path

INPUTS_DIR = REPO_ROOT / "data" / "pc_inputs"
OUTPUTS_DIR = REPO_ROOT / "data" / "pc_outputs"

DEFAULT_POSITIVE = "a clean, detailed image"
DEFAULT_NEGATIVE = "blurry, low quality, artifacts"
DEFAULT_LAYER = "ComfyUI Result"
DEFAULT_BOUNDS = "0,0,0,0"


def _md5_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.md5(path.read_bytes()).hexdigest()


def _inputs_signature(inputs_dir: str | Path) -> str:
    base = Path(inputs_dir) if inputs_dir else INPUTS_DIR
    parts = []
    for name in ("PC_canvas.png", "PC_mask.png", "config.json"):
        parts.append(f"{name}:{_md5_file(base / name)}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _load_pc_config(inputs_dir: str | Path) -> dict:
    base = Path(inputs_dir) if inputs_dir else INPUTS_DIR
    cfg_path = base / "config.json"
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pil_to_tensor(pil_image) -> Any:
    """PIL -> ComfyUI IMAGE tensor ([1, H, W, C], float 0..1)."""
    arr = np.asarray(pil_image.convert("RGB"), dtype=np.float32) / 255.0
    if torch is not None:
        return torch.from_numpy(arr)[None, :]
    return arr[None, :]


def _pil_to_mask(pil_image) -> Any:
    arr = np.asarray(pil_image.convert("L"), dtype=np.float32) / 255.0
    if torch is not None:
        return torch.from_numpy(arr)[None, :]
    return arr[None, :]


def _blank_image(width: int, height: int) -> Any:
    blank = Image.new("RGB", (max(1, width), max(1, height)), (128, 128, 128))
    return _pil_to_tensor(blank)


def _blank_mask(width: int, height: int) -> Any:
    blank = Image.new("L", (max(1, width), max(1, height)), 255)
    return _pil_to_mask(blank)


class PhotoCraftToComfyUI:
    """Read PhotoCraft canvas / mask / config into a ComfyUI workflow."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "slider": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.01}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**63 - 1}),
                "positive": ("STRING", {"default": DEFAULT_POSITIVE, "multiline": True}),
                "negative": ("STRING", {"default": DEFAULT_NEGATIVE, "multiline": True}),
                "layer_name": ("STRING", {"default": DEFAULT_LAYER}),
                "selection_bounds": ("STRING", {"default": DEFAULT_BOUNDS}),
            },
            "optional": {
                "inputs_dir": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "STRING", "STRING", "INT", "INT", "STRING", "STRING")
    RETURN_NAMES = ("canvas", "mask", "slider", "seed", "positive", "negative", "width", "height", "layer_name", "selection_bounds")
    FUNCTION = "load_inputs"
    CATEGORY = "PhotoCraft"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        inputs_dir = kwargs.get("inputs_dir") or ""
        return _inputs_signature(inputs_dir)

    def load_inputs(self, slider=0.7, seed=0, positive=DEFAULT_POSITIVE, negative=DEFAULT_NEGATIVE,
                    layer_name=DEFAULT_LAYER, selection_bounds=DEFAULT_BOUNDS, inputs_dir=""):
        base = Path(inputs_dir) if inputs_dir else INPUTS_DIR
        cfg = _load_pc_config(base)
        # config.json wins for values it defines; node inputs are fallbacks.
        slider = float(cfg.get("slider", slider))
        seed = int(cfg.get("seed", seed))
        positive = str(cfg.get("positive", positive))
        negative = str(cfg.get("negative", negative))
        layer_name = str(cfg.get("layer_name", layer_name))
        selection_bounds = str(cfg.get("selection_bounds", selection_bounds))
        width = int(cfg.get("width", 0) or 0)
        height = int(cfg.get("height", 0) or 0)

        canvas_path = base / "PC_canvas.png"
        mask_path = base / "PC_mask.png"
        if canvas_path.exists() and Image is not None:
            with Image.open(canvas_path) as im:
                canvas = _pil_to_tensor(im)
                width = width or im.width
                height = height or im.height
        else:
            canvas = _blank_image(width or 512, height or 512)
            width = width or 512
            height = height or 512
        if mask_path.exists() and Image is not None:
            with Image.open(mask_path) as im:
                mask = _pil_to_mask(im)
        else:
            mask = _blank_mask(width, height)
        return (canvas, mask, slider, seed, positive, negative, width, height, layer_name, selection_bounds)


class ComfyUIToPhotoCraft:
    """Save a ComfyUI image and notify the bridge (SaveImage-style)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "pc_result"}),
            },
            "optional": {
                "backend_port": ("INT", {"default": 8190, "min": 1, "max": 65535}),
                "backend_token": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "save_and_notify"
    OUTPUT_NODE = True
    CATEGORY = "PhotoCraft"

    def save_and_notify(self, images, filename_prefix="pc_result", backend_port=8190, backend_token=""):
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        saved: list[dict] = []
        # images is a batch tensor; handle torch / numpy / list uniformly.
        batch = images
        count = 1
        try:
            count = int(batch.shape[0])  # type: ignore[attr-defined]
        except Exception:
            count = len(batch) if hasattr(batch, "__len__") else 1
        for idx in range(count):
            try:
                item = batch[idx]
                if torch is not None and hasattr(item, "cpu"):
                    arr = (item.cpu().numpy() * 255.0).clip(0, 255).astype("uint8")
                elif np is not None:
                    arr = (np.asarray(item) * 255.0).clip(0, 255).astype("uint8")
                else:
                    continue
            except Exception:
                continue
            pil = Image.fromarray(arr)
            filename = f"{filename_prefix}_{idx:05d}.png"
            # Traversal-safe: name is constructed by us, not user input.
            out_path = resolve_safe_path(OUTPUTS_DIR, filename)
            pil.save(out_path)
            saved.append({"filename": filename, "subfolder": "", "type": "output"})
        # Best-effort notify: GET /pc/renderdone?filename=... . Failures are
        # ignored -- the file on disk is the durable result.
        notified = False
        if saved and backend_token:
            for entry in saved:
                url = f"http://127.0.0.1:{int(backend_port)}/pc/renderdone?filename={entry['filename']}"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {backend_token}"})
                try:
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        notified = resp.status == 200
                except Exception:
                    notified = False
        # Durable sidecar so the panel / adapter can pick up the render
        # even when the backend was not running at save time.
        sidecar = OUTPUTS_DIR / "last_render.json"
        sidecar.write_text(json.dumps({"files": saved, "notified": notified}, indent=2), encoding="utf-8")
        return {"ui": {"images": saved}}


class ClipPass:
    """Pass a CLIP object through unchanged."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"clip": ("CLIP",)}}

    RETURN_TYPES = ("CLIP",)
    FUNCTION = "pass_clip"
    CATEGORY = "PhotoCraft"

    def pass_clip(self, clip):
        return (clip,)


class ModelPass:
    """Pass a MODEL object through unchanged."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",)}}

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "pass_model"
    CATEGORY = "PhotoCraft"

    def pass_model(self, model):
        return (model,)


class PhotoCraftControl:
    """Execute a PhotoCraft engine command via the control channel (live)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "command": ("STRING", {"default": "layer.new.layer"}),
                "params": ("STRING", {"default": "{}", "multiline": True}),
                "host": ("STRING", {"default": "127.0.0.1"}),
                "port": ("INT", {"default": 7878, "min": 1, "max": 65535}),
                "token_file": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "execute"
    CATEGORY = "PhotoCraft"

    def execute(self, command, params="{}", host="127.0.0.1", port=7878, token_file=""):
        from .config import PluginConfig
        from .photocraft_adapter import PhotoCraftAdapter

        try:
            parsed = json.loads(params) if isinstance(params, str) else params
        except json.JSONDecodeError as exc:
            raise ValueError(f"params must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("params must be a JSON object")
        cfg = PluginConfig(
            control_host=host,
            control_port=int(port),
            control_token_file=token_file,
            mode="live",
        )
        adapter = PhotoCraftAdapter(cfg, mode="live")
        result = adapter.execute_command(command, parsed)
        return (json.dumps(result, ensure_ascii=False),)


NODE_CLASS_MAPPINGS = {
    "PhotoCraftToComfyUI": PhotoCraftToComfyUI,
    "ComfyUIToPhotoCraft": ComfyUIToPhotoCraft,
    "ClipPass": ClipPass,
    "ModelPass": ModelPass,
    "PhotoCraftControl": PhotoCraftControl,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PhotoCraftToComfyUI": "PhotoCraft -> ComfyUI",
    "ComfyUIToPhotoCraft": "ComfyUI -> PhotoCraft",
    "ClipPass": "Clip Pass",
    "ModelPass": "Model Pass",
    "PhotoCraftControl": "PhotoCraft Control",
}
