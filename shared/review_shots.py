"""Deterministic multiview, tactical-range, damage, collision, and silhouette review rendering."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from shared.profile_loader import load_profiled_target
from shared.scene_inspector import collider_patterns_from_naming, inspect_objects, inspect_scene, is_collider_name, lod_index
from shared.target_loader import deep_merge_dict


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


def configure_review_engine(scene, engine: str, device: str = "auto") -> str:
    """Configure the renderer declared by the resolved review style."""
    if engine == "CYCLES":
        return configure_cycles_device(scene, device=device)
    if engine == "BLENDER_EEVEE":
        scene.render.engine = "BLENDER_EEVEE"
        return "EEVEE_NEXT"
    raise ValueError(f"Unsupported review engine '{engine}'")


def _configure_world(scene, style_cfg: dict) -> None:
    import bpy

    color = [float(v) for v in style_cfg.get("background_color", [0.05, 0.05, 0.05, 1.0])]
    strength = float(style_cfg.get("background_strength", 1.0))
    if scene.world is None:
        scene.world = bpy.data.worlds.new("QA_Review_World")
    scene.world.color = tuple(color[:3])
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    background = nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = tuple(color)
        background.inputs["Strength"].default_value = strength


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


def _review_light_scale(radius: float, reference_radius: float = 2.5) -> float:
    """Scale light power with squared subject radius to preserve approximate illuminance."""
    safe_radius = max(float(radius), 0.5)
    return (safe_radius / reference_radius) ** 2


def _ensure_lighting(
    scene,
    center,
    radius: float,
    lighting_cfg: dict | None = None,
) -> None:
    import bpy

    cfg = dict(lighting_cfg or {})
    use_authored = bool(cfg.get("use_authored_lights", True))
    authored = [o for o in scene.objects if o.type == "LIGHT" and not o.hide_render]
    if use_authored and authored:
        return
    if not use_authored:
        for obj in authored:
            obj.hide_render = True

    reference_radius = float(cfg.get("reference_radius_m", 2.5))
    scale = _review_light_scale(radius, reference_radius=reference_radius)
    placements = cfg.get("lights") or [
        {"name": "QA_Key", "direction": [1.5, -1.5, 1.8], "energy": 900.0},
        {"name": "QA_Fill", "direction": [-1.5, -0.7, 1.0], "energy": 500.0},
        {"name": "QA_Rim", "direction": [0.3, 1.8, 1.4], "energy": 700.0},
    ]
    area_factor = float(cfg.get("area_size_factor", 0.8))
    min_area = float(cfg.get("min_area_size_m", 0.25))
    for item in placements:
        name = str(item["name"])
        direction = [float(v) for v in item["direction"]]
        base_energy = float(item["energy"])
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = base_energy * scale
        data.shape = "DISK"
        data.size = max(min_area, radius * area_factor)
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = tuple(center[i] + direction[i] * radius for i in range(3))
        _look_at(obj, center)


def _configure_view(
    camera,
    view: str,
    center: list[float],
    radius: float,
    style_cfg: dict | None = None,
) -> None:
    cfg = style_cfg or {}
    cx, cy, cz = center
    d = max(
        radius * float(cfg.get("hero_distance_factor", 2.8)),
        float(cfg.get("hero_min_distance_m", 2.0)),
    )
    height_factor = float(cfg.get("hero_height_factor", 0.65))
    hero_lens = float(cfg.get("hero_lens_mm", 55.0))
    ortho_factor = float(cfg.get("ortho_scale_factor", 2.4))
    camera.data.type = "PERSP"

    if view == "hero":
        camera.location = (cx + d, cy - d, cz + d * height_factor)
        camera.data.lens = hero_lens
    elif view == "front":
        camera.location = (cx, cy - d, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * ortho_factor
    elif view == "rear":
        camera.location = (cx, cy + d, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * ortho_factor
    elif view == "side":
        camera.location = (cx + d, cy, cz)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * ortho_factor
    elif view == "top":
        camera.location = (cx, cy, cz + d)
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = radius * ortho_factor
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


def _hierarchy_names(obj) -> list[str]:
    names = [obj.name]
    parent = obj.parent
    while parent is not None:
        names.append(parent.name)
        parent = parent.parent
    names.extend(c.name for c in getattr(obj, "users_collection", []))
    return names


def _matches_hierarchy_patterns(obj, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    import fnmatch
    return any(
        fnmatch.fnmatchcase(name, pattern)
        for name in _hierarchy_names(obj)
        for pattern in patterns
    )


def _visible_meshes(scene) -> list:
    return [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


def _set_mesh_visibility(
    scene,
    lod: int | None = None,
    damage_mode: str | None = None,
    damage_prefix: str = "Damage_",
    collision_only: bool = False,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    lod_pattern: str | None = None,
    collider_pattern: str | None = None,
) -> dict:
    saved = {o.name: bool(o.hide_render) for o in scene.objects if o.type == "MESH"}
    damage_targets = {
        o.name[len(damage_prefix):]
        for o in scene.objects
        if o.type == "MESH"
        and bool(damage_prefix)
        and o.name.startswith(damage_prefix)
        and not _matches_hierarchy_patterns(o, exclude_patterns)
    }
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        if collision_only:
            visible = is_collider_name(obj.name, collider_pattern)
        else:
            visible = not is_collider_name(obj.name, collider_pattern)
            if include_patterns:
                visible = visible and _matches_hierarchy_patterns(obj, include_patterns)
            if exclude_patterns:
                visible = visible and not _matches_hierarchy_patterns(obj, exclude_patterns)
            if lod is not None:
                visible = visible and lod_index(obj, lod_pattern) == lod
            if damage_mode == "intact" and damage_prefix and obj.name.startswith(damage_prefix):
                visible = False
            elif damage_mode == "damage":
                if damage_prefix and obj.name.startswith(damage_prefix):
                    visible = visible
                elif any(obj.name == tgt or obj.name.endswith("_" + tgt) for tgt in damage_targets):
                    visible = False
        obj.hide_render = not visible
    return saved


def _restore_visibility(scene, saved: dict) -> None:
    for obj in scene.objects:
        if obj.type == "MESH" and obj.name in saved:
            obj.hide_render = bool(saved[obj.name])


def _bounds_from_visible(
    scene,
    lod_pattern: str | None = None,
    collider_patterns: str | list[str] | None = None,
) -> dict | None:
    meshes = _visible_meshes(scene)
    if not meshes:
        return None
    return inspect_objects(
        meshes,
        lod_pattern=lod_pattern,
        collider_patterns=collider_patterns,
    )["bounds"]


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


def _set_collision_overlay_visibility(
    scene,
    lod: int | None,
    damage_prefix: str = "Damage_",
    exclude_patterns: list[str] | None = None,
    lod_pattern: str | None = None,
    collider_pattern: str | None = None,
) -> dict:
    """Show collision meshes together with the intact primary LOD for review."""
    saved = {o.name: bool(o.hide_render) for o in scene.objects if o.type == "MESH"}
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        if is_collider_name(obj.name, collider_pattern):
            visible = True
        else:
            visible = not _matches_hierarchy_patterns(obj, exclude_patterns)
            if lod is not None:
                visible = visible and lod_index(obj, lod_pattern) == lod
            if damage_prefix and obj.name.startswith(damage_prefix):
                visible = False
        obj.hide_render = not visible
    return saved


def _prepare_collision_wireframe(
    scene,
    radius: float,
    collider_pattern: str | None = None,
) -> list[dict]:
    """Temporarily render visible collision meshes as emissive wireframe overlays."""
    material = _collision_material()
    state: list[dict] = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render or not is_collider_name(obj.name, collider_pattern):
            continue
        original_materials = [m for m in obj.data.materials]
        obj.data.materials.clear()
        obj.data.materials.append(material)
        modifier = obj.modifiers.new(name="QA_Collision_Wireframe", type="WIREFRAME")
        modifier.thickness = max(0.001, float(radius) * 0.004)
        modifier.use_even_offset = True
        modifier.use_replace = True
        state.append({
            "object": obj,
            "modifier": modifier,
            "materials": original_materials,
        })
    return state


def _restore_collision_wireframe(state: list[dict]) -> None:
    for item in state:
        obj = item["object"]
        modifier = item["modifier"]
        if obj is None:
            continue
        try:
            obj.modifiers.remove(modifier)
        except (ReferenceError, RuntimeError):
            pass
        obj.data.materials.clear()
        for material in item["materials"]:
            if material is not None:
                obj.data.materials.append(material)


def _remove_imported_objects(imported: list) -> None:
    import bpy

    for obj in imported:
        obj_type = obj.type
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            collection_name = {
                "MESH": "meshes",
                "CURVE": "curves",
                "SURFACE": "curves",
                "FONT": "curves",
                "META": "metaballs",
                "ARMATURE": "armatures",
                "CAMERA": "cameras",
                "LIGHT": "lights",
            }.get(obj_type)
            collection = getattr(bpy.data, collection_name, None) if collection_name else None
            if collection is not None:
                try:
                    collection.remove(data)
                except Exception:
                    pass


def _render_reference_silhouette(
    scene,
    camera,
    subject_bounds: dict,
    reference_fbx: str,
    out_file: Path,
    damage_prefix: str = "Damage_",
    exclude_patterns: list[str] | None = None,
    collider_pattern: str | None = None,
    style_cfg: dict | None = None,
) -> dict:
    import bpy

    before = set(scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(Path(reference_fbx).resolve()))
    imported = [o for o in scene.objects if o not in before]
    for obj in imported:
        if obj.type == "MESH" and (
            obj.name.startswith(damage_prefix)
            or is_collider_name(obj.name, collider_pattern)
            or _matches_hierarchy_patterns(obj, exclude_patterns)
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
    _configure_view(camera, "side", center, radius, style_cfg)
    _render(scene, out_file)

    _remove_imported_objects(imported)
    return {"reference": str(Path(reference_fbx).resolve()), "path": str(out_file)}


def run(
    out_dir: str = "review",
    device: str = "auto",
    resolution: int | None = None,
    width: int | None = None,
    height: int | None = None,
    samples: int | None = None,
    views: list[str] | None = None,
    target: str = "unity",
    project_profile: str | None = None,
    preset: str | None = None,
    style: str | None = None,
    reference_fbx: str | None = None,
) -> dict:
    import bpy

    target_cfg, _, _, project_data, _ = load_profiled_target(
        target, project_profile=project_profile
    )
    naming = target_cfg.get("naming", {})
    lod_pattern = naming.get("lod_pattern")
    collider_pattern = collider_patterns_from_naming(naming)
    preset_cfg = {}
    if project_data and preset:
        preset_cfg = dict(project_data.get("review_presets", {}).get(preset, {}))
        if not preset_cfg:
            raise KeyError(f"Review preset '{preset}' not found in project profile '{project_data['name']}'")

    review_cfg = target_cfg.get("review", {})
    style_name = style or preset_cfg.get("style") or review_cfg.get("default_style")
    styles = review_cfg.get("styles", {})
    if not style_name or style_name not in styles:
        raise KeyError(
            f"Unknown review style '{style_name}'. Available: {sorted(styles)}"
        )
    style_cfg = dict(styles[style_name])
    effective_cfg = deep_merge_dict(style_cfg, preset_cfg)

    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    # Inventory uses the same resolved target/policy naming and LOD exclusions as QA.
    common = target_cfg.get("qa", {}).get("common", {})
    exclusions = set(common.get("lod_exclude_patterns", []))
    exclusions.update(effective_cfg.get("lod_exclude_patterns", []))
    inventory = inspect_scene(
        damage_prefix=effective_cfg.get("damage_prefix", common.get("damage_prefix")),
        lod_exclude_patterns=sorted(exclusions),
        lod_pattern=lod_pattern,
        collider_patterns=collider_pattern,
    )
    if not inventory["bounds"]:
        raise ValueError("Cannot render review sheet: scene has no mesh bounds")

    engine = str(effective_cfg.get("engine", "CYCLES"))
    active_device = configure_review_engine(scene, engine, device=device)
    effective_samples = int(samples if samples is not None else effective_cfg.get("samples", 16))
    if engine == "CYCLES":
        scene.cycles.samples = effective_samples
    size = effective_cfg.get("resolution", [512, 512])
    square = int(resolution) if resolution is not None else None
    render_w = int(width or square or size[0])
    render_h = int(height or square or size[1])
    scene.render.resolution_x = render_w
    scene.render.resolution_y = render_h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    _configure_world(scene, effective_cfg)

    base_bounds = inventory["bounds"]
    center = base_bounds["center"]
    radius = max(max(base_bounds["size"]) * 0.6, 0.5)
    camera = _ensure_camera(scene)
    _ensure_lighting(scene, center, radius, effective_cfg.get("lighting"))
    damage_prefix = str(effective_cfg.get("damage_prefix", common.get("damage_prefix", "Damage_")))
    exclude_patterns = [str(v) for v in effective_cfg.get("exclude_patterns", [])]
    reference_exclude_patterns = [
        str(v) for v in effective_cfg.get("reference_exclude_patterns", exclude_patterns)
    ]

    artifacts: dict[str, object] = {}
    requested = views or list(effective_cfg.get("orthographic_views", ["hero", "front", "side", "top"]))
    saved = _set_mesh_visibility(
        scene,
        lod=int(effective_cfg.get("primary_lod", 0)),
        damage_mode="intact",
        damage_prefix=damage_prefix,
        exclude_patterns=exclude_patterns,
        lod_pattern=lod_pattern,
        collider_pattern=collider_pattern,
    )
    try:
        bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern) or base_bounds
        c = bounds["center"]
        r = max(max(bounds["size"]) * 0.6, 0.5)
        for view in requested:
            _configure_view(camera, view, c, r, effective_cfg)
            out_file = out_path / f"review_{view}.png"
            _render(scene, out_file)
            artifacts[view] = str(out_file)
    finally:
        _restore_visibility(scene, saved)

    closeup_distance = effective_cfg.get("closeup_distance_m")
    if closeup_distance is not None:
        primary_lod = int(effective_cfg.get("primary_lod", 0))
        saved = _set_mesh_visibility(
            scene,
            lod=primary_lod,
            damage_mode="intact",
            damage_prefix=damage_prefix,
            exclude_patterns=exclude_patterns,
            lod_pattern=lod_pattern,
            collider_pattern=collider_pattern,
        )
        try:
            bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
            if bounds:
                _configure_range(
                    camera,
                    bounds["center"],
                    float(closeup_distance),
                    float(effective_cfg.get("azimuth_deg", 45.0)),
                    float(effective_cfg.get("elevation_deg", 45.0)),
                    float(effective_cfg.get("lens_mm", effective_cfg.get("hero_lens_mm", 50.0))),
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

    ranges = [float(v) for v in effective_cfg.get("range_shots_m", [])]
    lods = [int(v) for v in effective_cfg.get("lods", [0])]
    if ranges:
        range_artifacts: list[dict] = []
        for lod in lods:
            saved = _set_mesh_visibility(
                scene,
                lod=lod,
                damage_mode="intact",
                damage_prefix=damage_prefix,
                exclude_patterns=exclude_patterns,
                lod_pattern=lod_pattern,
                collider_pattern=collider_pattern,
            )
            try:
                bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
                if not bounds:
                    continue
                for distance in ranges:
                    _configure_range(
                        camera,
                        bounds["center"],
                        distance,
                        float(effective_cfg.get("azimuth_deg", 45.0)),
                        float(effective_cfg.get("elevation_deg", 45.0)),
                        float(effective_cfg.get("lens_mm", effective_cfg.get("hero_lens_mm", 50.0))),
                    )
                    label = f"lod{lod}_{int(distance)}m"
                    out_file = out_path / f"review_{label}.png"
                    _render(scene, out_file)
                    range_artifacts.append({"lod": lod, "distance_m": distance, "path": str(out_file)})
            finally:
                _restore_visibility(scene, saved)
        artifacts["ranges"] = range_artifacts

    if effective_cfg.get("damage_views", False):
        damage_artifacts: list[dict] = []
        for lod in [int(v) for v in effective_cfg.get("damage_lods", [0, 1])]:
            saved = _set_mesh_visibility(
                scene,
                lod=lod,
                damage_mode="damage",
                damage_prefix=damage_prefix,
                exclude_patterns=exclude_patterns,
                lod_pattern=lod_pattern,
                collider_pattern=collider_pattern,
            )
            try:
                bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
                if not bounds:
                    continue
                r = max(max(bounds["size"]) * 0.6, 0.5)
                _configure_view(camera, "hero", bounds["center"], r, effective_cfg)
                out_file = out_path / f"review_lod{lod}_damage.png"
                _render(scene, out_file)
                damage_artifacts.append({"lod": lod, "path": str(out_file)})
            finally:
                _restore_visibility(scene, saved)
        artifacts["damage"] = damage_artifacts

    variant_artifacts: list[dict] = []
    for variant in effective_cfg.get("variant_views", []):
        variant_id = str(variant.get("id", "variant"))
        include = [str(v) for v in variant.get("include_patterns", [])]
        if not include:
            raise ValueError(f"Review variant '{variant_id}' requires include_patterns")
        variant_exclude = [str(v) for v in variant.get("exclude_patterns", [])]
        variant_lod = variant.get("lod")
        saved = _set_mesh_visibility(
            scene,
            lod=int(variant_lod) if variant_lod is not None else None,
            damage_prefix=damage_prefix,
            include_patterns=include,
            exclude_patterns=variant_exclude,
            lod_pattern=lod_pattern,
            collider_pattern=collider_pattern,
        )
        try:
            bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
            if not bounds:
                raise ValueError(
                    f"Review variant '{variant_id}' matched no visible meshes; patterns={include}"
                )
            view = str(variant.get("view", "hero"))
            r = max(max(bounds["size"]) * 0.6, 0.5)
            _configure_view(camera, view, bounds["center"], r, effective_cfg)
            out_file = out_path / f"review_{variant_id}.png"
            _render(scene, out_file)
            variant_artifacts.append({
                "id": variant_id,
                "lod": int(variant_lod) if variant_lod is not None else None,
                "include_patterns": include,
                "path": str(out_file),
            })
        finally:
            _restore_visibility(scene, saved)
    if variant_artifacts:
        artifacts["variants"] = variant_artifacts

    if effective_cfg.get("collision_view", False):
        saved = _set_collision_overlay_visibility(
            scene,
            lod=int(effective_cfg.get("primary_lod", 0)),
            damage_prefix=damage_prefix,
            exclude_patterns=exclude_patterns,
            lod_pattern=lod_pattern,
            collider_pattern=collider_pattern,
        )
        wireframe_state: list[dict] = []
        try:
            bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
            if bounds:
                r = max(max(bounds["size"]) * 0.6, 0.5)
                wireframe_state = _prepare_collision_wireframe(
                    scene, r, collider_pattern=collider_pattern
                )
                if wireframe_state:
                    _configure_view(camera, "hero", bounds["center"], r, effective_cfg)
                    out_file = out_path / "review_collision_outline.png"
                    _render(scene, out_file)
                    artifacts["collision"] = str(out_file)
        finally:
            _restore_collision_wireframe(wireframe_state)
            _restore_visibility(scene, saved)

    effective_reference = reference_fbx or effective_cfg.get("reference_fbx")
    if effective_reference:
        saved = _set_mesh_visibility(
            scene,
            lod=int(effective_cfg.get("primary_lod", 0)),
            damage_mode="intact",
            damage_prefix=damage_prefix,
            exclude_patterns=exclude_patterns,
            lod_pattern=lod_pattern,
            collider_pattern=collider_pattern,
        )
        try:
            subject_bounds = _bounds_from_visible(scene, lod_pattern, collider_pattern)
            if subject_bounds:
                artifacts["silhouette_comparison"] = _render_reference_silhouette(
                    scene,
                    camera,
                    subject_bounds,
                    str(effective_reference),
                    out_path / "review_silhouette_comparison.png",
                    damage_prefix=damage_prefix,
                    exclude_patterns=reference_exclude_patterns,
                    collider_pattern=collider_pattern,
                    style_cfg=effective_cfg,
                )
        finally:
            _restore_visibility(scene, saved)

    return {
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "device": active_device,
        "render_engine": engine,
        "samples": effective_samples,
        "resolution": [render_w, render_h],
        "style": style_name,
        "review_settings": effective_cfg,
        "target": target_cfg["name"],
        "policy": target_cfg.get("default_policy"),
        "project_profile": project_data["name"] if project_data else None,
        "preset": preset,
        "inventory": inventory,
        "artifacts": artifacts,
    }


def cli_main(argv: list[str]) -> dict:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="review")
    p.add_argument("--device", choices=["auto", "gpu", "cpu"], default="auto")
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--views", default=None)
    p.add_argument("--target", default="unity")
    p.add_argument("--project-profile", default=None)
    p.add_argument("--preset", default=None)
    p.add_argument("--style", default=None)
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
        target=ns.target,
        project_profile=ns.project_profile,
        preset=ns.preset,
        style=ns.style,
        reference_fbx=ns.reference_fbx,
    )
