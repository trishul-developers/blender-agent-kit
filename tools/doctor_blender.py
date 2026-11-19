"""Blender-side doctor probe: checks version, bundled add-ons, GPU/CPU Cycles, and save/reopen."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from shared.review_shots import configure_cycles_device


def run(device: str = "auto") -> dict:
    import bpy

    version_tuple = tuple(bpy.app.version)
    version_ok = version_tuple >= (5, 2, 0)

    # Dynamically verify built-in/extension add-on availability without hardcoding legacy flags
    verified_addons = sorted(
        a.module for a in bpy.context.preferences.addons
        if any(k in a.module for k in ("fbx", "gltf", "rigify", "cycles"))
    )

    cycles_device = configure_cycles_device(bpy.context.scene, device=device)

    # Save & reopen tiny smoke test
    with tempfile.TemporaryDirectory(prefix="bak_doctor_") as tmp:
        blend_path = Path(tmp) / "smoke.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), copy=True)
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        smoke_ok = blend_path.is_file()

    return {
        "status": "ok" if smoke_ok else "error",
        "blender_version": bpy.app.version_string,
        "version_tuple": list(version_tuple),
        "meets_5_2_lts": version_ok,
        "build_hash": bpy.app.build_hash.decode("utf-8", errors="ignore")
        if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
        "cycles_device": cycles_device,
        "addons": verified_addons,
        "smoke_save_reopen": smoke_ok,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    ns = p.parse_args(argv)
    return run(device=ns.device)
