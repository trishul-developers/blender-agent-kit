---
name: blender-core
description: Use this skill as the starting point for any headless Blender 5.2+ asset creation, QA, texture packing, rendering, or game-engine export workflow. Routes requests to specialist core skills and target-engine plugins, and enforces the single run.py entrypoint.
---

# Blender Core

Always execute Blender through the single host entrypoint shim—never assemble raw multi-flag `blender -b ...` commands by hand:

```bash
python <blender-core>/scripts/run.py doctor --device auto
python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py export --blend in.blend --target unity --profile urp --out build/
python <blender-core>/scripts/run.py review --blend in.blend --device auto --out review/
```

## Routing Table
- **Geometry & props:** load `blender-modeling`
- **UV0/UV1 & raw PBR baking:** load `blender-uv-baking`
- **LOD chains & collision hulls:** load `blender-lod-collision`
- **Armatures & animation clips:** load `blender-rigging-animation`
- **Mesh/UV/budget audits:** load `blender-asset-qa`
- **Multi-file folder jobs:** load `blender-batch`
- **Engine-specific packing & export (Unity, etc.):** load `blender-target-<engine>` (e.g., `blender-target-unity`)

## Mandatory Rules
1. Run `doctor` first if the Blender environment has not been verified in this session.
2. Read `references/api-changes-5x.md` before writing custom `bpy` scripts for Blender 5.2 LTS / 5.3.
3. Never overwrite input `.blend` files in place; write outputs to `--out` with `copy=True` and co-deliver the deterministic Python build script alongside every generated `.blend`.
4. Keep core workflows engine-agnostic; let the active `target.json` drive axes, channel packing, naming, and QA thresholds.
