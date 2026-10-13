"""Configuration for the ComfyUI-PhotoCraft bridge (original code).

No secrets are hard-coded here. The bearer token is always read from a
private token file supplied by the user (see :func:`read_token`).
All file access is confined to the configured automation roots.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PluginConfig:
    """Runtime configuration for the bridge.

    Attributes:
        photocraft_cli: Path to the ``photocraft-cli`` binary (file mode).
        control_host: PhotoCraft control-channel host (live mode).
        control_port: PhotoCraft control-channel TCP port (live mode).
        control_token_file: Private file holding the control-channel token.
        automation_read_root: Directory PhotoCraft may read from.
        automation_write_root: Directory PhotoCraft may write to.
        comfyui_host: ComfyUI host (local only).
        comfyui_port: ComfyUI port.
        backend_host: This bridge backend host; must stay loopback.
        backend_port: This bridge backend port.
        backend_token_file: Private file holding this bridge's token.
        inputs_dir: Directory holding PC_canvas.png / PC_mask.png / config.json.
        outputs_dir: Directory for rendered outputs.
        mode: "file" or "live".
    """

    photocraft_cli: str = "photocraft-cli"
    control_host: str = "127.0.0.1"
    control_port: int = 7878
    control_token_file: str = ""
    automation_read_root: str = ""
    automation_write_root: str = ""
    comfyui_host: str = "127.0.0.1"
    comfyui_port: int = 8188
    backend_host: str = "127.0.0.1"
    backend_port: int = 8190
    backend_token_file: str = ""
    inputs_dir: str = ""
    outputs_dir: str = ""
    mode: str = "file"

    def __post_init__(self) -> None:
        if not self.inputs_dir:
            self.inputs_dir = str(REPO_ROOT / "data" / "pc_inputs")
        if not self.outputs_dir:
            self.outputs_dir = str(REPO_ROOT / "data" / "pc_outputs")
        if self.mode not in ("file", "live"):
            raise ValueError(f"mode must be 'file' or 'live', got {self.mode!r}")


def default_config_path() -> Path:
    """Return the default config.json path (repo root, or env override)."""
    override = os.environ.get("PHOTOCRAFT_PLUGIN_CONFIG")
    if override:
        return Path(override)
    return REPO_ROOT / "config.json"


def load_config(path: str | Path | None = None) -> PluginConfig:
    """Load configuration from JSON file; missing file -> defaults.

    Unknown keys are ignored so older config files keep working.
    """
    cfg_path = Path(path) if path is not None else default_config_path()
    data: dict = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = loaded
    known = {f for f in PluginConfig.__dataclass_fields__}
    filtered = {k: v for k, v in data.items() if k in known}
    return PluginConfig(**filtered)


def read_token(token_file: str | Path) -> str:
    """Read a bearer token from a private file.

    The file must exist and contain a non-empty token on its first line.
    No default / fallback token is ever used.
    """
    path = Path(token_file)
    if not path.exists():
        raise FileNotFoundError(f"token file not found: {path}")
    token = path.read_text(encoding="utf-8").splitlines()[0].strip() if path.read_text(encoding="utf-8").splitlines() else ""
    # Re-read once (kept simple and explicit); strip whitespace/newlines.
    if not token:
        raise ValueError(f"token file is empty: {path}")
    return token


def resolve_safe_path(root: str | Path, filename: str) -> Path:
    """Resolve ``filename`` inside ``root``; reject path traversal.

    Raises ValueError if the resolved path escapes ``root``.
    """
    root_path = Path(root).resolve()
    candidate = (root_path / filename).resolve()
    # commonpath check: candidate must be root itself or below it.
    import os.path as _osp

    if _osp.commonpath([str(root_path), str(candidate)]) != str(root_path):
        raise ValueError(f"path escapes root: {filename!r}")
    return candidate


def is_within_root(root: str | Path, candidate: str | Path) -> bool:
    """Return True iff ``candidate`` resolves inside ``root``.

    Relative candidates are interpreted relative to ``root``; absolute
    candidates are checked as-is.
    """
    import os.path as _osp

    root_path = Path(root).resolve()
    cand = Path(candidate)
    cand_path = (root_path / cand).resolve() if not cand.is_absolute() else cand.resolve()
    return _osp.commonpath([str(root_path), str(cand_path)]) == str(root_path)
