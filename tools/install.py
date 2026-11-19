#!/usr/bin/env python3
"""Unified zero-dependency multi-agent installer (Python 3.10+ stdlib only).

Installs core skills + selected target plugins into .agents/skills/ and/or .claude/skills/
using POSIX symlinks on Linux/macOS, Windows directory junctions (no Admin required),
or --copy fallback for CI/container filesystems.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
if str(KIT_ROOT) not in sys.path:
    sys.path.insert(0, str(KIT_ROOT))

from shared.paths import write_pointer_manifest  # noqa: E402

AGENT_DEST_MAP = {
    "agents": ".agents/skills",
    "claude": ".claude/skills",
}


def _create_link(src: Path, dst: Path, copy_mode: bool = False) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)

    if copy_mode:
        shutil.copytree(src, dst)
        return "copy"

    if platform.system() == "Windows":
        # Directory junctions require neither Admin nor Developer Mode
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return "junction"
        shutil.copytree(src, dst)
        return "copy-fallback"

    os.symlink(src, dst, target_is_directory=True)
    return "symlink"


def collect_skill_dirs(kit_root: Path, targets: list[str], packs: list[str]) -> list[Path]:
    skills: list[Path] = []
    core_dir = kit_root / "skills" / "core"
    if core_dir.is_dir():
        for d in sorted(core_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                skills.append(d)

    targets_dir = kit_root / "plugins" / "targets"
    for t in targets:
        folder_name = t if t.startswith("blender-target-") else f"blender-target-{t}"
        t_dir = targets_dir / folder_name
        if not (t_dir / "SKILL.md").is_file():
            raise FileNotFoundError(f"Target plugin not found: {t_dir}")
        skills.append(t_dir)

    for pack in packs:
        p_dir = kit_root / "plugins" / pack
        if p_dir.is_dir():
            for d in sorted(p_dir.iterdir()):
                if d.is_dir() and (d / "SKILL.md").is_file():
                    skills.append(d)

    return skills


def install_skills(
    agent: str = "all",
    targets: list[str] | None = None,
    packs: list[str] | None = None,
    project_dir: Path | None = None,
    copy_mode: bool = False,
    kit_root: Path | None = None,
    manifest_path: Path | None = None,
) -> dict:
    root = (kit_root or KIT_ROOT).resolve()
    target_list = targets if targets is not None else ["unity"]
    pack_list = packs or []
    skill_dirs = collect_skill_dirs(root, target_list, pack_list)

    base = project_dir.resolve() if project_dir else Path.home()
    dest_keys = ["agents", "claude"] if agent == "all" else (
        ["claude"] if agent == "claude" else ["agents"]
    )

    installed: list[dict] = []
    for key in dest_keys:
        dest_root = base / AGENT_DEST_MAP[key]
        for sdir in skill_dirs:
            dst = dest_root / sdir.name
            mode = _create_link(sdir, dst, copy_mode=copy_mode)
            installed.append({"skill": sdir.name, "dest": str(dst), "mode": mode})

    pointer = write_pointer_manifest(root, installed_targets=target_list, manifest_path=manifest_path)
    return {
        "status": "ok",
        "kit_root": str(root),
        "pointer_manifest": str(pointer),
        "installed_count": len(installed),
        "installed": installed,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Install blender-agent-kit skills for AI coding agents.")
    p.add_argument(
        "--agent",
        choices=["all", "claude", "codex", "cursor", "gemini", "copilot", "opencode"],
        default="all",
    )
    p.add_argument("--targets", nargs="*", default=["unity"], help="Target plugins (e.g. unity)")
    p.add_argument("--packs", nargs="*", default=[], help="Optional packs (e.g. styles)")
    p.add_argument("--project", type=Path, default=None, help="Install into a specific project directory")
    p.add_argument("--copy", action="store_true", help="Copy files instead of symlinks/junctions")
    ns = p.parse_args(argv)

    res = install_skills(
        agent=ns.agent,
        targets=ns.targets,
        packs=ns.packs,
        project_dir=ns.project,
        copy_mode=ns.copy,
    )
    print(f"Installed {res['installed_count']} skill links. Pointer: {res['pointer_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
