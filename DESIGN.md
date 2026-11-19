# `blender-agent-kit` — Architecture & Design (`DESIGN.md`)

**Status:** v1.2 — Final Review / Ready for Phase 1 Scaffolding

**License:** MIT

**Target Runtime:** Blender 5.2 LTS (forward-compatible with 5.3)

**Dependency Boundary:** Host-side scripts (`tools/*`, `shared/runner.py`) use **Python 3.10+ stdlib only** (zero `pip install`); Blender-side scripts (`shared/*`) use **Blender 5.2 LTS built-ins only** (`bpy`, `bmesh`, `mathutils`, bundled `numpy`).

**Scope:** Engine-agnostic, headless-first Blender AI agent skill set with multi-agent support, automated CI tests, and a data-driven 2-file target-engine plugin system (**Unity** shipped first with URP/HDRP + 2-stage C# postprocessor; **Godot**, **Unreal**, **Web** drop in later with zero Python boilerplate).

## 1. Design Goals & Lessons Learned

This architecture synthesizes verified patterns from four existing Blender agent repositories and the [Agent Skills open standard](https://agentskills.io/specification):

| Reference | Keep / Adopt | Avoid / Fix | 
| ----- | ----- | ----- | 
| [EL4CTEO/blender-skills](https://github.com/EL4CTEO/blender-skills) | Dual Python `run(**kw) -> dict` + CLI `--` contract; `env_report.py`; `validate_skills.py` token linter; headless CI tests; `.agents/skills` + `.claude/skills` installers. | Hardcoding engine-specific export branches across core skills; duplicating Bash/PowerShell installer logic. | 
| [ifBars/blender-agent-studio](https://github.com/ifBars/blender-agent-studio) | Co-delivering editable `.blend` + deterministic Python build source; fresh-import round-trip verification; multiview contact sheets; `doctor` smoke test; bounded optional MCP. | Requiring Bun/Rust for core execution or limiting native installs to Claude Code and Codex. | 
| [arjun988/blender-skills](https://github.com/arjun988/blender-skills) | Central router skill and swappable art-direction style overlays. | Pure-Markdown skills without executable code/tests; Windows-hardcoded `.mcp.json`; 90+ overlapping startup entries. | 
| [kevinbadi/blender-skills](https://github.com/kevinbadi/blender-skills) | Optional showcase/turntable presets and Poly Haven helpers as add-ons. | Hardcoded desktop paths, mandatory paid API keys (Meshy), missing license, and out-of-sync docs. | 

### Core Architectural Principles

1. **Engine-Agnostic Core:** Core skills produce canonical metric assets (`1 BU = 1 m`), clean UVs (UV0 + optional UV1 lightmap), raw PBR maps (`BaseColor`, `Normal +Y`, `Metallic`, `Roughness`, `AO`), generic LOD chains, and deform-only rigs.

2. **Data-Driven Target Plugins (Zero Boilerplate):** One shared `channel_pack.py`, `exporter.py`, and `qa_checks.py` read declarative rules from each engine's `target.json`. Adding Godot or Unreal requires **2 files** (`target.json` + `SKILL.md`), with optional `hooks.py` and `editor/` escape hatches only for genuine edge cases.

3. **Single Agent Entrypoint:** Agents never assemble raw 10-flag `blender -b ...` commands. Every call goes through `python <blender-core>/scripts/run.py <subcommand> ...`, which delegates to `shared/runner.py`.

4. **Strict `agentskills.io` Compliance:** Every skill's `name` field matches its parent directory name (including prefixed target plugins like `blender-target-unity`), keeping `SKILL.md` under 500 lines / \~5,000 tokens.

## 2. Repository Structure

```
blender-agent-kit/
├── schemas/                            # Single-source JSON Schemas (CI + runtime + C#)
│   ├── target.schema.json              # Validates plugins/targets/*/target.json
│   └── asset-manifest.schema.json      # Validates *.asset.manifest.json (v1.0)
├── skills/core/                        # Engine-agnostic Blender skills (always installed)
│   ├── blender-core/                   # Router, single agent entrypoint, 5.x API rules
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── run.py                  # Thin host shim -> resolves kit root -> shared/runner.py
│   │   └── references/
│   │       └── api-changes-5x.md       # Blender 5.2+/5.3 bpy migration & gotchas
│   ├── blender-modeling/               # Metric modeling, pivots, modifier hygiene
│   ├── blender-uv-baking/              # UV0/UV1 + EMIT-pass canonical raw PBR baking
│   ├── blender-lod-collision/          # Generic LOD chains + multi-hull convex colliders
│   ├── blender-rigging-animation/      # Deform-only rigs, NLA action clips, loop checks
│   ├── blender-asset-qa/               # Asset-class QA + target.json rule evaluation
│   └── blender-batch/                  # Incremental folder batch jobs (build_hash cache)
├── plugins/
│   ├── targets/
│   │   └── blender-target-unity/       # Prefixed to satisfy agentskills.io & avoid collisions
│   │       ├── target.json             # Declarative URP/HDRP/FBX/LOD/QA spec
│   │       ├── SKILL.md                # name: blender-target-unity
│   │       └── editor/                 # Optional 2-stage Unity C# AssetPostprocessor
│   │           └── BlenderAssetPostprocessor.cs
│   ├── styles/                         # Optional drop-in art-direction overlays
│   └── bridges/                        # Optional bounded live-viewport MCP adapter
├── shared/                             # Data-driven runtime (host stdlib + Blender built-ins)
│   ├── paths.py                        # Cross-platform kit-root pointer resolver (stdlib)
│   ├── runner.py                       # Host orchestrator: discovery, flags, --result-json
│   ├── bootstrap.py                    # Blender-side shim: injects kit root into sys.path
│   ├── target_loader.py                # Loads & validates target.json against schema
│   ├── channel_pack.py                 # Safe-grammar + pure-stdlib 8/16-bit PNG encoder
│   ├── exporter.py                     # Per-format schema-to-RNA translator + round-trip check
│   ├── qa_checks.py                    # Asset-class mesh/UV checks + target.json evaluator
│   └── review_shots.py                 # Multiview & backface-culling Cycles contact sheets
├── tests/
│   ├── test_core_*.py                  # Engine-agnostic headless bpy unit tests
│   ├── test_installer.py               # Tier 1 tests for tools/install.py
│   └── test_target_contract.py         # Auto-discovers & tests plugins/targets/*/target.json
├── tools/
│   ├── install.py                      # Unified stdlib installer (junctions / symlinks / --copy)
│   ├── doctor.py                       # Blender 5.2+ discovery, add-on & GPU probe, smoke test
│   ├── validate_skills.py              # agentskills.io frontmatter, token & schema linter
│   ├── run_tests.py                    # Headless Blender test runner for local + CI
│   └── new_target.py                   # Scaffolds a new 2-file blender-target-<name> plugin
├── install/
│   ├── install.sh                      # 5-line POSIX wrapper around tools/install.py
│   └── install.ps1                     # 5-line PowerShell wrapper around tools/install.py
└── .github/workflows/ci.yml            # Pinned Blender 5.2 LTS headless CI matrix

```

## 3. Data-Driven Target Plugin Contract

Every engine under `plugins/targets/blender-target-<engine>/` requires only **two files**:

1. **`target.json`** — Declarative configuration validated by `schemas/target.schema.json` and interpreted by `shared/channel_pack.py`, `shared/exporter.py`, and `shared/qa_checks.py`.

2. **`SKILL.md`** — Concise agent instructions (`name: blender-target-<engine>`, matching parent directory per [agentskills.io](https://agentskills.io/specification)).

**Optional escape hatches** (omitted unless genuinely needed):

* `hooks.py` — Optional Python hooks (`pre_export(ctx)`, `post_export(ctx)`, `extra_qa(ctx)`) loaded dynamically only if present.

* `editor/` — Optional engine-side import helper (e.g., Unity C# `AssetPostprocessor`).

### 3.1 Reference `target.json` — Unity (v1)

> **Exporter RNA Translation Rule:** Keys in `target.json["export"]` are **format-agnostic schema fields**, never passed via `**kwargs` directly to `bpy.ops.export_scene.*`. `shared/exporter.py` owns a strict per-format schema-to-RNA translator (mapping e.g. `apply_scalings` → `apply_scale_options`, `apply_modifiers` → `use_mesh_modifiers`, `only_deform_bones` → `use_armature_deform_only`, `forward_axis`/`up_axis` → `axis_forward`/`axis_up` for FBX, vs. `export_yup=True` for glTF/GLB).

Grounded in [Blender-to-Unity FBX/Axis/Rigging checklists](https://app.cinevva.com/guides/blender-to-unity-export-checklist), [3D-Agent Export Guidelines](https://3d-agent.com/blender-ai/game-engine-export), [Unity LODGroup documentation](https://docs.unity3d.com/6000.2/Documentation/Manual/lod/lod-transitions-lod-group.html), and [Unity URP/HDRP channel packing](https://discussions.unity.com/t/transferring-game-assets-from-blender-to-unity/1588309):

```
{
  "name": "unity",
  "skill_name": "blender-target-unity",
  "version": "1.0.0",
  "default_profile": "urp",
  "units": { "system": "METRIC", "scale": 1.0 },
  "export": {
    "format": "fbx",
    "alt_static_format": "glb",
    "use_selection": true,
    "object_types": ["MESH", "EMPTY", "ARMATURE"],
    "forward_axis": "-Z",
    "up_axis": "Y",
    "apply_scalings": "FBX_SCALE_ALL",
    "apply_unit_scale": true,
    "apply_transform_static": true,
    "apply_transform_rigged": false,
    "apply_modifiers": true,
    "use_triangles": true,
    "use_tspace": true,
    "mesh_smooth_type": "FACE",
    "only_deform_bones": true,
    "add_leaf_bones": false,
    "bake_anim": true,
    "bake_anim_use_nla_strips": true,
    "bake_anim_use_all_actions": false,
    "bake_anim_simplify_factor": 0.0,
    "embed_textures": false
  },
  "naming": {
    "lod_pattern": "{name}_LOD{index}",
    "collider_pattern": "{name}_COL_{index:02d}",
    "texture_pattern": "textures/{asset_id}__{material_name}__{map}.png",
    "manifest_file": "{name}.asset.manifest.json"
  },
  "textures": {
    "normal_convention": "opengl",
    "fallback_constants": {
      "ao": 1.0,
      "alpha": 1.0,
      "metallic": 0.0,
      "roughness": 0.5,
      "detail_mask": 0.0
    },
    "profiles": {
      "urp": {
        "shader": "Universal Render Pipeline/Lit",
        "maps": {
          "albedo": {
            "unity_slot": "_BaseMap",
            "channels": ["base_color.r", "base_color.g", "base_color.b", "alpha"],
            "srgb": true,
            "bit_depth": 8,
            "unity_type": "Default"
          },
          "metallic_smoothness": {
            "unity_slot": "_MetallicGlossMap",
            "channels": ["metallic", "metallic", "metallic", "1-roughness"],
            "srgb": false,
            "bit_depth": 8,
            "unity_type": "Default",
            "unpremultiplied_rgba": true
          },
          "normal": {
            "unity_slot": "_BumpMap",
            "channels": ["normal.r", "normal.g", "normal.b"],
            "srgb": false,
            "bit_depth": 16,
            "unity_type": "NormalMap"
          },
          "ao": {
            "unity_slot": "_OcclusionMap",
            "channels": ["ao"],
            "srgb": false,
            "bit_depth": 8,
            "unity_type": "Default"
          }
        }
      },
      "hdrp": {
        "shader": "HDRP/Lit",
        "maps": {
          "base_map": {
            "unity_slot": "_BaseColorMap",
            "channels": ["base_color.r", "base_color.g", "base_color.b", "alpha"],
            "srgb": true,
            "bit_depth": 8,
            "unity_type": "Default"
          },
          "mask_map": {
            "unity_slot": "_MaskMap",
            "channels": ["metallic", "ao", "detail_mask", "1-roughness"],
            "srgb": false,
            "bit_depth": 8,
            "unity_type": "Default",
            "unpremultiplied_rgba": true
          },
          "normal": {
            "unity_slot": "_NormalMap",
            "channels": ["normal.r", "normal.g", "normal.b"],
            "srgb": false,
            "bit_depth": 16,
            "unity_type": "NormalMap"
          }
        }
      }
    }
  },
  "qa": {
    "common": {
      "require_applied_scale": true,
      "reject_negative_scale": true,
      "reject_non_manifold_edges": true,
      "reject_inward_normals": true,
      "require_uv0": true,
      "require_monotonic_lod_tris": true,
      "roundtrip_armature_scale_tolerance": 0.001,
      "texel_density_px_per_m": [256, 1024]
    },
    "asset_classes": {
      "solid_prop": {
        "reject_boundary_edges": true,
        "require_non_overlapping_uv1": true,
        "pivot_rule": "bottom_center_z0",
        "max_tris": { "lod0": 15000, "lod1": 7500, "lod2": 3000 },
        "max_material_slots": 2
      },
      "open_sheet": {
        "reject_boundary_edges": false,
        "require_non_overlapping_uv1": false,
        "pivot_rule": "none",
        "max_tris": { "lod0": 10000 },
        "max_material_slots": 2
      },
      "skinned_character": {
        "reject_boundary_edges": false,
        "require_non_overlapping_uv1": false,
        "max_bone_weights_per_vertex": 4,
        "pivot_rule": "bottom_center_z0",
        "max_tris": { "lod0": 60000, "lod1": 30000, "lod2": 12000 },
        "max_material_slots": 4
      }
    }
  }
}

```

### 3.2 Versioned `*.asset.manifest.json` Schema (`schemas/asset-manifest.schema.json`, v1.0)

Emitted by `shared/exporter.py` with collision-free multi-material texture naming (`textures/{asset_id}__{material_name}__{map}.png`) and explicit `uv1_source` handoff:

```
{
  "schema_version": "1.0",
  "asset_id": "prop_crate_industrial_01",
  "category": "solid_prop",
  "source_blend": "source/prop_crate_industrial_01.blend",
  "build_script": "source/build_prop_crate_industrial_01.py",
  "build_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015",
  "blender_version": "5.2.3 LTS",
  "target": "unity",
  "profile": "urp",
  "rig_type": "none",
  "uv1_source": "blender",
  "export_file": "prop_crate_industrial_01.fbx",
  "disable_unity_auto_mesh_lod": true,
  "lods": [
    { "name": "prop_crate_industrial_01_LOD0", "tri_count": 4200, "screen_relative_transition_height": 0.50 },
    { "name": "prop_crate_industrial_01_LOD1", "tri_count": 1900, "screen_relative_transition_height": 0.20 },
    { "name": "prop_crate_industrial_01_LOD2", "tri_count": 720,  "screen_relative_transition_height": 0.05 }
  ],
  "colliders": [
    { "node_name": "prop_crate_industrial_01_COL_01", "shape": "convex_mesh", "strip_renderer": true }
  ],
  "materials": [
    {
      "material_name": "M_Crate_Industrial",
      "shader": "Universal Render Pipeline/Lit",
      "textures": {
        "_BaseMap": "textures/prop_crate_industrial_01__M_Crate_Industrial__albedo.png",
        "_MetallicGlossMap": "textures/prop_crate_industrial_01__M_Crate_Industrial__metallic_smoothness.png",
        "_BumpMap": "textures/prop_crate_industrial_01__M_Crate_Industrial__normal.png",
        "_OcclusionMap": "textures/prop_crate_industrial_01__M_Crate_Industrial__ao.png"
      }
    }
  ],
  "textures": [
    { "material_name": "M_Crate_Industrial", "path": "textures/prop_crate_industrial_01__M_Crate_Industrial__albedo.png", "srgb": true, "bit_depth": 8, "normal_map": false, "max_size": 2048 },
    { "material_name": "M_Crate_Industrial", "path": "textures/prop_crate_industrial_01__M_Crate_Industrial__metallic_smoothness.png", "srgb": false, "bit_depth": 8, "normal_map": false, "max_size": 2048 },
    { "material_name": "M_Crate_Industrial", "path": "textures/prop_crate_industrial_01__M_Crate_Industrial__normal.png", "srgb": false, "bit_depth": 16, "normal_map": true, "max_size": 2048 },
    { "material_name": "M_Crate_Industrial", "path": "textures/prop_crate_industrial_01__M_Crate_Industrial__ao.png", "srgb": false, "bit_depth": 8, "normal_map": false, "max_size": 2048 }
  ]
}

```

### 3.3 Unity 2-Stage `BlenderAssetPostprocessor.cs` Contract (Phase 3)

To eliminate Unity's import-order race (where `OnPostprocessModel` runs before sibling textures finish importing) and URP Lit's smoothness-multiplier trap:

1. **Stage 1 (`OnPreprocessTexture` / `OnPreprocessModel`):**

   * Read sibling `*.asset.manifest.json` directly via `System.IO.File.ReadAllText` (never `AssetDatabase`).

   * Apply `TextureImporter` settings (`sRGBTexture`, `TextureImporterType.NormalMap`, `maxTextureSize`).

   * Apply `ModelImporter` settings (`generateMeshLods = !manifest.disable_unity_auto_mesh_lod` on Unity 6.2+, `generateSecondaryUV = (manifest.uv1_source == "unity_generate")`, `avatarSetup` from `rig_type`, `importAnimation`).

2. **Stage 2 (`OnPostprocessAllAssets`):**

   * Once all assets in the batch are imported, create/update URP/HDRP `.mat` files and assign textures.

   * **URP Lit Smoothness Fix:** Explicitly set `_Metallic = 1.0f`, `_Smoothness = 1.0f`, `_SmoothnessTextureChannel = 0` (Metallic Alpha), and enable shader keywords (`_METALLICSPECGLOSSMAP`, `_NORMALMAP`, `_OCCLUSIONMAP`) so URP's default `0.5` smoothness never halves the packed alpha channel.

   * Wire `LODGroup` screen transition heights from `manifest.lods`, convert `*_COL_*` nodes into colliders (stripping `MeshRenderer`), and override `GetVersion()` so postprocessor updates trigger clean reimports.

### 3.4 How Future Engines Plug In (Zero Core Changes)

* **Godot (`plugins/targets/blender-target-godot/`):** `target.json` sets `format: "glb"`, `normal_convention: "opengl"`, `orm: ["ao", "roughness", "metallic"]`, `collider_pattern: "{name}-convcolonly"`, `max_bone_weights_per_vertex: 4`. Zero Python code required.

* **Unreal (`plugins/targets/blender-target-unreal/`):** `target.json` sets `format: "fbx"`, `forward_axis: "-Y"`, `up_axis: "Z"`, `normal_convention: "directx"` (automatic green-channel flip in `shared/channel_pack.py`), `orm: ["ao", "roughness", "metallic"]`, `lod_pattern: "SM_{name}_LOD{index}"`, `collider_pattern: "UCX_{name}_{index:02d}"`, `max_bone_weights_per_vertex: 8`. Zero Python code required.

## 4. Headless Execution, Path Resolution & PBR Guardrails

### 4.1 Single Agent Entrypoint (`run.py` → `shared/runner.py`)

Agents **never** construct raw `blender -b ...` CLI commands. They call one thin stdlib shim bundled inside `blender-core`:

```
python <blender-core>/scripts/run.py export \
  --blend in.blend --target unity --profile urp --device auto --out build/

```

Behind the scenes, `shared/runner.py` owns the full headless lifecycle ([Blender CLI rules](https://renderday.com/blog/mastering-the-blender-cli); [EL4CTEO pipeline patterns](https://www.typingmind.com/skills/el4cteo-blender-pipeline-automation)):

1. **Cross-Platform Kit-Root Resolution (`shared/paths.py`):** Resolves `BLENDER_AGENT_KIT_ROOT` env var → `%LOCALAPPDATA%/blender-agent-kit/manifest.json` on Windows, or `$XDG_CONFIG_HOME/blender-agent-kit/manifest.json` / `~/.config/blender-agent-kit/manifest.json` on POSIX. Never assumes CWD or `PYTHONPATH`.

2. **Blender Discovery & Strict Flag Ordering:** Resolves Blender 5.2+ binary and verified add-ons from `doctor.py`, then invokes:

   ```
   blender -b [in.blend] --factory-startup [--addons <verified>] --python-exit-code 1 \
     -P <kit_root>/shared/bootstrap.py -- --module <mod> --result-json <tmp.json> [args...]
   
   ```

   `--factory-startup` always precedes `--addons`; `shared/bootstrap.py` injects `<kit_root>` into Blender's `sys.path` before importing `shared/*`.

3. **Structured `--result-json` Transport:** `runner.py` allocates a temp file for `--result-json`, reads and validates the JSON payload after exit, cleans up the temp file, and returns clean JSON to the agent (preserving raw Blender stdout/stderr in a log file returned on error, with an optional `@@JSON@@{...}` fallback).

4. **GPU Auto-Detection (`--device auto|gpu|cpu`):** `tools/doctor.py` probes OptiX/CUDA/HIP/Metal once. `auto` uses GPU locally for fast Cycles baking/renders and falls back cleanly to Cycles CPU in headless Linux CI.

5. **Blender 5.x API Cheat Sheet (`skills/core/blender-core/references/api-changes-5x.md`):** Documents 5.2+/5.3 breaking APIs (slotted actions / channelbags, `scene.compositing_node_group`, `BLENDER_EEVEE`, `mod.properties.inputs` for Geometry Nodes, removal of `bgl` and `bpy.props` dict access).

### 4.2 PBR Baking & Pure-Stdlib PNG Packing Guardrails

* **No `eval()` in `shared/channel_pack.py`:** Parses channel formulas (`base_color.r`, `1-roughness`, `metallic`) via a small allowlisted grammar, applying `fallback_constants` when optional maps are absent.

* **Pure-Stdlib 8/16-Bit PNG Encoder (Zero Color-Management Interference):** Never uses `image.save_render()` (which applies AgX/Filmic view transforms) or `image.save()` (which risks global bit-depth and alpha-zero RGB mutation). Instead, `shared/channel_pack.py` writes packed 8-bit and 16-bit unpremultiplied RGBA/RGB/L PNGs directly from Blender's bundled `numpy` arrays using a \~40-line `struct` + `zlib` PNG writer—zero pip dependencies, verified by a Tier 2 unit test for `(metallic=1.0, roughness=1.0)`.

* **Cycles `DIFFUSE` Metal Trap (`blender-uv-baking`):** Cycles' `DIFFUSE` bake multiplies albedo by `(1 - metallic)`, turning pure metals black. Canonical `BaseColor` and `Metallic` maps must always be baked via temporary Emission shader routing (`EMIT` pass).

## 5. Multi-Agent Installation (`tools/install.py`)

Per [agentskills.io client conventions](https://agentskills.io/client-implementation/adding-skills-support):

* **Single Zero-Dependency Python Installer:** `tools/install.py` (Python 3.10+ stdlib only) uses **Windows directory junctions** (no Admin or Developer Mode required), **POSIX symlinks** on Linux/macOS, and a **`--copy` fallback** for CI/container filesystems. Wrapped by 5-line `install/install.sh` and `install/install.ps1` shims.

* **Pointer Manifest:** Writes the cross-platform kit-root pointer (`%LOCALAPPDATA%/blender-agent-kit/manifest.json` or `$XDG_CONFIG_HOME` / `~/.config/blender-agent-kit/manifest.json`).

* **Targets Both Shared Paths:** Installs into `~/.agents/skills/` (Codex, Cursor, Gemini CLI, GitHub Copilot, OpenCode, Antigravity) and `~/.claude/skills/` (Claude Code), or `<project>/.agents/skills/` + `<project>/.claude/skills/` with `--project DIR`.

  ```
  python tools/install.py --agent all --targets unity --packs styles
  python tools/install.py --project /path/to/game-repo --targets unity --copy
  
  ```

## 6. Four-Tier Automated Testing & CI Strategy

| Tier | Command / Tool | What It Verifies | Runs In | 
| ----- | ----- | ----- | ----- | 
| **Tier 1 · Spec, Schema & Installer** | `python tools/validate_skills.py` + `pytest tests/test_installer.py` | Valid `SKILL.md` frontmatter (`name` == folder name, `<500` lines / `<5,000` tokens), `schemas/target.schema.json` & `schemas/asset-manifest.schema.json` validation, `tools/install.py` junction/symlink/`--copy` & pointer tests, trigger evals. | Every PR (no Blender needed) | 
| **Tier 2 · Core Headless `bpy`** | `python tools/run_tests.py --suite core` | Modeling, UV0/UV1 packing, `EMIT`-pass raw PBR baking, `(metallic=1.0, roughness=1.0)` unpremultiplied 8/16-bit PNG test, asset-class QA profiles (`solid_prop` vs `open_sheet`), LODs, rigging. | Every PR (cached Blender 5.2 LTS Linux tarball) | 
| **Tier 3 · Auto-Discovered Target Contract** | `python tools/run_tests.py --suite targets` | Loops over `plugins/targets/*/target.json`; runs channel packing → schema-to-RNA export → **fresh headless Blender re-import** verifying scale `1.0`, `roundtrip_armature_scale_tolerance: 0.001`, monotonic LODs, tangent space, single non-duplicated clips, and manifest schema validity. | Every PR (auto-covers future Godot/Unreal) | 
| **Tier 4 · Visual QA** | `python <blender-core>/scripts/run.py review --device auto` | Renders orthogonal + hero Cycles contact sheets and optional magenta backface-culling sheets. | Asset deliveries & releases | 

## 7. Phased Implementation Plan

1. **Phase 1 — Core Runtime, Schemas, Installer & CI:** `schemas/target.schema.json`, `schemas/asset-manifest.schema.json`, `shared/paths.py`, `shared/runner.py`, `shared/bootstrap.py`, `shared/target_loader.py`, `tools/doctor.py`, `tools/install.py` (+ `install.sh`/`install.ps1` + `tests/test_installer.py`), `tools/validate_skills.py`, `tools/run_tests.py`, `skills/core/blender-core/` (`SKILL.md`, `scripts/run.py`, `references/api-changes-5x.md`), and `.github/workflows/ci.yml`.

2. **Phase 2 — Shared Mechanics & Core Skills:** `shared/channel_pack.py` (safe grammar + pure-stdlib 8/16-bit PNG encoder), `shared/exporter.py` (per-format RNA translator + round-trip check), `shared/qa_checks.py` (asset-class profiles), `shared/review_shots.py`, and core skills (`modeling`, `uv-baking`, `lod-collision`, `rigging-animation`, `asset-qa`, `batch`) with Tier 2 tests.

3. **Phase 3 — Unity Target Plugin (v1):** `plugins/targets/blender-target-unity/target.json` (URP + HDRP), `SKILL.md`, 2-stage `editor/BlenderAssetPostprocessor.cs` (with URP `_Smoothness = 1.0f` fix), and Tier 3 contract tests passing in CI.

4. **Phase 4 — Extensibility & Add-Ons:** `tools/new_target.py` scaffolder for Godot/Unreal, optional `plugins/styles/` overlays, optional bounded MCP bridge, and multi-agent trigger evals.