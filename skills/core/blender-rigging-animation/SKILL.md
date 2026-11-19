---
name: blender-rigging-animation
description: Use this skill when rigging characters or articulated props, normalizing skin weights, staging NLA animation clips, or checking loop seams in headless Blender prior to game-engine export.
---

# Blender Rigging & Animation

## Workflow
1. Author bipedal rigs in a clean T-pose with applied transforms (`Scale (1,1,1)`) on both armature and skinned meshes.
2. Limit bone influences per vertex to the active target's `max_bone_weights_per_vertex` (e.g., `4` for Unity/Godot, `8` for Unreal) and normalize all vertex weights.
3. Stage each animation clip cleanly as an NLA strip (`bake_anim_use_nla_strips: true`, `bake_anim_use_all_actions: false` in `target.json`) so exporters never emit duplicate clips.
4. Strip control/helper bones at export (`only_deform_bones: true`, `add_leaf_bones: false`) and verify `roundtrip_armature_scale_tolerance <= 0.001` in fresh re-import tests.
