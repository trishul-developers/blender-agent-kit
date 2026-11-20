---
name: blender-asset-qa
description: Use to inspect and validate Blender assets against the resolved target, production policy, and optional project profile, returning structured evidence.
---

# Blender Asset QA

Discover the effective requirements first:

```bash
python <blender-core>/scripts/run.py contract --target unity --asset-class solid_prop
python <blender-core>/scripts/run.py inspect --blend asset.blend --target unity
python <blender-core>/scripts/run.py qa --blend asset.blend --target unity --asset-class solid_prop
```

QA can cover transforms, topology/winding, UV presence/bounds, LOD/material budgets, hierarchy, pivots/ground contact, symmetry/dimensions, damage accounting, and vertex-influence limits when configured.

Treat warnings as evidence, not success claims. In particular, requested UV1 currently proves presence but not geometric island non-overlap; `uv1_overlap_unverified` must remain visible.

Project-specific asset classes belong in project profiles.
