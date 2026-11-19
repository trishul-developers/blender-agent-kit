"""Headless multiview Cycles render helper with --device auto|gpu|cpu fallback."""
from __future__ import annotations

import argparse
from pathlib import Path


def configure_cycles_device(scene, device: str = "auto") -> str:
    """Configure Cycles compute device; auto uses GPU locally and falls back to CPU in headless CI."""
    import bpy

    scene.render.engine = "CYCLES"
    if device == "cpu":
        scene.cycles.device = "CPU"
        return "CPU"

    prefs = bpy.context.preferences.addons.get("cycles")
    if prefs is not None:
        cp = prefs.preferences
        for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
            try:
                cp.compute_device_type = backend
                cp.get_devices()
                gpu_devs = [d for d in cp.devices if d.type == backend]
                if gpu_devs:
                    for d in cp.devices:
                        d.use = d.type == backend
                    scene.cycles.device = "GPU"
                    return f"GPU:{backend}"
            except Exception:  # noqa: BLE001
                continue

    if device == "gpu":
        raise RuntimeError("Requested --device gpu, but no Cycles GPU backend is available.")
    scene.cycles.device = "CPU"
    return "CPU"


def run(out_dir: str = "review", device: str = "auto", resolution: int = 512, samples: int = 16) -> dict:
    """Render a quick studio preview still via Cycles for visual QA."""
    import bpy

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    active_device = configure_cycles_device(scene, device=device)
    scene.cycles.samples = samples
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = "PNG"

    if scene.camera is None:
        cam_data = bpy.data.cameras.new("QA_Camera")
        cam_obj = bpy.data.objects.new("QA_Camera", cam_data)
        scene.collection.objects.link(cam_obj)
        cam_obj.location = (3.0, -3.0, 2.2)
        cam_obj.rotation_euler = (1.1, 0.0, 0.785)
        scene.camera = cam_obj

    out_file = out_path / "review_hero.png"
    scene.render.filepath = str(out_file)
    bpy.ops.render.render(write_still=True)

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "device": active_device,
        "artifacts": {"hero": str(out_file)},
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="review")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--resolution", type=int, default=512)
    p.add_argument("--samples", type=int, default=16)
    ns = p.parse_args(argv)
    return run(out_dir=ns.out, device=ns.device, resolution=ns.resolution, samples=ns.samples)
