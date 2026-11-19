---
name: blender-asset-qa
description: Use this skill to inventory and audit Blender assets for transforms, topology, UV presence/bounds, normals, aggregate LOD/material budgets, damage accounting, hierarchy, ground contact, symmetry, dimensions, and bone influences against target and optional project profiles.
---

# Blender Asset QA

```bash
python <blender-core>/scripts/run.py inspect --blend in.blend

python <blender-core>/scripts/run.py qa \
  --blend in.blend --target unity --asset-class solid_prop
```

Profiles can add project asset classes:

```bash
python <blender-core>/scripts/run.py qa \
  --blend vehicle.blend --target unity \
  --project-profile tactical-vehicle \
  --asset-class heavy_tracked_vehicle
```

## Implemented checks

- non-empty mesh scene;
- applied/negative scale;
- non-manifold and optional boundary-edge rejection;
- closed-mesh inward normals from signed volume;
- UV0 and requested UV1 presence;
- aggregate LOD triangle/material budgets;
- monotonic LOD counts and maximum reduction ratios;
- configurable `damage_prefix`, intact/damage triangle accounting, and allowed damage LODs;
- required nodes and parent pairs;
- ground-axis contact;
- vertex influence limits;
- simple pivot rules;
- L/R mirror subtree checks using triangle counts, mirrored bounds, and signed-volume magnitudes;
- semantic dimension boxes using named include/exclude patterns;
- UV min/max/span checks by pattern and LOD, suitable for repeat/atlas contracts.

Structured evidence is returned in `evidence.symmetry`, `evidence.dimensions`, and `evidence.uv`.

## Explicit limits

Geometric UV-island overlap and texel-density measurement are not yet implemented. Requested non-overlapping UV1 therefore enforces UV1 presence and emits `uv1_overlap_unverified` rather than claiming geometric proof.
