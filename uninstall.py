#!/usr/bin/env python3
"""Uninstaller for ComfyUI-PhotoCraft (original code).

Removes the installed copy/symlink from ComfyUI custom_nodes and,
optionally, the generated config.json. No admin, no git, no pip.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Uninstall ComfyUI-PhotoCraft")
    parser.add_argument("--comfyui-root", required=True, help="Path to your ComfyUI checkout")
    parser.add_argument("--remove-config", action="store_true", help="Also delete repo config.json")
    args = parser.parse_args(argv)

    dest = Path(args.comfyui_root) / "custom_nodes" / "comfyui-photocraft"
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
        print(f"removed {dest}")
    elif dest.is_dir():
        shutil.rmtree(dest)
        print(f"removed {dest}")
    else:
        print(f"nothing installed at {dest}")
    if args.remove_config:
        cfg = REPO_ROOT / "config.json"
        if cfg.exists():
            cfg.unlink()
            print(f"removed {cfg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
