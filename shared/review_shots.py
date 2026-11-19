"""Deterministic headless multiview Cycles review rendering with automatic framing."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from shared.scene_inspector import inspect_scene


def configure_cycles_device(scene, device: str = "auto") -> str:
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
            except Exception:
                continue

    if device == "gpu":
        raise RuntimeError("Requested --device gpu, but no Cycles GPU backend is available.")
    scene.cycles.device = "CPU"
    return "CPU"


def _look_at(obj, target) -> None:
    from mathutils import Vector

    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _ensure_camera(scene):
    import bpy

    if scene.camera is None:
        cam_data = bpy.data.cameras.new("QA_Camera")
        cam_obj = bpy.data.objects.new("QA_Camera", cam_data)
        scene.collection.objects.link(cam_obj)
        scene.camera = cam_obj
    return scene.camera


def _ensure_lighting(scene, center, radius: float) -> None:
    import bpy

    if any(o.type == "LIGHT" for o in scene.objects):
        return
    placements = [
        ("QA_Key", (1.5, -1.5, 1.8), 900.0),
        ("QA_Fill", (-1.5, -0.7, 1.0), 500.0),
        ("QA_Rim", (0.3, 1.8, 1.4), 700.0),
    ]
    for name, direction, energy in placements:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = max(1.0, radius)
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = tuple(center[i] + direction[i] * radius for i in range(3))
        _look_at(obj, center)


def _configure_view(camera, view: str, center: list[float], radius: float) -> None:
    cx, cy, cz = center
    d = max(radius * 2.8, 2.0)
    camera.data.type = "PERSP"

    if view == "hero":
        camera.location = (cx + d, cy - d, cz + d * 0.65)
        camera.data.lens = 55
    elif view == "front":
        camera.location = (cx, cy - d, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * 2.4
    elif view == "rear":
        camera.location = (cx, cy + d, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * 2.4
    elif view == "side":
        camera.location = (cx + d, cy, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * 2.4
    elif view == "top":
        camera.location = (cx, cy, cz + d)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * 2.4
    else:
        raise ValueError(f"Unknown review view '{view}'")
    _look_at(camera, center)


def run(
    out_dir: str = "review",
    device: str = "auto",
    resolution: int = 512,
    samples: int = 16,
    views: list[str] | None = None,
) -> dict:
    import bpy

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    inventory = inspect_scene()
    if not inventory["bounds"]:
        raise ValueError("Cannot render review sheet: scene has no mesh bounds")

    active_device = configure_cycles_device(scene, device=device)
    scene.cycles.samples = samples
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    bounds = inventory["bounds"]
    center = bounds["center"]
    radius = max(max(bounds["size"]) * 0.6, 0.5)
    camera = _ensure_camera(scene)
    _ensure_lighting(scene, center, radius)

    requested = views or ["hero", "front", "side", "top"]
    artifacts: dict[str, str] = {}
    for view in requested:
        _configure_view(camera, view, center, radius)
        out_file = out_path / f"review_{view}.png"
        scene.render.filepath = str(out_file)
        bpy.ops.render.render(write_still=True)
        artifacts[view] = str(out_file)

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "device": active_device,
        "inventory": inventory,
        "artifacts": artifacts,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="review")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--resolution", type=int, default=512)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--views", default="hero,front,side,top")
    ns = p.parse_args(argv)
    views = [v.strip() for v in ns.views.split(",") if v.strip()]
    return run(
        out_dir=ns.out,
        device=ns.device,
        resolution=ns.resolution,
        samples=ns.samples,
        views=views,
    )
