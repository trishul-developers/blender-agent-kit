---
name: blender-profile-tactical-vehicle
description: Optional reusable production profile for tracked/tactical ground-vehicle workflows. Use contract discovery for exact classes, budgets, packing, damage, bundle, and review rules.
---

# Tactical Vehicle Project Profile

This is an optional reusable overlay, not a Unity-global contract.

Discover its effective rules instead of copying values from prose:

```bash
python <blender-core>/scripts/run.py contract   --target unity --project-profile tactical-vehicle   --asset-class heavy_tracked_vehicle --profile tactical_urp
```

The profile adds tracked-vehicle asset classes, damage-aware QA, a custom texture profile, bundle defaults, and a tactical review preset. Exact vehicle dimensions, sockets, faction/content rules, and simulation behavior remain downstream.
