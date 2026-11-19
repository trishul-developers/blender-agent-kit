# blender-agent-kit — Architecture and Design

**Status:** v0.2 candidate architecture, implemented on `feat/generic-production-pipeline-v0.2`

**Runtime:** Blender 5.2+; Python 3.10+ host tooling.

**Core rule:** reusable Blender behavior remains generic. Engine behavior belongs in target plugins. Reusable downstream conventions belong in optional project profiles. Exact game/simulation contracts remain in downstream repositories.

## 1. Architectural layers

```text
AI agent / developer
        │
        ▼
blender-core run.py
        │
        ▼
generic runtime
  runner / inspector / QA
  packer / exporter / bundle
  round-trip / review renderer
        │
        ├─────────────► engine target
        │                Unity: FBX/GLB, axes,
        │                standard URP/HDRP layouts
        │
        └─────────────► optional project profile
                         budgets, naming, texture layouts,
                         hierarchy conventions
```

The separation is deliberate. A tactical-vehicle project may require a chassis/station split, aggressive LOD ratios, ground contact, and a packed mask. Those are useful reusable conventions, but they are not universal Unity requirements. They therefore live in a profile overlay rather than `blender-target-unity`.

Likewise, exact TTE socket names, simulation sample heights, faction/contact disclosure rules, or damage-state semantics do not belong in this repository's generic core.

## 2. Repository structure

```text
schemas/
  target.schema.json
  asset-manifest.schema.json
  project-profile.schema.json
  bundle-spec.schema.json
  bundle-manifest.schema.json

skills/core/
  blender-core/
  blender-modeling/
  blender-uv-baking/
  blender-lod-collision/
  blender-rigging-animation/
  blender-asset-qa/
  blender-bundle/
  blender-batch/

plugins/
  targets/
    blender-target-unity/
  profiles/
    blender-profile-tactical-vehicle/

shared/
  paths.py
  runner.py
  bootstrap.py
  target_loader.py
  profile_loader.py
  scene_inspector.py
  qa_checks.py
  channel_pack.py
  exporter.py
  bundle_exporter.py
  review_shots.py
  version.py

tools/
  doctor.py
  doctor_blender.py
  install.py
  new_target.py
  run_tests.py
  validate_skills.py
```

## 3. Execution contract

Every Blender operation runs through:

```text
skills/core/blender-core/scripts/run.py
        ↓
shared.runner.run_blender_module()
        ↓
Blender --factory-startup -b [blend]
        ↓
shared/bootstrap.py
        ↓
requested module
        ↓
structured result JSON
```

Startup-affecting flags precede the optional input blend file. Blender failures preserve stdout/stderr in an error log. The doctor fails when Blender is older than 5.2 rather than returning a misleading successful status.

Public subcommands are:

- `doctor`
- `inspect`
- `qa`
- `pack`
- `export`
- `bundle`
- `review`

## 4. Target plugins

A target answers engine-level questions:

- supported export format;
- forward/up axes;
- static versus rigged transform handling;
- animation exporter flags;
- standard texture packing;
- target naming defaults;
- generic QA defaults.

Unity is the first target. Its standard profiles remain `urp` and `hdrp`.

Adding a project profile must not mutate the stored base target. `shared.profile_loader` loads an optional overlay, recursively merges it into an in-memory target copy, then validates the resulting target.

Currently supported export formats are FBX, GLB, and glTF. USD is intentionally not advertised until an exporter implementation exists.

## 5. Project-profile contract

Project profiles can be installed as optional skill packs or supplied as external JSON files.

A profile may provide `target_overrides.<engine>` with partial configuration. After merge, the complete target must still satisfy normal target validation.

The built-in `tactical-vehicle` profile exists as an integration example and reusable production profile. It demonstrates generic requirements derived from military-assets/TTE experience:

| Requirement | Generic implementation |
|---|---|
| Multiple files per logical asset | semantic bundle spec |
| Chassis/station/collision/wreck/kit roles | free-form bundle roles |
| LOD0-3 production budgets | profile-added asset classes |
| At least 50% reduction per LOD | `max_lod_ratio: 0.5` |
| Ground-plane agreement | axis/target/tolerance QA rule |
| Turret/gun pivot hierarchy | optional required-node/parent rules |
| BaseColor + Normal + packed Mask | `tactical_urp` texture profile |
| Deterministic evidence | bundle manifest + build hash + round-trip |
| Review images | automatically framed multiview renderer |

The profile deliberately does not encode exact TTE socket inventories, per-vehicle dimensions, contact-knowledge rules, factions, content IDs, or simulation fields.

## 6. Scene inventory

`shared.scene_inspector` is the common measurement layer. QA and exporters consume the same inventory instead of reimplementing mesh traversal.

For each object it records:

- name/type/parent;
- location/rotation/scale;
- inferred LOD index from object, ancestor, or collection names;
- triangle count;
- UV-layer names;
- material names;
- non-manifold and boundary-edge counts;
- signed volume for closed meshes;
- maximum vertex-group influences;
- world bounds.

The scene inventory also records:

- roots;
- aggregate world bounds;
- aggregate LOD triangle/material counts;
- recognized collider-like object names.

This inventory is machine-readable and returned by the `inspect` command.

## 7. QA behavior

QA is designed to fail closed for conditions it actually measures.

Implemented checks include:

- at least one mesh exists;
- negative/unapplied scale;
- >2-face non-manifold edges;
- boundary edges where forbidden;
- inward winding on closed meshes via signed volume;
- UV0 presence;
- UV1 presence when requested;
- aggregate per-LOD triangle budgets;
- aggregate per-LOD unique-material budgets;
- monotonic LOD triangle counts;
- optional maximum LOD reduction ratio;
- optional required node/pattern presence;
- optional required parent relationships;
- optional ground-axis contact tolerance;
- maximum vertex-group influences;
- basic bottom-center pivot validation for simple props.

### Known QA limitations

Geometric UV-island overlap detection is not yet implemented. If a class requests a non-overlapping UV1, the runtime enforces that UV1 exists and emits `uv1_overlap_unverified` rather than silently claiming overlap verification.

Texel-density measurement is not yet implemented.

Collision convexity/volume decomposition is not yet automatically proven. Collider nodes are inventoried and can be constrained by downstream profiles/bundle specs.

These limitations are intentionally explicit so documentation does not claim checks the code does not perform.

## 8. Texture packing

`shared.channel_pack` uses an allowlisted expression grammar such as:

```text
base_color.r
metallic
1-roughness
normal.g
```

No `eval()` is used.

Output PNGs are written directly from float arrays with `struct` + `zlib`, preserving 8/16-bit data and RGB values even when alpha is zero.

The public `pack` subcommand reads canonical raw PNG names from an input directory and applies either the base target profile or an optional project overlay.

The tactical profile demonstrates:

```text
BaseColor = RGB base color + alpha
Normal    = tangent normal
Mask      = R metallic, G AO, B detail/reserved, A smoothness
```

That layout is a downstream profile, not a change to standard URP.

## 9. Single-file export and round-trip

`shared.exporter`:

1. inventories the selected scene objects;
2. exports FBX/GLB/glTF using target translation;
3. writes an asset manifest from aggregate inventory;
4. calculates a build hash over source/build/profile inputs plus canonical tool/target metadata;
5. imports the result into a fresh Blender scene;
6. compares expected object names, parent relationships, triangle totals, and unit scale.

This is stronger than simply checking that "something imported".

The single-file manifest remains suitable for normal props/characters. Compound assets should use semantic bundles.

## 10. Semantic bundle export

A bundle is one logical asset composed of multiple exported files.

A bundle spec selects each part by exactly one Blender collection or root hierarchy. Roles are intentionally free-form.

Example:

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
      "id": "collision",
      "role": "collision",
      "collection": "Collision",
      "file": "Vehicle01_Collision.fbx"
    }
  ]
}
```

Every part gets:

- independent export;
- source inventory;
- triangle/material totals;
- fresh Blender re-import;
- missing-object comparison;
- parent comparison;
- scale check;
- triangle-count comparison.

The resulting `*.bundle.manifest.json` becomes reusable evidence for delivery tooling.

This abstraction directly supports production patterns learned from military-assets without making the core know what a tank, wreck, or weapon station is.

## 11. Review rendering

`shared.review_shots` computes scene bounds, frames the asset automatically, creates lighting only when needed, and renders deterministic views:

- hero;
- front;
- side;
- top;
- optional rear.

Project-specific distance/readability render presets are intentionally not hard-coded. A downstream project can call the same renderer with its own camera/delivery policy.

## 12. Unity postprocessor boundary

The optional Unity `BlenderAssetPostprocessor.cs`:

- deterministically chooses a manifest only when it references the importing asset;
- configures model import settings;
- configures texture import settings;
- creates/updates standard URP/HDRP materials from recognized standard-profile filenames;
- prevents standard smoothness multiplier mistakes.

It does not currently:

- build complete project prefabs;
- construct project-specific LODGroups;
- generate project-specific colliders;
- implement ViewBinding/content registration;
- understand custom tactical `Mask` semantics.

Those responsibilities belong to a downstream Unity import pipeline or a future explicitly scoped generic feature.

For TTE specifically, FBX/PNG plus manifests/evidence should cross the boundary; TTE remains responsible for production prefabs, materials, LODGroups, and bindings.

## 13. Deterministic build identity

Build hashes include file content plus canonical metadata such as:

- kit version;
- Blender version;
- effective merged target configuration;
- selected texture profile;
- project-profile identity;
- bundle spec where relevant.

Callers can additionally list deterministic build scripts and source inputs.

This makes cache/evidence identity sensitive to configuration and tooling changes, not only to a generated `.blend`.

## 14. Testing and CI

Tier 1 runs on Ubuntu and Windows and checks:

- skill metadata;
- every JSON Schema document;
- target instances;
- project profiles and their merged target validity;
- channel packing and PNG bytes;
- installer behavior;
- project-profile isolation;
- bundle-spec validation;
- build-hash metadata sensitivity.

CI installs `jsonschema` for strict Draft 2020-12 validation; runtime remains usable without it.

Tier 2 runs Blender 5.2 headlessly and covers:

- compliant solid-prop QA;
- solid/open-sheet distinction;
- empty-scene fail-closed behavior;
- inward-normal detection;
- monotonic LOD failure;
- semantic bundle FBX export + fresh re-import.

Tier 3 auto-discovers target plugins and runs their single-file exporter round-trip.

## 15. Remaining work

The next useful improvements are:

1. geometric UV-overlap and texel-density measurement;
2. a generic collision QA module for convexity, hull counts, and target-specific proxy naming;
3. optional engine-side bundle verification in a scratch Unity project;
4. configurable review-camera presets for tactical-distance/silhouette testing;
5. a real executable folder batch scheduler around the existing build hashes;
6. richer manifest material semantics so the Unity helper never relies on filename inference;
7. downstream TTE/military-assets profile files containing their exact contracts, maintained in those repositories rather than the generic core.

The design goal is not to absorb downstream projects. It is to make their repeated technical asset requirements declarative, testable, and reusable while keeping project-specific truth where it belongs.
