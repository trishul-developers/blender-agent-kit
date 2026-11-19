---
name: blender-core
description: Use this skill as the starting point for headless Blender 5.2+ inspection, asset creation, QA, texture packing, rendering, semantic bundle export, or game-engine export. Routes to specialist core skills, target plugins, and optional project profiles through one run.py entrypoint.
---

# Blender Core

Always execute Blender through the single host entrypoint:

```bash
python <blender-core>/scripts/run.py doctor --device auto
python <blender-core>/scripts/run.py inspect --blend in.blend
python <blender-core>/scripts/run.py qa --blend in.blend --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py pack --target unity --profile urp --asset-id prop01 --material Body --input-dir raw/ --out build/
python <blender-core>/scripts/run.py export --blend in.blend --target unity --profile urp --out build/
python <blender-core>/scripts/run.py bundle --blend in.blend --spec bundle.json --target unity --out build/
python <blender-core>/scripts/run.py review --blend in.blend --device auto --out review/
```

## Routing

- Geometry: `blender-modeling`
- UV/raw PBR baking: `blender-uv-baking`
- LOD/collision authoring: `blender-lod-collision`
- Rigging/animation: `blender-rigging-animation`
- Inspection/QA: `blender-asset-qa`
- Compound multi-file assets: `blender-bundle`
- Folder jobs: `blender-batch`
- Engine export: `blender-target-<engine>`
- Optional downstream conventions: `blender-profile-<name>` or an external project-profile JSON

## Boundaries

1. Core primitives stay engine- and project-agnostic.
2. Target plugins own engine semantics such as axes, exporter settings, and standard texture layouts.
3. Project profiles are overlays: they may add asset classes, budgets, naming, or texture profiles without changing the base target.
4. Exact simulation contracts, faction rules, vehicle measurements, socket inventories, and game-specific damage semantics belong in downstream project profiles.
5. Deterministic build scripts and source files should be included in build inputs so manifests change when source/config/tool identity changes.
