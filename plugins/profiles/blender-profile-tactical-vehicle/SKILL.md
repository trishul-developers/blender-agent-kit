---
name: blender-profile-tactical-vehicle
description: Use this optional profile for multi-part tactical ground vehicles that need semantic chassis/station/collision/wreck bundles, aggressive LOD reduction, ground-contact QA, and BaseColor/Normal/Mask packing without modifying the generic Unity target.
---

# Tactical Vehicle Project Profile

This is an **optional project overlay**, not part of the generic Unity contract.

Use it when a downstream project has tracked tactical vehicles with separate semantic parts:

```bash
python <blender-core>/scripts/run.py qa --blend vehicle.blend --target unity \
  --project-profile tactical-vehicle --asset-class heavy_tracked_vehicle

python <blender-core>/scripts/run.py pack --target unity \
  --project-profile tactical-vehicle --profile tactical_urp \
  --asset-id Vehicle01 --material Body --input-dir raw/ --out build/
```

The profile demonstrates reusable requirements distilled from military-asset production:
- aggregate LOD budgets and <= 0.50 reduction ratios;
- ground contact tolerance;
- optional turret/gun hierarchy checks;
- multi-part bundle roles;
- BaseColor + Normal + Mask packing (Mask = Metallic/AO/Detail/Smoothness).

Exact project-specific sockets, damage-node names, vehicle measurements, faction rules, and simulation contracts belong in downstream profile files, not here.
