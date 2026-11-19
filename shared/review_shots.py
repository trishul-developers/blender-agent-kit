"""Deterministic multiview, tactical-range, damage, collision, and silhouette review rendering."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from shared.profile_loader import load_project_profile
from shared.scene_inspector import inspect_objects, inspect_scene, lod_index


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


def _configure_range(
    camera,
    center: list[float],
    distance_m: float,
    azimuth_deg: float,
    elevation_deg: float,
    lens_mm: float,
) -> None:
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    horizontal = distance_m * math.cos(el)
    offset = (
        horizontal * math.sin(az),
        -horizontal * math.cos(az),
        distance_m * math.sin(el),
    )
    camera.data.type = "PERSP"
    camera.data.lens = lens_mm
    camera.location = tuple(center[i] + offset[i] for i in range(3))
    _look_at(camera, center)


def _is_collision_name(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("COLLISION_") or "_COL_" in upper or upper.endswith("_COL")


def _is_wreck_object(obj) -> bool:
    candidates = [obj.name]
    parent = obj.parent
    while parent is not None:
        candidates.append(parent.name)
        parent = parent.parent
    candidates.extend(c.name for c in getattr(obj, "users_collection", []))
    return any("WRECK" in name.upper() for name in candidates)


def _visible_meshes(scene) -> list:
    return [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


def _set_mesh_visibility(
    scene,
    lod: int | None = None,
    damage_mode: str | None = None,
    damage_prefix: str = "Damage_",
    collision_only: bool = False,
) -> dict:
    saved = {o.name: bool(o.hide_render) for o in scene.objects if o.type == "MESH"}
    damage_targets = {
        o.name[len(damage_prefix):]
        for o in scene.objects
        if o.type == "MESH" and o.name.startswith(damage_prefix) and not _is_wreck_object(o)
    }
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        visible = True
        if collision_only:
            visible = _is_collision_name(obj.name)
        else:
            visible = not _is_collision_name(obj.name) and not _is_wreck_object(obj)
            if lod is not None:
                visible = visible and lod_index(obj) == lod
            if damage_mode == "intact" and obj.name.startswith(damage_prefix):
                visible = False
            elif damage_mode == "damage":
                if obj.name.startswith(damage_prefix):
                    visible = visible
                elif any(obj.name == tgt or obj.name.endswith("_" + tgt) for tgt in damage_targets):
                    visible = False
        obj.hide_render = not visible
    return saved


def _restore_visibility(scene, saved: dict) -> None:
    for obj in scene.objects:
        if obj.type == "MESH" and obj.name in saved:
            obj.hide_render = bool(saved[obj.name])


def _bounds_from_visible(scene) -> dict | None:
    meshes = _visible_meshes(scene)
    if not meshes:
        return None
    return inspect_objects(meshes)["bounds"]


def _render(scene, out_file: Path) -> None:
    import bpy

    scene.render.filepath = str(out_file)
    bpy.ops.render.render(write_still=True)


def _collision_material():
    import bpy

    mat = bpy.data.materials.get("QA_Collision_Outline")
    if mat is None:
        mat = bpy.data.materials.new("QA_Collision_Outline")
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        emission.inputs["Strength"].default_value = 1.0
        mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def _render_reference_silhouette(scene, camera, subject_bounds: dict, reference_fbx: str, out_file: Path) -> dict:
    import bpy

    before = set(scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(Path(reference_fbx).resolve()))
    imported = [o for o in scene.objects if o not in before]
    for obj in imported:
        if obj.type == "MESH" and (
            obj.name.startswith("Damage_") or _is_collision_name(obj.name) or _is_wreck_object(obj)
        ):
            obj.hide_render = True
    imported_meshes = [o for o in imported if o.type == "MESH" and not o.hide_render]
    if not imported_meshes:
        raise ValueError(f"Reference FBX imported no meshes: {reference_fbx}")

    ref_bounds = inspect_objects(imported_meshes)["bounds"]
    gap = max(subject_bounds["size"][1], ref_bounds["size"][1]) * 0.15 + 0.5
    shift_y = subject_bounds["max"][1] + gap - ref_bounds["min"][1]
    roots = [o for o in imported if o.parent not in imported]
    for root in roots:
        root.location.y += shift_y
    bpy.context.view_layer.update()

    combined_meshes = _visible_meshes(scene)
    combined_bounds = inspect_objects(combined_meshes)["bounds"]
    center = combined_bounds["center"]
    radius = max(max(combined_bounds["size"]) * 0.6, 0.5)
    _configure_view(camera, "side", center, radius)
    _render(scene, out_file)

    for obj in imported:
        obj_type = obj.type
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            collection = getattr(bpy.data, f"{obj_type.lower()}s", None)
            if collection is not None:
                try:
                    collection.remove(data)
                except Exception:
                    pass
    return {"reference": str(Path(reference_fbx).resolve()), "path": str(out_file)}


def run(
    out_dir: str = "review",
    device: str = "auto",
    resolution: int = 512,
    width: int | None = None,
    height: int | None = None,
    samples: int = 16,
    views: list[str] | None = None,
    project_profile: str | None = None,
    preset: str | None = None,
    reference_fbx: str | None = None,
) -> dict:
    import bpy

    project_data, _ = load_project_profile(project_profile) if project_profile else (None, None)
    preset_cfg = {}
    if project_data and preset:
        preset_cfg = dict(project_data.get("review_presets", {}).get(preset, {}))
        if not preset_cfg:
            raise KeyError(f"Review preset '{preset}' not found in project profile '{project_data['name']}'")

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    inventory = inspect_scene(damage_prefix=preset_cfg.get("damage_prefix"))
    if not inventory["bounds"]:
        raise ValueError("Cannot render review sheet: scene has no mesh bounds")

    active_device = configure_cycles_device(scene, device=device)
    scene.cycles.samples = samples
    size = preset_cfg.get("resolution", [width or resolution, height or resolution])
    render_w = int(width or size[0])
    render_h = int(height or size[1])
    scene.render.resolution_x = render_w
    scene.render.resolution_y = render_h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    base_bounds = inventory["bounds"]
    center = base_bounds["center"]
    radius = max(max(base_bounds["size"]) * 0.6, 0.5)
    camera = _ensure_camera(scene)
    _ensure_lighting(scene, center, radius)
    damage_prefix = str(preset_cfg.get("damage_prefix", "Damage_"))

    artifacts: dict[str, object] = {}
    requested = views or list(preset_cfg.get("orthographic_views", ["hero", "front", "side", "top"]))
    saved = _set_mesh_visibility(scene, lod=int(preset_cfg.get("primary_lod", 0)), damage_mode="intact", damage_prefix=damage_prefix)
    try:
        bounds = _bounds_from_visible(scene) or base_bounds
        c = bounds["center"]
        r = max(max(bounds["size"]) * 0.6, 0.5)
        for view in requested:
            _configure_view(camera, view, c, r)
            out_file = out_path / f"review_{view}.png"
            _render(scene, out_file)
            artifacts[view] = str(out_file)
    finally:
        _restore_visibility(scene, saved)

    closeup_distance = preset_cfg.get("closeup_distance_m")
    if closeup_distance is not None:
        primary_lod = int(preset_cfg.get("primary_lod", 0))
        saved = _set_mesh_visibility(scene, lod=primary_lod, damage_mode="intact", damage_prefix=damage_prefix)
        try:
            bounds = _bounds_from_visible(scene)
            if bounds:
                _configure_range(
                    camera,
                    bounds["center"],
                    float(closeup_distance),
                    float(preset_cfg.get("azimuth_deg", 45.0)),
                    float(preset_cfg.get("elevation_deg", 45.0)),
                    float(preset_cfg.get("lens_mm", 50.0)),
                )
                out_file = out_path / "review_closeup.png"
                _render(scene, out_file)
                artifacts["closeup"] = {
                    "lod": primary_lod,
                    "distance_m": float(closeup_distance),
                    "path": str(out_file),
                }
        finally:
            _restore_visibility(scene, saved)

    ranges = [float(v) for v in preset_cfg.get("range_shots_m", [])]
    lods = [int(v) for v in preset_cfg.get("lods", [0])]
    if ranges:
        range_artifacts: list[dict] = []
        for lod in lods:
            saved = _set_mesh_visibility(scene, lod=lod, damage_mode="intact", damage_prefix=damage_prefix)
            try:
                bounds = _bounds_from_visible(scene)
                if not bounds:
                    continue
                for distance in ranges:
                    _configure_range(
                        camera,
                        bounds["center"],
                        distance,
                        float(preset_cfg.get("azimuth_deg", 45.0)),
                        float(preset_cfg.get("elevation_deg", 45.0)),
                        float(preset_cfg.get("lens_mm", 50.0)),
                    )
                    label = f"lod{lod}_{int(distance)}m"
                    out_file = out_path / f"review_{label}.png"
                    _render(scene, out_file)
                    range_artifacts.append({"lod": lod, "distance_m": distance, "path": str(out_file)})
            finally:
                _restore_visibility(scene, saved)
        artifacts["ranges"] = range_artifacts

    if preset_cfg.get("damage_views", False):
        damage_artifacts: list[dict] = []
        for lod in [int(v) for v in preset_cfg.get("damage_lods", [0, 1])]:
            saved = _set_mesh_visibility(scene, lod=lod, damage_mode="damage", damage_prefix=damage_prefix)
            try:
                bounds = _bounds_from_visible(scene)
                if not bounds:
                    continue
                r = max(max(bounds["size"]) * 0.6, 0.5)
                _configure_view(camera, "hero", bounds["center"], r)
                out_file = out_path / f"review_lod{lod}_damage.png"
                _render(scene, out_file)
                damage_artifacts.append({"lod": lod, "path": str(out_file)})
            finally:
                _restore_visibility(scene, saved)
        artifacts["damage"] = damage_artifacts

    if preset_cfg.get("collision_view", False):
        saved = _set_mesh_visibility(scene, collision_only=True)
        old_override = scene.view_layers[0].material_override
        old_freestyle = getattr(scene.render, "use_freestyle", False)
        try:
            bounds = _bounds_from_visible(scene)
            if bounds:
                scene.view_layers[0].material_override = _collision_material()
                if hasattr(scene.render, "use_freestyle"):
                    scene.render.use_freestyle = True
                r = max(max(bounds["size"]) * 0.6, 0.5)
                _configure_view(camera, "hero", bounds["center"], r)
                out_file = out_path / "review_collision_outline.png"
                _render(scene, out_file)
                artifacts["collision"] = str(out_file)
        finally:
            scene.view_layers[0].material_override = old_override
            if hasattr(scene.render, "use_freestyle"):
                scene.render.use_freestyle = old_freestyle
            _restore_visibility(scene, saved)

    effective_reference = reference_fbx or preset_cfg.get("reference_fbx")
    if effective_reference:
        saved = _set_mesh_visibility(scene, lod=int(preset_cfg.get("primary_lod", 0)), damage_mode="intact", damage_prefix=damage_prefix)
        try:
            subject_bounds = _bounds_from_visible(scene)
            if subject_bounds:
                artifacts["silhouette_comparison"] = _render_reference_silhouette(
                    scene,
                    camera,
                    subject_bounds,
                    str(effective_reference),
                    out_path / "review_silhouette_comparison.png",
                )
        finally:
            _restore_visibility(scene, saved)

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "device": active_device,
        "resolution": [render_w, render_h],
        "project_profile": project_data["name"] if project_data else None,
        "preset": preset,
        "inventory": inventory,
        "artifacts": artifacts,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="review")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--resolution", type=int, default=512)
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--views", default=None)
    p.add_argument("--project-profile", default=None)
    p.add_argument("--preset", default=None)
    p.add_argument("--reference-fbx", default=None)
    ns = p.parse_args(argv)
    views = [v.strip() for v in ns.views.split(",") if v.strip()] if ns.views else None
    return run(
        out_dir=ns.out,
        device=ns.device,
        resolution=ns.resolution,
        width=ns.width,
        height=ns.height,
        samples=ns.samples,
        views=views,
        project_profile=ns.project_profile,
        preset=ns.preset,
        reference_fbx=ns.reference_fbx,
    )
