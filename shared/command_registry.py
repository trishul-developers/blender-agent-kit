"""Single source of truth for the public run.py command surface."""
from __future__ import annotations

COMMANDS = {
    "capabilities": {
        "module": "shared.capabilities",
        "mode": "host",
        "skill": "blender-core",
        "purpose": "Discover executable commands, installed targets/policies/profiles, and guidance-only skills.",
        "evidence": ["capability_inventory"],
    },
    "contract": {
        "module": "shared.contract",
        "mode": "host",
        "skill": "blender-core",
        "purpose": "Resolve target + production policy + optional project profile into one production contract.",
        "evidence": ["resolved_contract"],
    },
    "doctor": {
        "module": "tools.doctor_blender",
        "mode": "blender",
        "skill": "blender-core",
        "purpose": "Verify Blender version/device/runtime readiness.",
        "evidence": ["blender_version", "device"],
    },
    "inspect": {
        "module": "shared.scene_inspector",
        "mode": "blender",
        "skill": "blender-asset-qa",
        "purpose": "Inventory scene hierarchy, geometry, LODs, colliders, UVs, materials, and bounds.",
        "evidence": ["scene_inventory"],
    },
    "qa": {
        "module": "shared.qa_checks",
        "mode": "blender",
        "skill": "blender-asset-qa",
        "purpose": "Validate an asset against the resolved production contract.",
        "evidence": ["errors", "warnings", "qa_evidence", "scene_inventory"],
    },
    "pack": {
        "module": "shared.channel_pack",
        "mode": "blender",
        "skill": "blender-core",
        "purpose": "Pack canonical raw maps into a target texture profile.",
        "evidence": ["packed_textures", "texture_metadata"],
    },
    "export": {
        "module": "shared.exporter",
        "mode": "blender",
        "skill": "blender-core",
        "purpose": "Export one asset with target semantics and optional fresh-import verification.",
        "evidence": ["asset_manifest", "roundtrip", "scene_inventory"],
    },
    "bundle": {
        "module": "shared.bundle_exporter",
        "mode": "blender",
        "skill": "blender-bundle",
        "purpose": "Export a logical asset as multiple semantic parts with per-part verification.",
        "evidence": ["bundle_manifest", "part_inventories", "roundtrip"],
    },
    "review": {
        "module": "shared.review_shots",
        "mode": "blender",
        "skill": "blender-core",
        "purpose": "Render deterministic technical/review evidence from the resolved contract.",
        "evidence": ["review_images", "scene_inventory"],
    },
}

SUBCOMMAND_TO_MODULE = {name: spec["module"] for name, spec in COMMANDS.items()}
HOST_SUBCOMMANDS = {name for name, spec in COMMANDS.items() if spec["mode"] == "host"}
BLENDER_SUBCOMMANDS = {name for name, spec in COMMANDS.items() if spec["mode"] == "blender"}
