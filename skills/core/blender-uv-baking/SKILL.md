---
name: blender-uv-baking
description: Use for UV authoring and canonical raw PBR baking before target texture packing. Keep the baking guardrails here; obtain UV and texture requirements from run.py contract.
---

# Blender UV & Raw PBR Baking

Read the resolved contract for UV requirements, texel-density policy, texture profile, map channels, bit depth, and normal convention.

## Critical baking guardrails

- Do **not** bake BaseColor or Metallic with Cycles `DIFFUSE`: metallic response can corrupt the source color. Route BaseColor, Metallic, and Roughness through temporary Emission and bake with `type='EMIT'`.
- Treat tangent-space normal convention as explicit source metadata; do not infer it from appearance alone. Preserve high precision when the contract requires 16-bit output.
- Do **not** save data maps through `image.save_render()`; view transforms can alter bytes. Use raw float data / the kit packing path for deterministic PNG output.
- UV1 presence is enforceable, but geometric island-overlap proof is not currently implemented; keep the emitted limitation in evidence.

Use `pack` only after canonical raw maps are valid.
