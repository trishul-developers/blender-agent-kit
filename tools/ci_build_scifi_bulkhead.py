"""Source-only Sci-Fi bulkhead build for CI; preserves original agent trial.

The original demo builder renders the full catalog and 21-module corridor as
part of its default workflow. A CI smoke must not spend minutes on beauty
renders just to verify that the source still builds, validates and exports.
This driver directly reuses the same builder functions to create the canonical
representative bulkhead and saves it to a clean temporary directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def main() -> int:
    import bpy

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-textures", type=Path, required=True)
    parser.add_argument("--out-blend", type=Path, required=True)
    args = parser.parse_args(argv)

    builder_path = Path(__file__).resolve().parents[1] / "demo/SciFiKit/source/build_scifi_kit.py"
    spec = importlib.util.spec_from_file_location("independent_scifi_trial_builder", builder_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load independent demo builder: {builder_path}")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    builder.clear_scene()
    materials = list(builder.create_materials(args.raw_textures))
    builder.build_bulkhead_module(
        materials, include_all_lods=True, name_prefix="SF_Bulkhead_Arch",
    )
    destination = args.out_blend.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(destination))
    print(f"Saved independent-source representative Sci-Fi bulkhead: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
