"""Host delivery orchestration must gate expensive stages on QA."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import deliver

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "skills/core/blender-core/scripts/run.py"


def _entrypoint():
    spec = importlib.util.spec_from_file_location("bak_deliver_entry", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeliverTests(unittest.TestCase):
    def test_qa_failure_skips_review_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            blend = Path(directory) / "asset.blend"
            blend.write_bytes(b"placeholder")
            calls = []

            def fake(module_name, **kwargs):
                calls.append(module_name)
                if module_name == "shared.scene_inspector":
                    return {"status": "ok", "inventory": {"mesh_count": 1}}
                if module_name == "shared.qa_checks":
                    return {
                        "status": "ok",
                        "passed": False,
                        "errors": [{"code": "pivot_rule"}],
                        "warnings": [],
                    }
                raise AssertionError(f"expensive stage should not execute: {module_name}")

            with patch.object(deliver, "run_blender_module", side_effect=fake):
                result = deliver.run(
                    blend_file=str(blend),
                    out_dir=str(Path(directory) / "out"),
                    kit_root=ROOT,
                )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failed_stage"], "qa")
            self.assertEqual(calls, ["shared.scene_inspector", "shared.qa_checks"])
            self.assertTrue(result["qa_gate"]["expensive_stages_skipped"])
            self.assertEqual([x["name"] for x in result["stages"]], ["inspect", "qa"])
            self.assertTrue(all(x["duration_ms"] >= 0 for x in result["stages"]))

    def test_success_reuses_existing_commands_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            blend = Path(directory) / "asset.blend"
            blend.write_bytes(b"placeholder")
            calls = []

            def fake(module_name, **kwargs):
                calls.append((module_name, list(kwargs.get("module_args") or []), kwargs.get("blend_file")))
                if module_name == "shared.scene_inspector":
                    return {"status": "ok", "inventory": {}}
                if module_name == "shared.qa_checks":
                    return {"status": "ok", "passed": True, "errors": [], "warnings": []}
                if module_name == "shared.review_shots":
                    return {"status": "ok", "style": "technical", "artifacts": {"hero": "hero.png"}}
                if module_name == "shared.exporter":
                    return {"status": "ok", "roundtrip": {"passed": True}}
                raise AssertionError(module_name)

            with patch.object(deliver, "run_blender_module", side_effect=fake):
                result = deliver.run(
                    blend_file=str(blend),
                    target="unity",
                    asset_class="solid_prop",
                    asset_id="Demo",
                    out_dir=str(Path(directory) / "out"),
                    kit_root=ROOT,
                )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                [x[0] for x in calls],
                ["shared.scene_inspector", "shared.qa_checks", "shared.review_shots", "shared.exporter"],
            )
            self.assertIn("--style", calls[2][1])
            self.assertIn("technical", calls[2][1])
            self.assertTrue(result["qa_gate"]["passed"])
            self.assertGreaterEqual(result["duration_ms"], 0)

    def test_pack_is_opt_in_and_requires_material_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            blend = Path(directory) / "asset.blend"
            blend.write_bytes(b"placeholder")
            raw = Path(directory) / "raw"
            raw.mkdir()

            def fake(module_name, **kwargs):
                if module_name == "shared.scene_inspector":
                    return {"status": "ok", "inventory": {}}
                if module_name == "shared.qa_checks":
                    return {"status": "ok", "passed": True}
                raise AssertionError(f"pack preflight should stop before {module_name}")

            with patch.object(deliver, "run_blender_module", side_effect=fake):
                result = deliver.run(
                    blend_file=str(blend),
                    pack_input_dir=str(raw),
                    no_review=True,
                    no_export=True,
                    kit_root=ROOT,
                )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failed_stage"], "pack")
            self.assertIn("--asset-id", result["error"])

    def test_run_py_passes_global_blend_to_host_orchestrator(self):
        entry = _entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            blend = Path(directory) / "asset.blend"
            blend.write_bytes(b"placeholder")

            def fake(module_name, **kwargs):
                if module_name == "shared.scene_inspector":
                    return {"status": "ok", "inventory": {}}
                if module_name == "shared.qa_checks":
                    return {"status": "ok", "passed": True}
                raise AssertionError(module_name)

            stream = io.StringIO()
            with patch.object(deliver, "run_blender_module", side_effect=fake):
                with contextlib.redirect_stdout(stream):
                    rc = entry.main([
                        "deliver", "--blend", str(blend),
                        "--no-review", "--no-export",
                    ])
            self.assertEqual(rc, 0)
            payload = json.loads(stream.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual([s["name"] for s in payload["stages"]], ["inspect", "qa"])


if __name__ == "__main__":
    unittest.main()
