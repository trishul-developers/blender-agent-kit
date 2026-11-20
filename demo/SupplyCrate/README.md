# Demonstration A — SupplyCrate (Independent Trial)

> **Canonical v0.2.3+ reproduction:** `python demo/SupplyCrate/run_demo.py --mode full --clean`  
> Fast CI/source smoke: `python demo/SupplyCrate/run_demo.py --mode smoke --clean`  
> Regenerated output is written to `build/canonical-demos/SupplyCrate/` by default; the checked-in evidence below remains the original independent v0.2.1 trial.


Independently authored industrial wooden-and-steel shipping crate built from scratch using deterministic Blender 5.2.4 LTS Python scripts and validated end-to-end through **Blender Agent Kit v0.2.1** (`0c6c3d10cb7265166fe46e7c5ccab69ff2abf793`).

## Design & Specifications

- **Bounds (Metric, 1 BU = 1 m):** `1.19 m (W) × 0.86 m (D) × 0.73 m (H)` (including side handles, latches, hinges, and corner brackets; core body `1.10 × 0.80 × 0.72 m`)
- **Origin / Pivot:** `bottom_center_z0` at `(0.0, 0.0, 0.0)` (centered X/Y bounds, `Z min = 0.0`)
- **Material Budget:** `1` material (`M_SupplyCrate_Body`), `2048×2048` procedural PBR source atlas (`seed=42`) packed into Unity URP (`_BaseMap`, `_MetallicGlossMap`, `_BumpMap`, `_OcclusionMap`)
- **UV Channels:** `UVMap` (UV0, structured 4-quadrant atlas) and `LightmapUV` (UV1, Smart UV Project non-overlapping)

## Geometry, LOD & Round-Trip Metrics

| Part | Scene Triangles | Exported / Re-imported Triangles | Non-Manifold / Boundary Edges | Signed Volume (m³) | Round-Trip Parity | Embedded Images |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `SupplyCrate_LOD0` | 4,204 | 4,204 | 0 / 0 | +0.574 | PASS | 0 (PASS) |
| `SupplyCrate_LOD1` | 1,084 | 1,084 | 0 / 0 | +0.574 | PASS | 0 (PASS) |
| `SupplyCrate_LOD2` | 136 | 136 | 0 / 0 | +0.617 | PASS | 0 (PASS) |
| `SupplyCrate_COL_01` | 12 | 12 | 0 / 0 | +0.749 | PASS | 0 (PASS) |

- **QA (`solid_prop`, Unity target + profile):** `PASS` (`0` errors; `3` explicit `uv1_overlap_unverified` warnings documenting the kit's known geometric UV1 overlap limit).
- **URP Texture Packing Verification:** `16-bit` OpenGL normal preserved (`_BumpMap`), `_MetallicGlossMap` alpha channel matches `1 - roughness` with `MAE = 2.23e-08`.

## Showcase Gallery

1. `showcase/01_hero.webp` (`01_hero.png`) — 1920×1080 Cycles hero render
2. `showcase/02_orthographic_multiview.webp` (`02_orthographic_multiview.png`) — 2×2 orthographic multiview
3. `showcase/03_lod_comparison.webp` (`03_lod_comparison.png`) — LOD0 / LOD1 / LOD2 silhouette comparison
4. `showcase/04_lod_distance_grid.webp` (`04_lod_distance_grid.png`) — 3×3 LOD × viewing-distance grid
5. `showcase/05_collision_overlay.webp` (`05_collision_overlay.png`) — 12-tri convex hull wireframe over LOD0
6. `showcase/06_pbr_to_urp_textures.webp` (`06_pbr_to_urp_textures.png`) — All 5 raw PBR + 4 Unity URP packed maps

## Reproduction Commands

```bash
export BLENDER_EXECUTABLE=/path/to/blender-5.2.4/blender
KIT=/path/to/blender-agent-kit
OUT=/path/to/blender-agent-kit-independent-trial/SupplyCrate

python3 "$OUT/source/generate_pbr_atlas.py" --out "$OUT/raw_textures" --size 2048 --seed 42
"$BLENDER_EXECUTABLE" --factory-startup -b --python-exit-code 1 \
  -P "$OUT/source/build_supplycrate.py" -- \
  --raw-textures "$OUT/raw_textures" --out-blend "$OUT/scenes/SupplyCrate.blend"

python3 "$KIT/skills/core/blender-core/scripts/run.py" qa \
  --blend "$OUT/scenes/SupplyCrate.blend" --target unity \
  --project-profile "$OUT/source/supplycrate.profile.json" \
  --asset-class solid_prop --result-json "$OUT/evidence/qa.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" pack \
  --target unity --profile urp --asset-id SupplyCrate \
  --material M_SupplyCrate_Body --input-dir "$OUT/raw_textures" \
  --size 2048 --detect-normal-y --out "$OUT/packed_textures" \
  --result-json "$OUT/evidence/pack.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" bundle \
  --blend "$OUT/scenes/SupplyCrate.blend" --spec "$OUT/source/bundle-spec.json" \
  --target unity --profile urp --out "$OUT/exports" \
  --result-json "$OUT/evidence/bundle.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" review \
  --blend "$OUT/scenes/SupplyCrate.blend" \
  --project-profile "$OUT/source/supplycrate.profile.json" \
  --preset showcase_tiles --samples 14 --device cpu \
  --out "$OUT/renders/tiles" --result-json "$OUT/evidence/review_tiles.json"

python3 "$KIT/skills/core/blender-core/scripts/run.py" review \
  --blend "$OUT/scenes/SupplyCrate.blend" \
  --project-profile "$OUT/source/supplycrate.profile.json" \
  --preset hero_hd --samples 28 --device cpu \
  --out "$OUT/renders/hd" --result-json "$OUT/evidence/review_hd.json"

python3 "$OUT/source/compose_showcase.py" --trial-dir "$OUT"
```
