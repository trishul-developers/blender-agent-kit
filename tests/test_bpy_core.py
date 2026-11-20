"""Tier 2 headless Blender tests for QA and hierarchy-safe semantic bundle export."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from shared.bundle_exporter import run as run_bundle
from shared.qa_checks import run as run_qa
from shared.review_shots import (
    _ensure_lighting,
    _matches_hierarchy_patterns,
    _prepare_collision_wireframe,
    _remove_imported_objects,
    _restore_collision_wireframe,
    _review_light_scale,
    _set_collision_overlay_visibility,
    _set_mesh_visibility,
)

DEFAULT_LOD_PATTERN = "{name}_LOD{index}"
DEFAULT_COLLIDER_PATTERN = "{name}_COL_{index:02d}"


def _ensure_uv(obj, second: bool = True):
    if len(obj.data.uv_layers) == 0:
        obj.data.uv_layers.new(name="UVMap")
    if second and len(obj.data.uv_layers) < 2:
        obj.data.uv_layers.new(name="LightmapUV")


def _make_compliant_cube(name: str = "Cube", location=(0.0, 0.0, 1.0), size: float = 2.0):
    import bpy

    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _ensure_uv(obj)
    return obj


def _link_empty(name: str, parent=None, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    import bpy

    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    obj.rotation_euler = rotation
    return obj


def run() -> dict:
    import bmesh
    import bpy

    passed = 0

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("SolidProp")
    res = run_qa(target="unity", asset_class="solid_prop")
    assert res["passed"], f"Expected compliant cube to pass: {res}"
    passed += 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    plane = bpy.context.object
    plane.name = "OpenSheet"
    _ensure_uv(plane, second=False)
    assert not run_qa(target="unity", asset_class="solid_prop")["passed"]
    assert run_qa(target="unity", asset_class="open_sheet")["passed"]
    passed += 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    empty = run_qa(target="unity", asset_class="open_sheet")
    assert not empty["passed"]
    assert any(e["code"] == "no_meshes" for e in empty["errors"])
    passed += 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = _make_compliant_cube("InsideOut")
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    inside = run_qa(target="unity", asset_class="solid_prop")
    assert not inside["passed"]
    assert any(e["code"] == "inward_normals" for e in inside["errors"]), inside
    passed += 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("Asset_LOD0")
    _make_compliant_cube("Asset_LOD1")
    lod = run_qa(target="unity", asset_class="open_sheet")
    assert not lod["passed"]
    assert any(e["code"].startswith("non_monotonic_lod") for e in lod["errors"]), lod
    passed += 1

    # Damage accounting and LOD leakage are profile-driven.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("Hull_LOD0")
    _make_compliant_cube("Damage_EngineDeck_LOD0", location=(0.0, 0.0, 3.0), size=0.5)
    _make_compliant_cube("Hull_LOD2", size=0.5)
    _make_compliant_cube("Damage_Track_L_LOD2", location=(0.0, 0.0, 2.0), size=0.25)
    with tempfile.TemporaryDirectory(prefix="bak_profile_") as tmp:
        profile_path = Path(tmp) / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "qa-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "qa": {
                        "common": {
                            "damage_prefix": "Damage_",
                            "damage_allowed_lods": [0, 1],
                            "require_monotonic_lod_tris": False
                        },
                        "asset_classes": {
                            "damage_test": {
                                "reject_boundary_edges": False,
                                "require_non_overlapping_uv1": False,
                                "max_tris": {"lod0": 1000, "lod2": 1000}
                            }
                        }
                    }
                }
            }
        }), encoding="utf-8")
        damage = run_qa(target="unity", asset_class="damage_test", project_profile=str(profile_path))
        assert any(e["code"] == "damage_lod_leak" for e in damage["errors"]), damage
        assert damage["inventory"]["lods"]["0"]["damage_tri_count"] > 0
    passed += 1

    # Symmetry bounds check catches asymmetric L/R geometry.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    left = _link_empty("Running_L")
    right = _link_empty("Running_R")
    lmesh = _make_compliant_cube("RoadWheel_L_01", location=(-1.0, 0.0, 1.0), size=1.0)
    lmesh.parent = left
    rmesh = _make_compliant_cube("RoadWheel_R_01", location=(1.4, 0.0, 1.0), size=1.0)
    rmesh.parent = right
    with tempfile.TemporaryDirectory(prefix="bak_profile_") as tmp:
        profile_path = Path(tmp) / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "symmetry-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "qa": {
                        "common": {"require_monotonic_lod_tris": False},
                        "asset_classes": {
                            "symmetry_test": {
                                "reject_boundary_edges": False,
                                "require_non_overlapping_uv1": False,
                                "mirror_symmetry": {
                                    "axis": "X",
                                    "left_token": "_L",
                                    "right_token": "_R",
                                    "include_patterns": ["Running_L"],
                                    "bounds_tolerance": 0.05
                                }
                            }
                        }
                    }
                }
            }
        }), encoding="utf-8")
        symmetry = run_qa(target="unity", asset_class="symmetry_test", project_profile=str(profile_path))
        assert any(e["code"] == "symmetry_bounds" for e in symmetry["errors"]), symmetry
    passed += 1

    # Dimension boxes can explicitly target LOD0 and exclude wreck geometry.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("Hull_LOD0", size=2.0)
    _make_compliant_cube("Hull_LOD1", location=(0.0, 0.0, 2.0), size=8.0)
    _make_compliant_cube("Wreck_Hull_LOD0", location=(0.0, 0.0, 4.0), size=10.0)
    with tempfile.TemporaryDirectory(prefix="bak_profile_") as tmp:
        profile_path = Path(tmp) / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "dimension-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "qa": {
                        "common": {"require_monotonic_lod_tris": False},
                        "asset_classes": {
                            "dimension_test": {
                                "reject_boundary_edges": False,
                                "require_non_overlapping_uv1": False,
                                "dimension_boxes": [{
                                    "id": "lod0_hull",
                                    "include_patterns": ["*Hull*"],
                                    "exclude_patterns": ["Wreck*"],
                                    "lods": [0],
                                    "expected_size": {"X": 2.0, "Y": 2.0, "Z": 2.0},
                                    "tolerance": 0.001
                                }]
                            }
                        }
                    }
                }
            }
        }), encoding="utf-8")
        dimension = run_qa(target="unity", asset_class="dimension_test", project_profile=str(profile_path))
        assert dimension["passed"], dimension
        assert dimension["evidence"]["dimensions"][0]["matched_objects"] == ["Hull_LOD0"], dimension
    passed += 1

    # LOD-suffixed authoring names are stripped only during export and all
    # selected/unselected names are restored after the FBX is written.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    base_root = _link_empty("Vehicle_Station")
    base_turret = _link_empty("Turret_Pivot")
    base_gun = _link_empty("Gun_Elevation_Pivot")
    base_socket = _link_empty("Socket_Sight")

    lod_root = _link_empty("Vehicle_Station_LOD1", location=(0.0, -0.04, 1.64))
    lod_turret = _link_empty("Turret_Pivot_LOD1", parent=lod_root)
    lod_gun = _link_empty("Gun_Elevation_Pivot_LOD1", parent=lod_turret, location=(0.0, -0.5, 0.3))
    lod_socket = _link_empty(
        "Socket_Sight_LOD1",
        parent=lod_turret,
        location=(0.65, -0.25, 0.4),
        rotation=(0.1, -0.2, 0.25),
    )
    lod_mesh = _make_compliant_cube("Hull_LOD1", size=0.4)
    lod_mesh.parent = lod_root
    lod_mesh.location = (0.0, 0.0, 0.5)

    with tempfile.TemporaryDirectory(prefix="bak_lod_strip_") as tmp:
        root_dir = Path(tmp)
        profile_path = root_dir / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "lod-strip-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "export": {
                        "strip_lod_suffix_on_export": True,
                        "strip_lod_suffix_pattern": "_LOD[0-9]+$"
                    }
                }
            }
        }), encoding="utf-8")
        spec_path = root_dir / "bundle.json"
        spec_path.write_text(json.dumps({
            "schema_version": "1.0",
            "asset_id": "lod_strip",
            "parts": [{
                "id": "station_lod1",
                "role": "station",
                "lod": 1,
                "root": "Vehicle_Station_LOD1",
                "file": "lod_strip_Station_LOD1.fbx",
                "zero_root_location": True
            }]
        }), encoding="utf-8")

        restored = run_bundle(
            str(spec_path),
            target="unity",
            project_profile=str(profile_path),
            out_dir=str(root_dir / "out_restore"),
            verify_roundtrip=False,
        )
        assert restored["status"] == "ok", restored
        restored_part = restored["parts"][0]
        exported_names = {o["name"] for o in restored_part["inventory"]["objects"]}
        assert {"Vehicle_Station", "Turret_Pivot", "Gun_Elevation_Pivot", "Socket_Sight", "Hull"} <= exported_names, restored_part
        assert restored_part["export_root"] == "Vehicle_Station", restored_part

        # Original authoring names and the unselected colliding base names survive
        # the temporary rename context before any fresh-scene round-trip reset.
        assert lod_root.name == "Vehicle_Station_LOD1"
        assert lod_turret.name == "Turret_Pivot_LOD1"
        assert lod_gun.name == "Gun_Elevation_Pivot_LOD1"
        assert lod_socket.name == "Socket_Sight_LOD1"
        assert base_root.name == "Vehicle_Station"
        assert base_turret.name == "Turret_Pivot"
        assert base_gun.name == "Gun_Elevation_Pivot"
        assert base_socket.name == "Socket_Sight"

        stripped = run_bundle(
            str(spec_path),
            target="unity",
            project_profile=str(profile_path),
            out_dir=str(root_dir / "out_roundtrip"),
            verify_roundtrip=True,
        )
        assert stripped["status"] == "ok", stripped
        part = stripped["parts"][0]
        assert part["export_root"] == "Vehicle_Station", part
        assert part["roundtrip"]["passed"], part["roundtrip"]
    passed += 1

    # LOD exclusion is generic and hierarchy-aware; colliders are exempt from UV0.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("Body_LOD0", size=2.0)
    wreck_root = _link_empty("Variant_Destroyed_LOD0")
    wreck_mesh = _make_compliant_cube("DestroyedBody", location=(0.0, 0.0, 4.0), size=4.0)
    wreck_mesh.parent = wreck_root
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 1.0))
    collider = bpy.context.object
    collider.name = "Collision_Hull"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    with tempfile.TemporaryDirectory(prefix="bak_profile_") as tmp:
        profile_path = Path(tmp) / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "lod-exclude-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "qa": {
                        "common": {
                            "require_monotonic_lod_tris": False,
                            "lod_exclude_patterns": ["Variant_Destroyed*", "Collision_*"]
                        },
                        "asset_classes": {
                            "lod_exclude_test": {
                                "reject_boundary_edges": False,
                                "require_non_overlapping_uv1": False,
                                "max_tris": {"lod0": 20}
                            }
                        }
                    }
                }
            }
        }), encoding="utf-8")
        excluded = run_qa(
            target="unity",
            asset_class="lod_exclude_test",
            project_profile=str(profile_path),
        )
        assert excluded["passed"], excluded
        assert excluded["inventory"]["lods"]["0"]["tri_count"] == 12, excluded
        flags = {o["name"]: o["excluded_from_lod"] for o in excluded["inventory"]["objects"]}
        assert flags["DestroyedBody"] is True
        assert flags["Collision_Hull"] is True
    passed += 1

    # Per-face UV filtering separates two atlas bands inside one merged LOD mesh.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    merged = _make_compliant_cube("Merged_LOD2", size=2.0)
    uv = merged.data.uv_layers[0]
    for poly in merged.data.polygons:
        high_band = (poly.index % 2) == 0
        uvals = [0.80, 0.90, 0.90, 0.80] if high_band else [0.10, 0.70, 0.70, 0.10]
        vvals = [0.0, 10.0, 20.0, 30.0] if high_band else [0.0, 1.0, 1.0, 0.0]
        for offset, loop_index in enumerate(poly.loop_indices):
            uv.data[loop_index].uv = (uvals[offset % len(uvals)], vvals[offset % len(vvals)])
    with tempfile.TemporaryDirectory(prefix="bak_profile_") as tmp:
        profile_path = Path(tmp) / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "atlas-band-test",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "qa": {
                        "common": {"require_monotonic_lod_tris": False},
                        "asset_classes": {
                            "atlas_band_test": {
                                "reject_boundary_edges": False,
                                "require_non_overlapping_uv1": False,
                                "uv_checks": [
                                    {
                                        "id": "high_band",
                                        "patterns": ["Merged*"],
                                        "lods": [2],
                                        "face_u_min_gte": 0.78,
                                        "u_min_gte": 0.78,
                                        "u_max_lte": 1.0,
                                        "min_v_span": 5.0
                                    },
                                    {
                                        "id": "body_band",
                                        "patterns": ["Merged*"],
                                        "lods": [2],
                                        "exclude_face_u_min_gte": 0.78,
                                        "u_max_lte": 0.74
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }), encoding="utf-8")
        atlas = run_qa(
            target="unity",
            asset_class="atlas_band_test",
            project_profile=str(profile_path),
        )
        assert atlas["passed"], atlas
        by_id = {item["id"]: item["uv"] for item in atlas["evidence"]["uv"]}
        assert by_id["high_band"]["u_min"] >= 0.78
        assert by_id["high_band"]["v_span"] >= 5.0
        assert by_id["body_band"]["u_max"] <= 0.74
    passed += 1

    # Review visibility uses generic hierarchy patterns, not vehicle/wreck semantics.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    normal = _make_compliant_cube("Body_LOD0", size=1.0)
    variant_root = _link_empty("Variant_Destroyed_LOD0")
    variant = _make_compliant_cube("Body_Destroyed", location=(0.0, 0.0, 2.0), size=1.0)
    variant.parent = variant_root
    assert _matches_hierarchy_patterns(variant, ["Variant_Destroyed*"])
    saved = _set_mesh_visibility(
        bpy.context.scene,
        lod=0,
        exclude_patterns=["Variant_Destroyed*"],
        lod_pattern=DEFAULT_LOD_PATTERN,
        collider_pattern=DEFAULT_COLLIDER_PATTERN,
    )
    assert normal.hide_render is False
    assert variant.hide_render is True
    _restore = saved
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name in _restore:
            obj.hide_render = _restore[obj.name]
    saved = _set_mesh_visibility(
        bpy.context.scene,
        lod=0,
        include_patterns=["Variant_Destroyed*"],
        lod_pattern=DEFAULT_LOD_PATTERN,
        collider_pattern=DEFAULT_COLLIDER_PATTERN,
    )
    assert normal.hide_render is True
    assert variant.hide_render is False
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name in saved:
            obj.hide_render = saved[obj.name]
    passed += 1

    # Auto review lighting scales with subject size instead of assuming vehicle-scale assets.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    assert abs(_review_light_scale(0.5) - 0.04) < 1e-9
    assert abs(_review_light_scale(2.5) - 1.0) < 1e-9
    _ensure_lighting(scene, [0.0, 0.0, 0.0], 0.5)
    energies = {o.name: o.data.energy for o in scene.objects if o.type == "LIGHT"}
    assert set(energies) == {"QA_Key", "QA_Fill", "QA_Rim"}, energies
    assert abs(energies["QA_Key"] - 36.0) < 1e-6, energies
    assert abs(energies["QA_Fill"] - 20.0) < 1e-6, energies
    assert abs(energies["QA_Rim"] - 28.0) < 1e-6, energies
    passed += 1

    # Collision review keeps the primary LOD visible and overlays temporary wire geometry.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    body0 = _make_compliant_cube("Prop_LOD0", size=1.0)
    body1 = _make_compliant_cube("Prop_LOD1", location=(0.0, 0.0, 2.0), size=0.8)
    collider = _make_compliant_cube("Prop_COL_01", size=1.05)
    saved = _set_collision_overlay_visibility(
        bpy.context.scene,
        lod=0,
        lod_pattern=DEFAULT_LOD_PATTERN,
        collider_pattern=DEFAULT_COLLIDER_PATTERN,
    )
    assert body0.hide_render is False
    assert body1.hide_render is True
    assert collider.hide_render is False
    overlay = _prepare_collision_wireframe(
        bpy.context.scene, 0.5, collider_pattern=DEFAULT_COLLIDER_PATTERN
    )
    assert len(overlay) == 1, overlay
    assert overlay[0]["object"] is collider
    assert overlay[0]["modifier"].type == "WIREFRAME"
    assert len(collider.data.materials) == 1
    _restore_collision_wireframe(overlay)
    assert not any(mod.type == "WIREFRAME" for mod in collider.modifiers)
    assert len(collider.data.materials) == 0
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name in saved:
            obj.hide_render = saved[obj.name]
    passed += 1

    # Imported-object cleanup caches type/data before deletion and removes orphan mesh data.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    temp = _make_compliant_cube("ImportedTemp", size=1.0)
    mesh_name = temp.data.name
    _remove_imported_objects([temp])
    assert bpy.data.objects.get("ImportedTemp") is None
    assert bpy.data.meshes.get(mesh_name) is None
    passed += 1

    # Hierarchy-safe FBX prebake + station root zeroing must survive a fresh Blender import.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root = _link_empty("Vehicle_Station", location=(0.0, -0.04, 1.64))
    turret = _link_empty("Turret_Pivot", parent=root)
    gun = _link_empty("Gun_Elevation_Pivot", parent=turret, location=(0.0, -0.5, 0.3))
    barrel = _make_compliant_cube("Gun_Barrel_LOD0", location=(0.0, 0.0, 0.0), size=0.4)
    barrel.parent = gun
    barrel.location = (0.0, -1.0, 0.0)
    socket = _link_empty(
        "Socket_Muzzle_Main",
        parent=gun,
        location=(0.0, -2.0, 0.0),
        rotation=(0.15, -0.2, 0.1),
    )
    original_root_location = tuple(root.location)

    with tempfile.TemporaryDirectory(prefix="bak_bundle_test_") as tmp:
        root_dir = Path(tmp)
        spec = {
            "schema_version": "1.0",
            "asset_id": "bundle_contract",
            "parts": [{
                "id": "station_lod0",
                "role": "station",
                "lod": 0,
                "root": "Vehicle_Station",
                "file": "bundle_contract_Station_LOD0.fbx",
                "zero_root_location": True
            }]
        }
        spec_path = root_dir / "bundle.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        first = run_bundle(str(spec_path), target="unity", out_dir=str(root_dir / "out1"), verify_roundtrip=False)
        assert first["status"] == "ok", first
        assert tuple(round(v, 6) for v in root.location) == tuple(round(v, 6) for v in original_root_location)
        assert first["parts"][0]["inventory"]["objects"][0] is not None

        second = run_bundle(str(spec_path), target="unity", out_dir=str(root_dir / "out2"), verify_roundtrip=True)
        assert second["status"] == "ok", second
        rt = second["parts"][0]["roundtrip"]
        assert rt["passed"], rt
        assert not rt["transform_errors"], rt
        assert not rt["zero_root_errors"], rt
        assert rt["embedded_images"]["passed"], rt
        assert Path(second["artifacts"]["manifest"]).is_file()
    passed += 1

    # Alternate LOD/collider/socket naming is entirely profile-driven.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    alt_root = _link_empty("AltRoot")
    alt_body0 = _make_compliant_cube("Level0__Body", size=1.0)
    alt_body0.parent = alt_root
    alt_body1 = _make_compliant_cube("Level1__Body", location=(0.0, 0.0, 1.0), size=0.5)
    alt_body1.parent = alt_root
    alt_proxy = _make_compliant_cube("Proxy01__Body", size=1.05)
    alt_proxy.parent = alt_root
    alt_aim = _link_empty(
        "Aim_Muzzle",
        parent=alt_root,
        location=(0.1, -0.3, 0.4),
        rotation=(0.1, 0.2, -0.15),
    )
    with tempfile.TemporaryDirectory(prefix="bak_alt_policy_") as tmp:
        root_dir = Path(tmp)
        profile_path = root_dir / "profile.json"
        profile_path.write_text(json.dumps({
            "name": "alternate-naming",
            "version": "0.1.0",
            "target_overrides": {
                "unity": {
                    "naming": {
                        "lod_pattern": "Level{index}__{name}",
                        "collider_pattern": "Proxy{index:02d}__{name}"
                    },
                    "export": {
                        "prebake_directional_patterns": ["Aim_*"]
                    },
                    "qa": {
                        "common": {"require_monotonic_lod_tris": False}
                    }
                }
            }
        }), encoding="utf-8")
        spec_path = root_dir / "bundle.json"
        spec_path.write_text(json.dumps({
            "schema_version": "1.0",
            "asset_id": "alternate",
            "parts": [{
                "id": "main",
                "role": "primary",
                "root": "AltRoot",
                "file": "alternate.fbx"
            }]
        }), encoding="utf-8")
        alt = run_bundle(
            str(spec_path),
            target="unity",
            project_profile=str(profile_path),
            out_dir=str(root_dir / "out"),
            verify_roundtrip=True,
        )
        assert alt["status"] == "ok", alt
        part = alt["parts"][0]
        assert part["assembly_inventory"]["lods"]["0"]["objects"] == ["Level0__Body"], part
        assert part["assembly_inventory"]["lods"]["1"]["objects"] == ["Level1__Body"], part
        assert part["assembly_inventory"]["colliders"] == ["Proxy01__Body"], part
        assert part["roundtrip"]["passed"], part["roundtrip"]
        assert not part["roundtrip"]["transform_errors"], part["roundtrip"]
        imported_names = {o["name"] for o in part["roundtrip"]["imported_inventory"]["objects"]}
        assert "Aim_Muzzle" in imported_names, imported_names
    passed += 1

    # Explicit collision geometry must remain visible in collider evidence but
    # never inflate the render-LOD triangle count or visible asset bounds.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    primary = _make_compliant_cube("Prop_LOD0", location=(0, 0, 1), size=2.0)
    proxy = _make_compliant_cube("Prop_COL_01", location=(0, 0, 1), size=2.5)
    from shared.scene_inspector import inspect_scene
    separated = inspect_scene(
        lod_pattern=DEFAULT_LOD_PATTERN,
        collider_patterns=DEFAULT_COLLIDER_PATTERN,
    )
    assert separated["lods"]["0"]["tri_count"] == 12, separated["lods"]
    assert separated["colliders"] == ["Prop_COL_01"], separated["colliders"]
    assert any(o["name"] == "Prop_COL_01" and o["excluded_from_lod"] and o["is_collider"]
               for o in separated["objects"])
    assert separated["bounds"]["size"] == [2.0, 2.0, 2.0], separated["bounds"]
    passed += 1

    return {"status": "ok", "tests_passed": passed}
