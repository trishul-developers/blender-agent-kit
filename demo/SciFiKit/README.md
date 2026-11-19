# Demonstration B — Sci-Fi Modular Environment Kit ("Helios Conduit")

Independently authored 6-piece industrial sci-fi modular environment kit built from scratch in Blender 5.2.4 LTS and validated through **Blender Agent Kit v0.2.1** (`0c6c3d10cb7265166fe46e7c5ccab69ff2abf793`).

## Modular Grid & Component Inventory

- **Grid Pitch (Metric, 1 BU = 1 m):** `4.00 m × 4.00 m` horizontal footprint, `3.60 m` corridor clearance height (`0.25 m` deck + `3.60 m` wall/bulkhead + `0.35 m` ceiling plenum).
- **Materials:** `2` shared materials across the entire kit — `M_SciFi_TrimSheet` (`2048×2048` 5-band hard-surface trim sheet) and `M_SciFi_Emissive` (`1024×1024` cyan LED / amber beacon / telemetry screen trim).
- **UV Channels:** `UVMap` (UV0, trim-sheet mapped) and `LightmapUV` (UV1, Smart UV Project non-overlapping).

| Module | Dimensions (m) | LOD0 Tris | Sockets | Role |
| --- | --- | ---: | ---: | --- |
| `SF_Bulkhead_Arch` | `4.00 × 0.90 × 3.60` | 2,392 | 6 (incl. depth-2 `Header`) | Hero 4-LOD pressurized doorway + 3-hull walkable collision |
| `SF_Wall_Straight` | `4.00 × 0.45 × 3.60` | 764 | 2 | Armored dado, ceramic panels, conduit pipe, cyan LED cornice |
| `SF_Wall_Corner` | `4.00 × 4.00 × 3.60` | 324 | 2 | 90° L-junction with 45° diagnostic telemetry console |
| `SF_Floor_Panel` | `4.00 × 4.00 × 0.25` | 280 | 4 | Diamond-plate walkways, central grating, cyan under-floor busbars |
| `SF_Ceiling_Panel` | `4.00 × 4.00 × 0.35` | 388 | 2 | Coffered ribs, ventilation ducting, twin overhead LED troughs |
| `SF_Pillar_Support` | `0.65 × 0.65 × 3.60` | 236 | 2 | Octagonal chamfered support column with vertical cyan accent strips |

- **Assembled Environment (`scenes/SciFi_Corridor_Assembly.blend`):** `21` snapped module instances (`109` objects, `21` meshes, `13,308` triangles) forming an L-shaped pressurized corridor.

## Representative Hero Module (`SF_Bulkhead_Arch`) QA & Round-Trip Evidence

- **QA (`modular_bulkhead` profile class):** `PASS` (`0` errors; `7/7` required nodes and `4/4` nested parent-child pairs verified; `4` explicit `uv1_overlap_unverified` warnings).
- **Semantic Bundle Export (`Unity URP`, `prebake_yup_hierarchy=true`, `prebake_directional_patterns=["Socket_*"]`):**

| Bundle Part | File | Objects | Scene Tris | Re-Imported Tris | Parent / Transform Errors | Round-Trip | Embedded Images |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| `bulkhead_full` | `SF_Bulkhead_Arch_Complete.fbx` | 15 | 3,728 | 3,728 | 0 / 0 | PASS | 0 (PASS) |
| `bulkhead_lod0` | `SF_Bulkhead_Arch_LOD0.fbx` | 1 | 2,392 | 2,392 | 0 / 0 | PASS | 0 (PASS) |
| `bulkhead_lod1` | `SF_Bulkhead_Arch_LOD1.fbx` | 1 | 904 | 904 | 0 / 0 | PASS | 0 (PASS) |
| `bulkhead_lod2` | `SF_Bulkhead_Arch_LOD2.fbx` | 1 | 336 | 336 | 0 / 0 | PASS | 0 (PASS) |
| `bulkhead_lod3` | `SF_Bulkhead_Arch_LOD3.fbx` | 1 | 60 | 60 | 0 / 0 | PASS | 0 (PASS) |
| `bulkhead_collision` | `SF_Bulkhead_Arch_COL.fbx` | 3 | 36 | 36 | 0 / 0 | PASS | 0 (PASS) |

## Showcase Gallery

1. `showcase/01_hero_assembly.webp` (`01_hero_assembly.png`) — 1920×1080 Cycles hero render of assembled L-shaped corridor
2. `showcase/02_technical_multiview.webp` (`02_technical_multiview.png`) — 6-module perspective, top/front orthographics, and bulkhead ortho
3. `showcase/03_lod_comparison.webp` (`03_lod_comparison.png`) — 4-level LOD comparison (`2,392 / 904 / 336 / 60` tris)
4. `showcase/04_collision_hierarchy_sockets.webp` (`04_collision_hierarchy_sockets.png`) — 3-hull walkable collision wireframe + verified 15-object hierarchy & socket round-trip proof
5. `showcase/05_textures_materials.webp` (`05_textures_materials.png`) — Trim-sheet (2048²) & emissive (1024²) raw PBR → Unity URP packed proof

## Reproduction Commands

```bash
export BLENDER_EXECUTABLE=/path/to/blender-5.2.4/blender
KIT=/path/to/blender-agent-kit
OUT=/path/to/blender-agent-kit-independent-trial/SciFiKit

python3 "$OUT/source/generate_scifi_textures.py" --out "$OUT/raw_textures"
"$BLENDER_EXECUTABLE" --factory-startup -b --python-exit-code 1 \
  -P "$OUT/source/build_scifi_kit.py" -- \
  --raw-textures "$OUT/raw_textures" --out-dir "$OUT"

python3 "$KIT/skills/core/blender-core/scripts/run.py" qa \
  --blend "$OUT/scenes/SF_Bulkhead_Arch.blend" --target unity \
  --project-profile "$OUT/source/scifikit.profile.json" \
  --asset-class modular_bulkhead --result-json "$OUT/evidence/qa_bulkhead.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" pack \
  --target unity --profile urp --asset-id SciFiKit \
  --material M_SciFi_TrimSheet --input-dir "$OUT/raw_textures/trim_sheet" \
  --size 2048 --detect-normal-y --out "$OUT/packed_textures" \
  --result-json "$OUT/evidence/pack_trim_sheet.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" pack \
  --target unity --profile urp --asset-id SciFiKit \
  --material M_SciFi_Emissive --input-dir "$OUT/raw_textures/emissive" \
  --size 1024 --detect-normal-y --out "$OUT/packed_textures" \
  --result-json "$OUT/evidence/pack_emissive.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" bundle \
  --blend "$OUT/scenes/SF_Bulkhead_Arch.blend" --spec "$OUT/source/bundle-spec.json" \
  --target unity --profile urp --out "$OUT/exports" \
  --result-json "$OUT/evidence/bundle_bulkhead.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" review \
  --blend "$OUT/scenes/SF_Bulkhead_Arch.blend" \
  --project-profile "$OUT/source/scifikit.profile.json" \
  --preset bulkhead_lods --samples 14 --device cpu \
  --out "$OUT/renders/bulkhead_review" --result-json "$OUT/evidence/review_bulkhead.json"

python3 "$OUT/source/compose_scifi_showcase.py" --scifi-dir "$OUT"
```
