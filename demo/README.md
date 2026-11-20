# Canonical Blender Agent Kit demonstrations

As of the v0.2.3 release line, **`demo/` is the canonical reproducible showcase lineage**.

These demonstrations were originally authored by an independent agent against v0.2.1. Their original reports, renders, scenes, and provenance remain preserved. Current CI does not rewrite that historical evidence: it regenerates source-bound assets in a clean temporary directory and validates the current toolkit against them.

## Canonical demos

### SupplyCrate

```bash
python demo/SupplyCrate/run_demo.py --mode full --clean
```

The full entrypoint regenerates deterministic source textures, builds the Blender scene, runs inspect/QA, Unity URP packing, verified semantic bundle export, review rendering, and the six showcase sheets.

CI uses the faster source-bound smoke path:

```bash
python demo/SupplyCrate/run_demo.py --mode smoke --clean
```

### Helios Conduit / SciFiKit

```bash
python demo/SciFiKit/run_demo.py --mode full --clean
```

The full entrypoint regenerates the trim/emissive source maps, standalone bulkhead, module catalog, assembled corridor, inspect/QA, both Unity URP material packs, verified bundle export, review evidence, and five showcase sheets.

CI uses a representative bulkhead smoke build:

```bash
python demo/SciFiKit/run_demo.py --mode smoke --clean
```

## Output and provenance

By default, regenerated output is written under:

```text
build/canonical-demos/
  SupplyCrate/
  SciFiKit/
```

This keeps generated scenes, textures, renders, exports, and reports out of the source/evidence directories. Pass `--out` to use another working directory and `--blender` (or `BLENDER_EXECUTABLE`) to select Blender.

The checked-in `demo/*/evidence` directories remain the original independent-trial evidence. A new reproduction must be evaluated from its own output directory; do not overwrite historical reports and then present them as original evidence.

## Historical `demos/` directory

The separate top-level `demos/` tree is the **historical v0.2.1 showcase/prototype lineage**. It is retained for provenance and backwards links, but it is no longer the canonical reproduction path. See [../demos/README.md](../demos/README.md).
