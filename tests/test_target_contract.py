"""Tier 3 auto-discovered target contract tests (loops over plugins/targets/*/target.json)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from shared.exporter import run as run_export
from shared.target_loader import list_targets


def run() -> dict:
    import bpy

    targets = list_targets()
    assert targets, "No target plugins found under plugins/targets/"
    results: dict[str, dict] = {}

    for target_name in sorted(targets.keys()):
        bpy.ops.wm.read_factory_settings(use_empty=False)
        with tempfile.TemporaryDirectory(prefix=f"bak_t3_{target_name}_") as tmp:
            res = run_export(
                target=target_name,
                out_dir=tmp,
                asset_id=f"contract_{target_name}",
                verify_roundtrip=True,
            )
            assert res["status"] == "ok", f"Target '{target_name}' failed round-trip: {res}"
            assert Path(res["artifacts"]["export"]).is_file()
            assert Path(res["artifacts"]["manifest"]).is_file()
            results[target_name] = {"passed": True, "roundtrip": res["roundtrip"]}

    return {"status": "ok", "targets_tested": sorted(results.keys()), "results": results}
