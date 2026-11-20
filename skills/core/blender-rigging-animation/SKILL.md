---
name: blender-rigging-animation
description: Use for skinned or articulated assets and animation staging. Rig type, bone-weight limits, export settings, and verification requirements come from the resolved contract.
---

# Blender Rigging & Animation

Read `run.py contract` before rigging.

- Use a bind/rest pose appropriate to the asset and downstream rig contract; do not assume every rig is a biped or T-pose.
- Keep armature and skinned-mesh transforms consistent with the contract.
- Enforce the configured maximum vertex influences and normalize weights.
- Stage clips so the target exporter emits each intended action once; honor resolved NLA/action settings.
- Keep control/helper-bone export behavior target-driven.
- Verify exported armature scale, hierarchy, transforms, and animation inventory with the available round-trip/engine-side checks.

Do not infer engine-specific weight limits or skeleton conventions from this core skill.
