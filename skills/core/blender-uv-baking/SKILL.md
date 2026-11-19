---
name: blender-uv-baking
description: Use this skill when unwrapping UV0/UV1 lightmap channels, setting texel density, or baking canonical raw PBR maps (BaseColor, Normal, Metallic, Roughness, AO) in headless Blender before target channel packing.
---

# Blender UV & Canonical Raw PBR Baking

## UV Rules
1. Pack primary texture UVs on `UVMap` (UV0) with consistent texel density (default target band `256–1024 px/m`) and seam margins.
2. For static props and modular environment kits, create a second non-overlapping `LightmapUV` (UV1) channel with generous island padding (or record `"uv1_source": "unity_generate"` in the manifest).

## Critical Cycles Baking Guardrails
- **Never bake `BaseColor` or `Metallic` with Cycles' `DIFFUSE` pass:** Cycles multiplies `DIFFUSE` by `(1 - metallic)`, baking pure metals completely black. Always route the Principled BSDF's BaseColor, Metallic, and Roughness sockets into a temporary `ShaderNodeEmission` node and bake with `type='EMIT'`.
- **Normal Maps:** Bake tangent-space OpenGL (`+Y`) normal maps into 16-bit float buffers; `shared/channel_pack.py` handles 16-bit PNG output and automatic DirectX `-Y` green-channel flipping for DirectX targets.
- **No View-Transform Corruption:** Never save baked maps via `image.save_render()`. Pass float32 NumPy arrays into `shared/channel_pack.py` so packed 8/16-bit unpremultiplied PNGs preserve exact bytes even when `Alpha == 0`.
