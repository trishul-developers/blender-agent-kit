---
name: blender-profile-tactical-vehicle
description: Use this optional reusable profile for multi-part tactical ground vehicles that need semantic bundles, aggressive LOD reduction, damage-aware QA, ground-contact checks, BaseColor/Normal/Mask packing, and tactical review presets without modifying the generic Unity target.
---

# Tactical Vehicle Project Profile

This is an optional reusable overlay, not a Unity-global contract.

```bash
python <blender-core>/scripts/run.py qa \
  --blend vehicle.blend --target unity \
  --project-profile tactical-vehicle \
  --asset-class heavy_tracked_vehicle

python <blender-core>/scripts/run.py pack \
  --target unity \
  --project-profile tactical-vehicle \
  --profile tactical_urp \
  --asset-id Vehicle01 --material Body \
  --input-dir raw/ --size 2048 --detect-normal-y \
  --out build/

python <blender-core>/scripts/run.py review \
  --blend vehicle.blend \
  --project-profile tactical-vehicle \
  --preset tactical --out review/
```

The profile demonstrates reusable conventions:

- heavy/light tracked LOD budgets;
- every-step LOD ratio ≤ 0.50;
- `Damage_*` only in LOD0/LOD1;
- ground contact;
- optional turret/gun hierarchy;
- BaseColor + Normal + Mask packing;
- `station`/`kit` default zero-root roles;
- 1280×720 tactical review:
  - 12m close-up;
  - 50m / 150m / 400m;
  - LOD0–3;
  - damage views;
  - collision outline.

Exact vehicle dimensions, socket inventories, faction rules, simulation values, content IDs, and game-specific import behavior belong in an external downstream profile.
