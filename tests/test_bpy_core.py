"""Tier 2 headless Blender core tests (runs inside Blender 5.2+ via tools/run_tests.py --suite core)."""
from __future__ import annotations

from shared.qa_checks import run as run_qa


def run() -> dict:
    import bpy

    # Test 1: Solid prop (default cube) should pass solid_prop QA
    bpy.ops.wm.read_factory_settings(use_empty=False)
    res_solid = run_qa(target="unity", asset_class="solid_prop")
    assert res_solid["passed"], f"Expected default cube to pass solid_prop QA: {res_solid}"

    # Test 2: Open plane should fail solid_prop (boundary edges) but pass open_sheet
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    res_fail = run_qa(target="unity", asset_class="solid_prop")
    assert not res_fail["passed"], "Expected open plane to fail solid_prop boundary check"
    res_sheet = run_qa(target="unity", asset_class="open_sheet")
    assert res_sheet["passed"], f"Expected open plane to pass open_sheet QA: {res_sheet}"

    return {"status": "ok", "tests_passed": 2}
