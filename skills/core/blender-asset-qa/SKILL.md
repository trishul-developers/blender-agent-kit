---
name: blender-asset-qa
description: Use this skill to inventory and audit Blender meshes, transforms, UV presence, normals, aggregate LOD/material budgets, hierarchy, ground contact, bone influences, and simple pivot rules against target and optional project-profile QA classes.
---

# Blender Asset QA

```bash
python <blender-core>/scripts/run.py inspect --blend in.blend

python <blender-core>/scripts/run.py qa \
  --blend in.blend --target unity --asset-class solid_prop
```

Optional project overlays can add production classes:

```bash
python <blender-core>/scripts/run.py qa \
  --blend vehicle.blend --target unity \
  --project-profile tactical-vehicle \
  --asset-class heavy_tracked_vehicle
```

Implemented checks include mesh presence, applied/negative scale, non-manifold and boundary edges, signed-volume inward normals, UV0/UV1 presence, aggregate per-LOD triangle/material budgets, monotonic/reduction-ratio rules, required nodes/parents, ground contact, vertex-group influence count, and simple bottom-center pivots.

**Explicit limitation:** when non-overlapping UV1 is requested, the current implementation enforces UV1 presence but does not yet calculate geometric UV-island overlap. It emits `uv1_overlap_unverified` instead of claiming a check that was not performed.
