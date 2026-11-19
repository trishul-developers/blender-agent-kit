# Blender Agent Kit

**Give AI agents production-grade Blender capabilities.**

Blender Agent Kit is a headless-first Blender 5.2+ toolkit for AI agents that need to **create, modify, validate, render, and export 3D assets** through deterministic, automatable workflows.

Instead of treating Blender as a manual GUI-only tool, the kit gives an agent a structured production path:

```text
task / prompt
    ↓
create or modify geometry
    ↓
UVs · materials · textures
    ↓
LODs · collision · rigging / animation
    ↓
QA + machine-readable evidence
    ↓
review renders
    ↓
FBX / GLB / glTF / semantic bundles
    ↓
game-engine pipeline
```

The emphasis is not only on generating geometry. The goal is to let an agent produce **repeatable, inspectable, testable assets** that can survive a real production pipeline.

> Blender Agent Kit is not a neural text-to-3D or text-to-image model. Asset creation is skill-driven: an agent authors deterministic Blender/Python build logic, executes Blender headlessly, and uses the kit to validate and deliver the result.

## Independently tested — two real 3D asset workflows

A separate agent installed **Blender 5.2.4 LTS** and the **unmodified Blender Agent Kit v0.2.1** release, then authored two new assets from scratch. It recorded installation friction, actual QA failures, output files, real Blender FBX round trips, and an estimated with-kit versus no-kit effort comparison. This is an **agent-authored field trial**, not a controlled benchmark or Unity Editor test.

### SupplyCrate — procedural prop, PBR, QA, LOD and collision

![Independently authored SupplyCrate hero render](demo/SupplyCrate/showcase/01_hero.webp)

An independently authored weathered wood-and-steel prop with a **2,048² PBR atlas** and LODs of **4,204 → 1,084 → 136 triangles**. The kit's QA caught **two actual production defects** in earlier iterations: a missing common root and a **2.5 mm pivot offset**. The corrected scene reports **0 QA errors**, and all **4/4 FBX exports** passed Blender fresh-import checks.

![Actual collision wireframe overlay over the SupplyCrate](demo/SupplyCrate/showcase/05_collision_overlay.webp)

<details>
<summary><strong>View SupplyCrate technical proof: PBR → URP, LODs, orthographics, distance grid</strong></summary>

![Five raw PBR maps and four Unity URP packed maps](demo/SupplyCrate/showcase/06_pbr_to_urp_textures.webp)

![Three SupplyCrate LODs](demo/SupplyCrate/showcase/03_lod_comparison.webp)

![SupplyCrate orthographic review](demo/SupplyCrate/showcase/02_orthographic_multiview.webp)

![SupplyCrate LOD versus distance](demo/SupplyCrate/showcase/04_lod_distance_grid.webp)

</details>

[Independent SupplyCrate source, evidence, and reproduction instructions](demo/SupplyCrate/README.md)

### Helios Conduit — modular Sci-Fi environment and hierarchy-safe export

![Independently authored Helios Conduit modular corridor](demo/SciFiKit/showcase/01_hero_assembly.webp)

The agent created **six modular piece types** and an assembled corridor of **21 module instances, 109 objects, and 13,308 triangles**. The representative bulkhead has four LODs (**2,392 / 904 / 336 / 60 triangles**), six directional sockets, a nested hierarchy, and three walkable collision hulls. All **6/6 FBX exports** passed Blender fresh-import parity, including hierarchy and transform checks.

![Sci-Fi bulkhead LOD comparison](demo/SciFiKit/showcase/03_lod_comparison.webp)

<details>
<summary><strong>View Sci-Fi technical proof: modules, collision/sockets and materials</strong></summary>

![Six-piece Sci-Fi module catalog and technical multiview](demo/SciFiKit/showcase/02_technical_multiview.webp)

![Bulkhead collision, sockets, hierarchy and round-trip evidence](demo/SciFiKit/showcase/04_collision_hierarchy_sockets.webp)

![Trim sheet, emissive and Unity URP texture evidence](demo/SciFiKit/showcase/05_textures_materials.webp)

</details>

[Independent Sci-Fi source, evidence, and reproduction instructions](demo/SciFiKit/README.md)

### What the independent agent found valuable

| Real-world result | Evidence from the v0.2.1 trial |
| --- | --- |
| **Asset correctness** | QA caught an unrooted scene and 2.5 mm pivot drift; both failures and final passing reports are retained |
| **Hierarchy-safe FBX** | **10/10 exported FBXs** passed Blender fresh-import triangle parity; the bulkhead also passed parent/local-transform verification |
| **Unity URP texture preparation** | 16-bit OpenGL normal preservation and verified smoothness-from-roughness alpha packing; the SupplyCrate comparison contains all **5 source + 4 packed** maps |
| **Agent-readable automation** | Structured `inspect`, `qa`, `pack`, `bundle`, and `review` results fed the agent's technical proof sheets |
| **Review evidence** | Headless orthographic, LOD/range, and wireframe collision views reduced custom rendering work |

### Agent-reported effort savings — estimates, not benchmarks

| Scope | Estimated effort with kit | Estimated without kit | Estimated saving |
| --- | ---: | ---: | ---: |
| Pipeline engineering (setup, packing, QA, review, sheets, export) | 62 min | 238–308 min | **74–80%** |
| Combined end-to-end work (both new demos) | 148 min | 329–399 min | **55–63%** |

The agent estimated the with-kit minutes from its implementation record and estimated the no-kit baseline from required custom Blender/Python work. **These are retrospective estimates, not independently timed measurements, an A/B benchmark, or guaranteed savings.** Geometry authoring remained custom; the agent's strongest benefits were **QA, texture packing, automated rendering, and hierarchy-safe export/round-trip validation**. Its contact-sheet presentation work still required custom scripts and even added some overhead.

Read the [complete independent report](demo/REPORT.md), [capability evaluation](demo/KIT_EVALUATION.md), [effort methodology](demo/EFFORT_ANALYSIS.md), and [improvement backlog](demo/IMPROVEMENT_BACKLOG.md). No Unity Editor import was performed; the proof is based on Blender validation and documented texture checks.


---

## Independent A/B workflow comparison — 58-part quadcopter

An additional independent agent ran a **plain Blender Python (`bpy`) baseline versus a Blender Agent Kit-guided workflow**, both constructing the same *58-component quadcopter concept* using Blender 5.2.4 LTS and CPU Cycles. Unlike the SupplyCrate/Sci-Fi retrospective effort estimates above, this comparison preserves **both implementation scripts, Blender scenes, renders, CLI reports and QA results**. The two implementations were independently authored, so this is a **real-world workflow comparison, not a controlled same-output speed benchmark**.

| Observed metric | Plain `bpy` | With Blender Agent Kit |
| --- | ---: | ---: |
| Agent turns | **2** | **4** (skill reading + QA remediation) |
| Recorded Blender execution time | **48.07 s**, one build/render/export pass | **30.63 s**, two passes (15.70 + 14.93 s) |
| Custom render/export pipeline boilerplate | **71 LOC** | **0 LOC** (agent-assessed classification) |
| QA errors under the **same** Unity `solid_prop` policy | **78 — FAIL** | **0 — PASS** after an initial **59-error** iteration |
| QA warnings in final state | 0 | **58 `uv1_overlap_unverified`** |
| Scene mesh count / triangles | 58 meshes / **2,776 tris** | 58 meshes / **5,528 tris** |
| Materials | **10** | **2** |
| FBX fresh-import parity | Not checked | **PASS: 5,528 → 5,528 tris**, no reported parent/transform mismatches |
| Skill-document reading | None | **~1,234 tokens estimated** from characters, *not API token telemetry* |

### What the benchmark demonstrated

- **Correctness:** An identical `run.py qa --target unity --asset-class solid_prop` audit found **58 missing UV1**, **18 unapplied-scale**, **1 material-budget**, and **1 pivot/root** issue in the plain-`bpy` output. The kit-guided first pass surfaced 59 errors (58 UV1 + 1 material-budget), and the agent corrected them on a second pass. Final QA passed with **zero errors**, but **UV1 island overlap remains unverified** on all 58 meshes.
- **Agent effort and complexity:** The kit offloaded scene inspection, QA, review rendering, Unity-target export, and round-trip verification; the agent reported eliminating **71 lines of pipeline boilerplate**. This did **not** reduce total authoring turns: **4 with the kit versus 2 without**, including skill onboarding and a fix loop.
- **Execution-time observation:** The recorded Blender compute totals were **36.3% lower** for the kit-guided runs (30.63 s versus 48.07 s). **These are not equivalent workloads**: the baseline performed three custom renders and an unchecked default FBX export; the kit runs included four-view review, QA, and fresh-import verification. The kit run also recorded **149.39 s elapsed including agent edits**, without a comparable end-to-end baseline elapsed-time measurement. Do not interpret the 36.3% as an isolated toolkit speedup.
- **Asset difference:** Both builds modeled the same 58-part architecture, but the final kit-guided output had more triangles, different shading/material organization, more hierarchy nodes, and a stronger verification bar. The experiment supports a **workflow-quality and verification** comparison, not a pixel-identical or geometry-identical performance result.

**Bottom line:** The agent using Blender Agent Kit delivered a validated, hierarchy-organized quadcopter with automated FBX parity evidence, while plain `bpy` stopped at a recognizable but QA-failing result. The trade-off was extra agent iterations and upfront documentation reading. The independent trial's earlier **74–80% / 55–63%** figures remain *estimated savings*, separate from these recorded A/B outcomes.

*Provenance:* Source: independent `quadcopter_assembly_benchmark_plain_bpy_vs_blender_agent_kit.html` and `quadcopter-blender-assets.zip` submission. The supplied package includes `comparison/benchmark_summary.json`, both build scripts and scenes, QA results for each run, final export verification and original render images. Full benchmark files are not yet published in this repository; the numbers above are from that submitted evidence, not a rerun by the maintainers.

## What can an agent do?

| Agent task | Support |
| --- | --- |
| Create procedural 3D props and modular assets from a brief | **Yes** — deterministic Blender/Python modeling workflow |
| Refine or modify an existing `.blend` scene | **Yes** |
| Create and validate LOD chains | **Yes** |
| Generate simplified collision proxies | **Yes** |
| Build pivots, hierarchies, sockets, and compound assets | **Yes** |
| Unwrap UV0 / UV1 and prepare baking workflows | **Yes** |
| Bake canonical PBR maps | **Yes** |
| Pack texture channels and resize maps deterministically | **Yes** |
| Rig articulated assets or characters | **Yes** — skill-guided workflow |
| Stage animation clips for export | **Yes** — skill-guided workflow |
| Render review / orthographic / range views | **Yes** |
| Validate geometry, LOD, UV, hierarchy, symmetry, dimensions, and budgets | **Yes** |
| Export FBX, GLB, or glTF using target-specific rules | **Yes** |
| Export one logical asset as multiple engine files | **Yes** — semantic bundles |
| Produce machine-readable QA / manifest evidence | **Yes** |
| Run repeatable headless / CI workflows | **Yes** |
| Generate arbitrary concept art from text | **No** — use an image-generation system upstream |
| Neural one-shot text-to-3D generation | **No** — this kit operates Blender deterministically |

## 3D and 2D scope

**3D asset creation is the primary product.** The modeling, LOD/collision, UV/baking, rigging/animation, review, QA, and export skills are designed to let agents operate on real Blender scenes and assets.

The kit also produces useful **2D production outputs** through Blender:

- BaseColor, Normal, Metallic, Roughness, AO, and packed texture maps;
- masks and channel-packed images;
- baked maps;
- review renders and orthographic views;
- deterministic resized/converted texture outputs.

General-purpose illustration, concept-art generation, or arbitrary text-to-image creation is intentionally outside the current scope.

## Core skill set

| Skill | Purpose |
| --- | --- |
| `blender-core` | Single entrypoint and routing for agent workflows |
| `blender-modeling` | Create/refine meshes, props, and modular kits |
| `blender-uv-baking` | UV0/UV1 workflows and canonical raw PBR baking |
| `blender-lod-collision` | LOD generation and collision proxies |
| `blender-rigging-animation` | Rigging, weights, and animation staging |
| `blender-asset-qa` | Production QA and structured evidence |
| `blender-bundle` | Compound multi-file asset delivery |
| `blender-batch` | Folder-scale headless processing and build caching |
| `blender-target-unity` | Unity-specific axes, export, and texture conventions |
| project profiles | Optional reusable production policies layered over a target |

## Command surface

The host-facing command surface is intentionally small:

```bash
python skills/core/blender-core/scripts/run.py doctor --device auto
python skills/core/blender-core/scripts/run.py inspect --blend asset.blend
python skills/core/blender-core/scripts/run.py qa --blend asset.blend --target unity --asset-class solid_prop
python skills/core/blender-core/scripts/run.py pack --target unity --profile urp --asset-id Prop01 --material Body --input-dir raw/ --out build/
python skills/core/blender-core/scripts/run.py export --blend asset.blend --target unity --profile urp --out build/
python skills/core/blender-core/scripts/run.py bundle --blend asset.blend --spec bundle.json --target unity --out build/
python skills/core/blender-core/scripts/run.py review --blend asset.blend --device auto --out review/ 
# Optional public JSON report on any subcommand:
python skills/core/blender-core/scripts/run.py pack --target unity --profile urp --asset-id Prop01 --material Body --input-dir raw/ --out build/ --result-json build/pack.report.json
```

Asset **creation itself is performed by the agent through Blender/Python**, using the modeling and specialist skills. The commands above provide the stable runtime around creation: discovery, inspection, QA, packing, export, bundle delivery, and review evidence.

## Architecture

```text
AI agent / developer
        ↓
Blender Agent Kit
        ↓
generic Blender core
        ↓
engine target (Unity today)
        ↓
optional reusable project profile / external profile JSON
        ↓
downstream asset-specific builders and game contracts
```

Core mechanics stay reusable. Engine semantics belong in target plugins. Project-specific dimensions, socket inventories, content IDs, and simulation rules stay downstream.

## Quick start

```bash
# Generic core + Unity target
python tools/install.py --agent all --targets unity

# Optional project-profile skills
python tools/install.py --agent all --targets unity --packs profiles

python tools/doctor.py --device auto
python tools/run_tests.py --suite host
python tools/run_tests.py --suite core
python tools/run_tests.py --suite targets
```

## Single agent entrypoint

```bash
python skills/core/blender-core/scripts/run.py doctor --device auto

python skills/core/blender-core/scripts/run.py inspect \
  --blend asset.blend

python skills/core/blender-core/scripts/run.py qa \
  --blend asset.blend --target unity --asset-class solid_prop

python skills/core/blender-core/scripts/run.py pack \
  --target unity --profile urp \
  --asset-id Prop01 --material Body \
  --input-dir raw/ --size 2048 --detect-normal-y \
  --out build/

python skills/core/blender-core/scripts/run.py export \
  --blend asset.blend --target unity --profile urp --out build/

python skills/core/blender-core/scripts/run.py bundle \
  --blend vehicle.blend --spec bundle.json --target unity --out build/

python skills/core/blender-core/scripts/run.py review \
  --blend asset.blend --device auto --out review/
```

## Production capabilities in v0.2

Compared with v0.1, v0.2 adds:

- strict Blender 5.2+ discovery and doctor behavior;
- strict Draft 2020-12 JSON Schema checks in CI;
- generic scene inventory shared by QA/export/evidence;
- fail-closed QA for empty scenes and malformed geometry;
- aggregate LOD/material budgets and LOD reduction ratios;
- intact-vs-`Damage_*` triangle accounting with configurable allowed LODs;
- configurable L/R mirror checks using triangle counts, mirrored bounds, and signed-volume magnitudes;
- configurable semantic dimension boxes, including optional LOD scoping and exclude patterns;
- profile-driven LOD aggregation exclusions for variant/collision hierarchies in multi-LOD authoring scenes;
- configurable UV-range/V-scroll checks, including per-face U-band selection for merged atlases;
- safe 8/16-bit channel packing plus Lanczos resizing via `--size`;
- optional normal-Y convention reporting, explicitly marked heuristic;
- hierarchy-safe static FBX Y-up prebaking for nested pivots and directional socket empties;
- optional temporary LOD-suffix stripping for multi-LOD authoring scenes, with collision-safe name stashing/restoration;
- zero-root export for selected compound parts;
- FBX embedded-image magic-header checks;
- semantic multi-file bundle export with authoring and export-coordinate inventories;
- stronger Blender fresh-import comparison;
- deterministic build hashes including tool/config identity;
- profile-driven review presets with close-up, 50/150/400m shots, per-LOD views, damage views, collision outline, and reference-FBX silhouette comparison;
- optional `tactical-vehicle` profile demonstrating reusable tracked-vehicle conventions without modifying the base Unity target.

## Unity static hierarchy export

For static MESH/EMPTY hierarchies, the Unity target uses:

```json
{
  "use_space_transform": false,
  "prebake_yup_hierarchy": true,
  "prebake_directional_patterns": ["Socket_*"],
  "apply_transform_static": false
}
```

This avoids Blender FBX `bake_space_transform` on nested hierarchies.

The exporter converts the authored Blender Z-up basis into a Unity-friendly Y-up/+Z-forward basis before FBX export:

- positions are transformed by `Rx(-90°)`;
- ordinary transform frames use a basis change `C · R · C⁻¹`;
- directional empties matching `prebake_directional_patterns` use `C · R`, preserving their authored forward/up vectors;
- mesh-local vertices are transformed by `C`;
- local matrices are reconstructed from converted world matrices, preserving depth ≥ 2 parent chains.

The authoring scene is restored immediately after export.

Blender's FBX importer shows a +90° X root wrapper when re-importing a Y-up FBX back into Blender's Z-up viewport. The generic round-trip verifier accounts for that importer presentation while verifying child local transforms, hierarchy, scale, triangle count, and embedded-image absence.

The prebake is intentionally **static-only**. Rigged/armature exports remain on the configured rigged FBX path and are not mutated by the static hierarchy conversion.

## Project profiles

A project profile is an in-memory overlay over an engine target. It can add:

- QA asset classes and budgets;
- naming rules;
- custom texture packing profiles;
- damage conventions;
- mirror/dimension/UV rules;
- bundle defaults;
- review presets.

The stored base target is never mutated.

The optional built-in profile is:

```text
plugins/profiles/blender-profile-tactical-vehicle/
```

It demonstrates reusable production conventions:

- heavy/light tracked vehicle LOD budgets;
- ≤ 0.50 reduction per LOD step;
- `Damage_*` permitted only in LOD0/LOD1;
- ground-contact checks;
- optional turret/gun hierarchy checks;
- BaseColor + Normal + Mask packing;
- profile-driven `station`/`kit` zero-root defaults;
- tactical review preset:
  - 1280×720;
  - 12m close-up;
  - 50m, 150m, 400m;
  - LOD0–3;
  - damage views;
  - collision outline.

Exact game-specific dimensions, socket inventories, simulation rules, faction/contact knowledge, content IDs, or prefab logic belong in downstream profile files.

### Minimal external profile example

A project-specific profile overlays a target in memory; it does not modify the generic toolkit or Unity target file. Save this as `project-profile.json` alongside your asset:

```json
{
  "name": "example-prop",
  "version": "1.0.0",
  "target_overrides": {
    "unity": {
      "qa": {
        "common": {"lod_exclude_patterns": ["*_COL_*"]},
        "asset_classes": {
          "example_prop": {
            "pivot_rule": "bottom_center_z0",
            "max_material_slots": 2,
            "required_parent_pairs": [
              {"child": "Socket_Front", "parent": "AssetRoot"}
            ]
          }
        }
      }
    }
  },
  "review_presets": {
    "hero": {
      "resolution": [1280, 720],
      "orthographic_views": ["front", "side", "top"],
      "primary_lod": 0,
      "collision_view": true
    }
  }
}
```

Use `--project-profile project-profile.json --asset-class example_prop` for QA, or `--preset hero` for review. Parent relationships use **objects with `child` and `parent` strings**, not positional arrays. The common collider exclusion is now automatic for recognized collision meshes; retaining the explicit example is supported for portability to older toolkit releases.

For Linux/macOS, use `python3` if `python` is not on `PATH`. If Blender was extracted to a nonstandard directory, set `BLENDER_EXECUTABLE=/absolute/path/to/blender` before invoking doctor or a subcommand. Run `run.py qa --help`, `run.py pack --help`, and similar commands to discover the exact accepted flags without starting Blender.

## Semantic bundle export

A bundle represents one logical asset that produces multiple engine files.

```json
{
  "schema_version": "1.0",
  "asset_id": "Vehicle01",
  "parts": [
    {
      "id": "chassis_lod0",
      "role": "chassis",
      "lod": 0,
      "collection": "Chassis_LOD0",
      "file": "Vehicle01_Chassis_LOD0.fbx"
    },
    {
      "id": "station_lod0",
      "role": "station",
      "lod": 0,
      "root": "Vehicle01_Station",
      "file": "Vehicle01_Station_LOD0.fbx",
      "zero_root_location": true
    }
  ]
}
```

Each part can be selected by exactly one collection or root hierarchy.

Downstream profiles can opt into temporary authoring-name normalization:

```json
{
  "export": {
    "strip_lod_suffix_on_export": true,
    "strip_lod_suffix_pattern": "_LOD[0-9]+$"
  }
}
```

When enabled, selected names such as `Turret_Pivot_LOD1` are exported as `Turret_Pivot`. Any unselected object already owning the base name is temporarily moved to an internal stash name; all selected and unselected names are restored after export. The exporter fails instead of guessing if stripping would create duplicate names inside the selected part.

The exporter records both:

- `assembly_inventory` — the authored assembled position;
- `inventory` — the actual export-coordinate state, including zeroed part roots when requested.

For every part it also records:

- total/intact/damage triangles;
- material counts;
- hierarchy and roots;
- Blender fresh-import result;
- child transform comparison;
- zero-root result;
- FBX PNG/JPEG magic-header scan.

`zero_root_location` is explicit and generic. Optional project profiles can declare `bundle_defaults.zero_root_location_roles` such as `station` and `kit`; the generic core itself does not assign meanings to role strings.

## QA

Implemented generic checks include:

- at least one mesh;
- applied/negative scale;
- non-manifold and boundary edges;
- inward closed-mesh winding using signed volume;
- UV0 and requested UV1 presence;
- aggregate per-LOD triangle/material budgets;
- monotonic LOD counts and maximum ratios;
- separate intact/damage triangle evidence;
- configurable damage-prefix and allowed-damage-LOD policy;
- required nodes and parent relationships;
- ground-axis contact tolerance;
- maximum vertex-group influences;
- simple bottom-center pivots;
- configurable mirror-pair checks;
- configurable semantic dimension boxes;
- configurable per-object/per-LOD UV bounds and V-span checks.

QA returns structured `evidence.symmetry`, `evidence.dimensions`, and `evidence.uv` data so downstream delivery tools do not need to parse prose.

### Explicit limitations

The pipeline does **not** yet prove:

- geometric UV-island non-overlap;
- texel density;
- collider convexity/decomposition quality;
- complete engine-side prefab/LODGroup construction.

When non-overlapping UV1 is requested, UV1 presence is enforced and the limitation is emitted as `uv1_overlap_unverified`.

## Texture packing

`shared/channel_pack` accepts allowlisted channel expressions such as:

```text
base_color.r
metallic
1-roughness
normal.g
```

No `eval()` is used.

`--size N` Lanczos-resamples every loaded raw map to `N×N` before packing, so different source resolutions can feed deterministic material outputs. Without `--size`, mismatched raw-map dimensions fail explicitly.

`--detect-normal-y` reports a green-channel directional-bias heuristic:

```json
{
  "convention": "opengl",
  "heuristic_only": true,
  "mean_green": 0.63,
  "confidence": 0.52
}
```

Pixel statistics cannot mathematically prove a tangent-space normal convention, so downstream pipelines should retain source/build evidence when available.

## Review rendering

A profile can define `review_presets` with:

- output resolution;
- orthographic views;
- primary LOD;
- close-up distance;
- range shots;
- azimuth/elevation/lens;
- LOD list;
- damage prefix and damage LODs;
- generic hierarchy `exclude_patterns` for ordinary review shots;
- optional `reference_exclude_patterns` for comparison imports;
- generic `variant_views` selected by hierarchy include/exclude patterns;
- collision view with a wireframe proxy over the primary LOD;
- optional reference FBX.

If the scene has no authored lights, automatic review lighting scales with the subject bounds so small props and larger assets receive comparable illumination instead of assuming a fixed vehicle-scale rig.

Example:

```bash
python skills/core/blender-core/scripts/run.py review \
  --blend vehicle.blend \
  --project-profile tactical-vehicle \
  --preset tactical \
  --reference-fbx reference.fbx \
  --out review/
```

## Generic review contact sheets

Use the separate, host-side `tools/review_compose.py` after rendering; this stage uses Pillow and does **not** require starting Blender. A data-driven specification can compose a multi-view sheet, LOD strip, distance grid, or collision comparison without hardcoded prop/vehicle/game assumptions.

```json
{
  "schema_version": "1.0",
  "columns": 2,
  "tile_size": [480, 270],
  "tiles": [
    {"path": "review_hero.png", "label": "Hero"},
    {"path": "review_front.png", "label": "Front"},
    {"path": "review_lod0_3m.png", "label": "LOD0", "evidence": "Triangles: supply from QA"},
    {"path": "review_collision_outline.png", "label": "Collision overlay"}
  ]
}
```

```bash
python tools/review_compose.py --spec review/sheet.json --out review/contact.webp
```

Labels and counts are supplied by the caller; the compositor never invents geometry or QA metrics. Missing or completely flat input images fail by default. Pillow is an optional host dependency for this step.

## Unity helper boundary

The optional `BlenderAssetPostprocessor.cs` remains a generic import helper for standard URP/HDRP assets. It deterministically binds manifests to importing assets and configures model/texture/material settings.

It does **not** own project-specific:

- prefab construction;
- LODGroup construction;
- collision policy;
- custom packed-mask shaders;
- content registration;
- ViewBinding or simulation state.

A downstream project may use a separate scratch-Unity verifier against bundle evidence without contaminating the generic Unity target.

## Documentation

- [DESIGN.md](DESIGN.md)
- [Unity target](plugins/targets/blender-target-unity/SKILL.md)
- [Asset QA](skills/core/blender-asset-qa/SKILL.md)
- [Semantic bundle export](skills/core/blender-bundle/SKILL.md)
- [Tactical vehicle profile](plugins/profiles/blender-profile-tactical-vehicle/SKILL.md)

## License

MIT — see [LICENSE](LICENSE).
