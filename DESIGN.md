# blender-agent-kit — Architecture and Design

**Status:** v0.2 candidate architecture on `feat/generic-production-pipeline-v0.2`

**Runtime:** Blender 5.2+; Python 3.10+ host tooling.

**Core rule:** Blender mechanics stay generic; engine semantics live in targets; reusable downstream conventions live in optional profiles; exact game/simulation truth remains downstream.

## 1. Layering

```text
AI agent / developer
        ↓
blender-core run.py
        ↓
generic runtime
  runner
  scene inspector
  QA primitives
  channel packer
  exporter
  semantic bundle exporter
  round-trip evidence
  review renderer
        ↓
engine target
  Unity today
        ↓
optional project profile
        ↓
downstream repo builder / exact contract
```

A reusable tactical profile may know that a tracked vehicle uses multiple LODs, damage siblings, ground contact, or a packed mask. It must not know a game's hidden simulation state, faction logic, exact content IDs, or per-vehicle truth.

## 2. Generic scene inventory

`shared.scene_inspector` is the single measurement layer consumed by QA and exporters.

For every object it records:

- name, type, parent;
- local and world location;
- local rotation and scale;
- local 4×4 matrix;
- world +Y and +Z basis vectors;
- inferred LOD index from object, ancestor, or collection names.

For meshes it additionally records:

- triangle count;
- material names/slots;
- UV layer names;
- per-layer U/V min, max, and span;
- non-manifold and boundary-edge counts;
- signed volume for closed meshes;
- maximum vertex-group influences;
- world bounds;
- configurable damage classification.

LOD aggregates record:

- total triangles;
- intact triangles;
- damage triangles;
- mesh/damage-mesh counts;
- unique materials;
- damage object names.

This machine-readable inventory is returned by `inspect`, embedded in bundle evidence, and reused by QA.

## 3. Target plugin contract

An engine target answers only engine-level questions:

- export format;
- axes;
- FBX/glTF options;
- texture conventions;
- generic naming;
- baseline QA classes.

Unity is the first target, with standard URP/HDRP profiles.

Supported export formats are FBX, GLB, and glTF. USD remains unadvertised until implemented.

## 4. Project profiles

`shared.profile_loader` deep-merges an optional profile overlay into an in-memory copy of the target, validates the merged target, and leaves the stored base target unchanged.

Profiles may add:

- target texture profiles;
- QA classes;
- damage policy;
- symmetry rules;
- semantic dimension boxes;
- UV rules;
- bundle defaults;
- review presets.

External profile JSON files are supported, allowing an exact downstream project contract to remain in that project's repository.

## 5. Static Unity hierarchy conversion

### Problem

Blender FBX `bake_space_transform=True` is unsuitable for deeply nested static pivot/socket hierarchies because it can alter local transforms. Simply disabling it can leave a root axis rotation for engines that expect an identity authoring root.

### Implemented approach

The Unity target declares:

```json
{
  "forward_axis": "-Z",
  "up_axis": "Y",
  "use_space_transform": false,
  "prebake_yup_hierarchy": true,
  "prebake_directional_patterns": ["Socket_*"],
  "apply_transform_static": false
}
```

For static MESH/EMPTY exports, `shared.exporter` temporarily applies a coordinate-basis conversion with `C = Rx(-90°)`.

For every selected object it captures the authored world matrix.

It then computes:

- world position: `C · p`;
- ordinary transform-frame rotation: `C · R · C⁻¹`;
- directional EMPTY rotation when its name matches a configured pattern: `C · R`;
- mesh-local vertices: `C · v`.

Converted world matrices are turned back into locals using:

```text
local' = inverse(parent_world') · world'
```

This parent-world reconstruction is what preserves depth ≥ 2 chains.

The authoring scene's mesh data, parent inverse, and local matrices are restored after the export context exits.

### Static-only boundary

This prebake is disabled when the export is rigged or contains an armature. Rigged assets stay on their configured rigged FBX path. Extending basis prebaking to armatures is a separate future feature because bind/rest matrices require a different proof contract.

### Blender round-trip interpretation

A Y-up FBX imported back into Blender is displayed through Blender's Z-up convention, producing a +90° X root wrapper. The generic verifier therefore:

- validates object presence and parents;
- validates scale;
- compares non-root exported child local matrices;
- validates the expected Blender root-axis wrapper when a zero-root Y-up FBX is re-imported;
- validates triangle totals;
- scans the binary FBX for embedded PNG/JPEG headers.

A downstream Unity verifier can then prove identity roots and exact forward/up axes using Unity's default ModelImporter.

## 6. Semantic bundle export

A bundle is a logical asset composed of multiple exported files.

A part selects exactly one:

- Blender collection; or
- object root and its descendant hierarchy.

A part may declare:

```json
{
  "id": "station_lod0",
  "role": "station",
  "lod": 0,
  "root": "Vehicle_Station",
  "file": "Vehicle_Station_LOD0.fbx",
  "zero_root_location": true
}
```

`zero_root_location` temporarily zeroes that part root for export and restores its assembled authoring location immediately afterward.

The bundle manifest records:

- `assembly_inventory` — authored assembled state;
- `inventory` — actual export-coordinate state;
- role/LOD/file/root;
- total/intact/damage triangles;
- material counts;
- round-trip evidence;
- no-embedded-image result.

For projects that keep several LOD hierarchies in one Blender file, the export target can optionally declare `strip_lod_suffix_on_export` plus a regex such as `_LOD[0-9]+# blender-agent-kit — Architecture and Design

**Status:** v0.2 candidate architecture on `feat/generic-production-pipeline-v0.2`

**Runtime:** Blender 5.2+; Python 3.10+ host tooling.

**Core rule:** Blender mechanics stay generic; engine semantics live in targets; reusable downstream conventions live in optional profiles; exact game/simulation truth remains downstream.

## 1. Layering

```text
AI agent / developer
        ↓
blender-core run.py
        ↓
generic runtime
  runner
  scene inspector
  QA primitives
  channel packer
  exporter
  semantic bundle exporter
  round-trip evidence
  review renderer
        ↓
engine target
  Unity today
        ↓
optional project profile
        ↓
downstream repo builder / exact contract
```

A reusable tactical profile may know that a tracked vehicle uses multiple LODs, damage siblings, ground contact, or a packed mask. It must not know a game's hidden simulation state, faction logic, exact content IDs, or per-vehicle truth.

## 2. Generic scene inventory

`shared.scene_inspector` is the single measurement layer consumed by QA and exporters.

For every object it records:

- name, type, parent;
- local and world location;
- local rotation and scale;
- local 4×4 matrix;
- world +Y and +Z basis vectors;
- inferred LOD index from object, ancestor, or collection names.

For meshes it additionally records:

- triangle count;
- material names/slots;
- UV layer names;
- per-layer U/V min, max, and span;
- non-manifold and boundary-edge counts;
- signed volume for closed meshes;
- maximum vertex-group influences;
- world bounds;
- configurable damage classification.

LOD aggregates record:

- total triangles;
- intact triangles;
- damage triangles;
- mesh/damage-mesh counts;
- unique materials;
- damage object names.

This machine-readable inventory is returned by `inspect`, embedded in bundle evidence, and reused by QA.

## 3. Target plugin contract

An engine target answers only engine-level questions:

- export format;
- axes;
- FBX/glTF options;
- texture conventions;
- generic naming;
- baseline QA classes.

Unity is the first target, with standard URP/HDRP profiles.

Supported export formats are FBX, GLB, and glTF. USD remains unadvertised until implemented.

## 4. Project profiles

`shared.profile_loader` deep-merges an optional profile overlay into an in-memory copy of the target, validates the merged target, and leaves the stored base target unchanged.

Profiles may add:

- target texture profiles;
- QA classes;
- damage policy;
- symmetry rules;
- semantic dimension boxes;
- UV rules;
- bundle defaults;
- review presets.

External profile JSON files are supported, allowing an exact downstream project contract to remain in that project's repository.

## 5. Static Unity hierarchy conversion

### Problem

Blender FBX `bake_space_transform=True` is unsuitable for deeply nested static pivot/socket hierarchies because it can alter local transforms. Simply disabling it can leave a root axis rotation for engines that expect an identity authoring root.

### Implemented approach

The Unity target declares:

```json
{
  "forward_axis": "-Z",
  "up_axis": "Y",
  "use_space_transform": false,
  "prebake_yup_hierarchy": true,
  "prebake_directional_patterns": ["Socket_*"],
  "apply_transform_static": false
}
```

For static MESH/EMPTY exports, `shared.exporter` temporarily applies a coordinate-basis conversion with `C = Rx(-90°)`.

For every selected object it captures the authored world matrix.

It then computes:

- world position: `C · p`;
- ordinary transform-frame rotation: `C · R · C⁻¹`;
- directional EMPTY rotation when its name matches a configured pattern: `C · R`;
- mesh-local vertices: `C · v`.

Converted world matrices are turned back into locals using:

```text
local' = inverse(parent_world') · world'
```

This parent-world reconstruction is what preserves depth ≥ 2 chains.

The authoring scene's mesh data, parent inverse, and local matrices are restored after the export context exits.

### Static-only boundary

This prebake is disabled when the export is rigged or contains an armature. Rigged assets stay on their configured rigged FBX path. Extending basis prebaking to armatures is a separate future feature because bind/rest matrices require a different proof contract.

### Blender round-trip interpretation

A Y-up FBX imported back into Blender is displayed through Blender's Z-up convention, producing a +90° X root wrapper. The generic verifier therefore:

- validates object presence and parents;
- validates scale;
- compares non-root exported child local matrices;
- validates the expected Blender root-axis wrapper when a zero-root Y-up FBX is re-imported;
- validates triangle totals;
- scans the binary FBX for embedded PNG/JPEG headers.

A downstream Unity verifier can then prove identity roots and exact forward/up axes using Unity's default ModelImporter.

## 6. Semantic bundle export

A bundle is a logical asset composed of multiple exported files.

A part selects exactly one:

- Blender collection; or
- object root and its descendant hierarchy.

A part may declare:

```json
{
  "id": "station_lod0",
  "role": "station",
  "lod": 0,
  "root": "Vehicle_Station",
  "file": "Vehicle_Station_LOD0.fbx",
  "zero_root_location": true
}
```

`zero_root_location` temporarily zeroes that part root for export and restores its assembled authoring location immediately afterward.

The bundle manifest records:

- `assembly_inventory` — authored assembled state;
- `inventory` — actual export-coordinate state;
- role/LOD/file/root;
- total/intact/damage triangles;
- material counts;
- round-trip evidence;
- no-embedded-image result.

. Selected objects are temporarily renamed to their engine-contract names, unselected collisions are stashed, and all names are restored in `finally`. Duplicate stripped names inside the selected export set are a hard error.

Role names remain free-form. The generic core does not hardcode `station` or `kit`; a profile can declare:

```json
{
  "bundle_defaults": {
    "zero_root_location_roles": ["station", "kit"]
  }
}
```

## 7. QA contract

QA fails closed for checks it claims to perform.

Implemented:

- non-empty mesh scene;
- negative/unapplied scale;
- non-manifold/boundary edges;
- inward closed-mesh winding via signed volume;
- UV0/UV1 presence;
- per-LOD aggregate triangle budgets;
- per-LOD unique material budgets;
- monotonic LOD counts;
- maximum LOD ratios;
- intact and damage triangle evidence;
- damage allowed-LOD policy;
- required nodes/patterns;
- required child/parent relations;
- ground-axis contact;
- maximum vertex-group influences;
- simple bottom-center pivot rule;
- mirror-pair triangle/bounds/absolute-volume checks;
- semantic dimension-box checks with optional LOD scoping and exclude patterns;
- configurable U/V bounds and V-span checks.

Optional checks return structured evidence:

```text
evidence.symmetry
evidence.dimensions
evidence.uv
```

### Known limits

Not yet implemented:

- geometric UV-island overlap;
- texel-density measurement;
- generic collision convexity/decomposition proof.

When non-overlapping UV1 is requested, QA enforces UV1 presence and reports `uv1_overlap_unverified`.

## 8. PBR channel packing

Expressions are parsed by an allowlist grammar; no `eval()` is used.

The direct PNG writer preserves 8/16-bit output and RGB values at alpha zero.

`--size` enables deterministic Lanczos3 resampling before packing, including normalizing differently sized source maps.

`--detect-normal-y` produces a statistical green-channel bias report. The report always marks itself `heuristic_only` because pixels cannot prove tangent-space convention in the general case.

## 9. Review evidence

`shared.review_shots` supports ordinary automatically framed views and profile-defined presets.

Preset fields include:

- output resolution;
- orthographic view list;
- primary LOD;
- `closeup_distance_m`;
- `range_shots_m`;
- LOD list;
- azimuth/elevation/lens;
- damage prefix and damage LODs;
- collision view;
- optional reference FBX.

The built-in tactical profile demonstrates:

- 1280×720;
- 12m close-up;
- 50m, 150m, 400m;
- 45° azimuth/elevation;
- LOD0–3;
- damage views;
- collision outline.

Reference FBXs can be imported temporarily for a side-by-side silhouette render and then removed from the scene.

## 10. Deterministic build identity

Build hashes include file bytes plus canonical metadata such as:

- kit version;
- Blender version;
- effective merged target;
- texture profile;
- project profile;
- bundle spec.

Callers can list additional build scripts and source inputs.

## 11. Unity helper boundary

The generic Unity postprocessor:

- deterministically chooses only a manifest that references the importing asset;
- configures model import;
- configures texture import;
- creates/updates standard URP/HDRP materials.

It does not own:

- game-specific prefabs;
- LODGroups;
- collision construction;
- custom tactical shader semantics;
- content IDs;
- simulation bindings.

A downstream scratch-Unity verifier may consume bundle evidence to prove project-specific root/pivot/socket contracts without changing the generic target.

## 12. Tests and CI

Tier 1 on Ubuntu + Windows covers:

- skill metadata;
- JSON Schema documents/instances;
- target/profile merge validity;
- channel expressions and PNG bytes;
- Lanczos resizing;
- normal-Y heuristic semantics;
- bundle-spec validation;
- installer behavior;
- export-option translation.

Tier 2 on Blender 5.2 covers:

- solid/open-sheet QA;
- empty fail-closed behavior;
- inward normals;
- LOD monotonicity;
- damage LOD leakage;
- mirror-bounds failure;
- nested station → turret → gun → barrel/socket FBX export;
- temporary LOD-suffix stripping with unselected-name collision stashing/restoration;
- LOD0-scoped dimension checks that exclude wreck geometry;
- authoring-root restoration;
- zero-root semantic export;
- Blender fresh-import hierarchy/local-transform proof;
- no embedded images.

Tier 3 auto-discovers targets and runs target export contracts.

## 13. Remaining work

The highest-value remaining generic work is:

1. geometric UV-overlap detection;
2. texel-density measurement;
3. collision convexity/hull-count/proxy QA;
4. generic scratch-engine bundle verification beyond project-specific downstream adapters;
5. executable incremental folder batch scheduling;
6. richer manifest material semantics that remove filename inference from engine helpers;
7. proven armature/rigged coordinate-prebake support if a target requires it.

The design goal is not to absorb downstream projects. It is to turn repeated technical asset requirements into reusable, declarative, testable primitives while leaving exact project truth where it belongs.
