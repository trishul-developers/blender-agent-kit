"""Tier 2 headless Blender tests for fail-closed QA and semantic bundle round trips."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from shared.bundle_exporter import run as run_bundle
from shared.qa_checks import run as run_qa


def _make_compliant_cube(name: str = "Cube"):
    import bpy

    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(obj.data.uv_layers) < 2:
        obj.data.uv_layers.new(name="LightmapUV")
    return obj


def run() -> dict:
    import bmesh
    import bpy

    passed = 0

    # 1. Closed prop with bottom-center origin and UV1 passes.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("SolidProp")
    res = run_qa(target="unity", asset_class="solid_prop")
    assert res["passed"], f"Expected compliant cube to pass: {res}"
    passed += 1

    # 2. Open plane fails solid_prop but passes open_sheet.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    plane = bpy.context.object
    plane.name = "OpenSheet"
    assert not run_qa(target="unity", asset_class="solid_prop")["passed"]
    assert run_qa(target="unity", asset_class="open_sheet")["passed"]
    passed += 1

    # 3. Empty scenes fail closed.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    empty = run_qa(target="unity", asset_class="open_sheet")
    assert not empty["passed"]
    assert any(e["code"] == "no_meshes" for e in empty["errors"])
    passed += 1

    # 4. Closed mesh with reversed winding is rejected as inward-facing.
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

    # 5. Equal-triangle LODs violate monotonic reduction.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _make_compliant_cube("Asset_LOD0")
    _make_compliant_cube("Asset_LOD1")
    lod = run_qa(target="unity", asset_class="open_sheet")
    assert not lod["passed"]
    assert any(e["code"] == "non_monotonic_lod" for e in lod["errors"]), lod
    passed += 1

    # 6. A semantic bundle exports and fresh-reimports with matching inventory.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = _make_compliant_cube("BundleCube_LOD0")
    coll = bpy.data.collections.new("Body_LOD0")
    bpy.context.scene.collection.children.link(coll)
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    coll.objects.link(obj)

    with tempfile.TemporaryDirectory(prefix="bak_bundle_test_") as tmp:
        root = Path(tmp)
        spec = {
            "schema_version": "1.0",
            "asset_id": "bundle_contract",
            "parts": [
                {
                    "id": "body_lod0",
                    "role": "primary",
                    "lod": 0,
                    "collection": "Body_LOD0",
                    "file": "bundle_contract_LOD0.fbx"
                }
            ]
        }
        spec_path = root / "bundle.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        bundle = run_bundle(str(spec_path), target="unity", out_dir=str(root / "out"), verify_roundtrip=True)
        assert bundle["status"] == "ok", bundle
        assert bundle["parts"][0]["roundtrip"]["passed"], bundle
        assert Path(bundle["artifacts"]["manifest"]).is_file()
    passed += 1

    return {"status": "ok", "tests_passed": passed}
