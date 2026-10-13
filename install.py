#!/usr/bin/env python3
"""Installer for ComfyUI-PhotoCraft (original code).

What it does (and only this):
* validates paths (ComfyUI root, photocraft-cli, automation roots),
* copies or symlinks this repo into <comfyui>/custom_nodes/comfyui-photocraft,
* writes config.json (paths + ports + token-file locations, never tokens).

What it NEVER does:
* no admin / sudo / elevation, no git operations, no pip installs,
* no network access, no writing outside the requested destinations.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _fail(msg: str) -> "SystemExit":
    return SystemExit(f"install: {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install ComfyUI-PhotoCraft (no admin, no git, no pip)")
    parser.add_argument("--comfyui-root", required=True, help="Path to your ComfyUI checkout")
    parser.add_argument("--photocraft-cli", default="photocraft-cli", help="Path to photocraft-cli (or name on PATH)")
    parser.add_argument("--control-host", default="127.0.0.1")
    parser.add_argument("--control-port", type=int, default=7878)
    parser.add_argument("--control-token-file", default="", help="Private file holding the PhotoCraft control token")
    parser.add_argument("--automation-read-root", default="")
    parser.add_argument("--automation-write-root", default="")
    parser.add_argument("--comfyui-host", default="127.0.0.1")
    parser.add_argument("--comfyui-port", type=int, default=8188)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8190)
    parser.add_argument("--backend-token-file", default="", help="Private file holding this bridge backend token")
    parser.add_argument("--mode", default="file", choices=["file", "live"])
    parser.add_argument("--link", action="store_true", help="Symlink instead of copy")
    parser.add_argument("--force", action="store_true", help="Replace an existing install at the destination")
    args = parser.parse_args(argv)

    if args.backend_host != "127.0.0.1":
        raise _fail("backend host must stay 127.0.0.1 (loopback only)")
    if args.control_host != "127.0.0.1":
        raise _fail("control host must stay 127.0.0.1 (loopback only)")

    comfyui_root = Path(args.comfyui_root)
    if not comfyui_root.is_dir():
        raise _fail(f"ComfyUI root not found: {comfyui_root}")
    if not (comfyui_root / "main.py").exists() and not (comfyui_root / "custom_nodes").is_dir():
        print("warning: ComfyUI root does not look like a ComfyUI checkout (no main.py / custom_nodes); continuing", file=sys.stderr)

    dest = comfyui_root / "custom_nodes" / "comfyui-photocraft"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if not args.force:
            raise _fail(f"destination already exists: {dest} (use --force to replace)")
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)

    if args.link:
        try:
            os.symlink(REPO_ROOT, dest, target_is_directory=True)
        except OSError as exc:
            raise _fail(f"could not create symlink (try without --link): {exc}") from exc
        print(f"linked {dest} -> {REPO_ROOT}")
    else:
        shutil.copytree(REPO_ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".git", "config.json"))
        print(f"copied {REPO_ROOT} -> {dest}")

    config = {
        "photocraft_cli": args.photocraft_cli,
        "control_host": args.control_host,
        "control_port": args.control_port,
        "control_token_file": args.control_token_file,
        "automation_read_root": args.automation_read_root,
        "automation_write_root": args.automation_write_root,
        "comfyui_host": args.comfyui_host,
        "comfyui_port": args.comfyui_port,
        "backend_host": args.backend_host,
        "backend_port": args.backend_port,
        "backend_token_file": args.backend_token_file,
        "inputs_dir": str(REPO_ROOT / "data" / "pc_inputs"),
        "outputs_dir": str(REPO_ROOT / "data" / "pc_outputs"),
        "mode": args.mode,
    }
    config_path = REPO_ROOT / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"wrote {config_path}")
    print("Next: start the bridge backend (python -m py.backend), open photocraft_panel/index.html,")
    print("and for live mode start PhotoCraft yourself with --control (see README).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
