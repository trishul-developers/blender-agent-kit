# realtime-default production policy

This is Blender Agent Kit's reusable default **real-time asset production policy**. It is automatically applied by targets that declare:

```json
{ "default_policy": "realtime-default" }
```

It is deliberately separate from an engine target. Values here are toolkit production defaults, **not Unity/Godot/Unreal requirements**.

The policy currently supplies:

- generic applied-transform, manifold, winding and UV0 QA;
- default `solid_prop`, `open_sheet`, and `skinned_character` QA classes;
- default triangle/material/pivot/UV1/texel-density expectations;
- configurable LOD naming;
- configurable collider naming (including both `{name}_COL_{index:02d}` and legacy `COLLISION_{name}`);
- directional-empty convention used by hierarchy-safe export;
- LOD suffix stripping pattern and screen-transition defaults.

Resolution order is:

```text
engine target
  -> target's default production policy
  -> optional project profile
```

Project profiles remain the correct place for asset-line or project-specific budgets, dimensions, socket inventories, damage rules, custom texture layouts, and review presets.

The raw engine target is valid without this policy so engine semantics can be inspected/tested independently. Host commands such as `qa`, `inspect`, `review`, `export`, and `bundle` use the resolved target/policy contract.

## v0.2.3 migration note

Normal `run.py` commands remain backwards compatible because they call `load_profiled_target(...)`, which resolves the target's default policy automatically.

Python integrations that intentionally call low-level `load_target("unity")` now receive the **engine-only** target and should not expect `solid_prop`, generic LOD/collider naming, or production budgets there. Use `load_profiled_target("unity")` when you need the effective production contract.

Existing v0.2.x manifests remain schema-compatible. New manifests/results may additionally record the resolved `policy` name for provenance.
