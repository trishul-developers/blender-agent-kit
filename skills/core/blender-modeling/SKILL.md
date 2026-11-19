---
name: blender-modeling
description: Use this skill when creating or refining 3D meshes, props, or modular kits in headless Blender. Enforces metric scale, clean topology, applied transforms, pivot placement, and deterministic Python build scripts.
---

# Blender Modeling (Engine-Agnostic Core)

## Workflow
1. Set scene units to Metric (`scale_length = 1.0`, `1 BU = 1 m`) before creating geometry.
2. Author geometry via a deterministic Python build script and save both the `.blend` and `.py` build script to `--out`.
3. Place prop pivots at `bottom_center_z0` (object origin at ground plane `Z = 0`, centered in X/Y) unless the brief specifies otherwise.
4. Keep modifiers non-destructive during modeling, then verify applied transforms (`Location (0,0,0)`, `Rotation (0,0,0)`, `Scale (1,1,1)` — never negative scale) before QA or export.
5. Run `python <blender-core>/scripts/run.py qa --blend <out.blend> --target <target> --asset-class <solid_prop|open_sheet|skinned_character>` after modeling.
