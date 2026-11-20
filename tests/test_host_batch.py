"""Batch processing: isolation, cache invalidation, evidence and telemetry."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import batch
from shared.capabilities import build_capabilities
from shared.command_registry import HOST_SUBCOMMANDS
from tools.validate_skills import validate_json_instance

ROOT = Path(__file__).resolve().parents[1]
BLENDER_ID = {
    "path": "/fake/blender",
    "version": "Blender 5.2.4 LTS",
    "size": 123456,
    "mtime_ns": 123,
}


def _write_profile(path: Path, max_slots: int) -> None:
    path.write_text(json.dumps({
        "name": "batch-test",
        "version": "1.0.0",
        "target_overrides": {
            "unity": {
                "qa": {
                    "asset_classes": {
                        "solid_prop": {
                            "max_material_slots": max_slots
                        }
                    }
                }
            }
        }
    }), encoding="utf-8")


class BatchTests(unittest.TestCase):
    def test_qa_cache_hit_and_source_change_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "assets"
            source_dir.mkdir()
            blend = source_dir / "A.blend"
            blend.write_bytes(b"blend-v1")
            output = root / "out"
            calls = []

            def fake(module_name, **kwargs):
                calls.append((module_name, kwargs.get("blend_file")))
                self.assertEqual(module_name, "shared.qa_checks")
                return {"status": "ok", "passed": True, "errors": [], "warnings": []}

            with patch.object(batch, "_blender_identity", return_value=BLENDER_ID):
                with patch.object(batch, "run_blender_module", side_effect=fake):
                    first = batch.run(
                        operation="qa", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )
                    second = batch.run(
                        operation="qa", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )
                    blend.write_bytes(b"blend-v2")
                    third = batch.run(
                        operation="qa", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )

            self.assertEqual(first["counts"], {"discovered": 1, "processed": 1, "skipped": 0, "failed": 0})
            self.assertEqual(second["counts"], {"discovered": 1, "processed": 0, "skipped": 1, "failed": 0})
            self.assertTrue(second["items"][0]["cache_hit"])
            self.assertEqual(third["counts"]["processed"], 1)
            self.assertFalse(third["items"][0]["cache_hit"])
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(first["items"][0]["cache_key"], third["items"][0]["cache_key"])

    def test_project_config_and_tool_identity_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "assets"
            source_dir.mkdir()
            (source_dir / "A.blend").write_bytes(b"same-source")
            output = root / "out"
            profile = root / "profile.json"
            _write_profile(profile, 2)
            calls = []

            def fake(module_name, **kwargs):
                calls.append(module_name)
                return {"status": "ok", "passed": True, "errors": [], "warnings": []}

            with patch.object(batch, "_blender_identity", return_value=BLENDER_ID):
                with patch.object(batch, "run_blender_module", side_effect=fake):
                    with patch.object(batch, "_tool_identity", return_value="sha256:tool-v1"):
                        first = batch.run(
                            operation="qa", input_dir=str(source_dir), out_dir=str(output),
                            project_profile=str(profile), kit_root=ROOT
                        )
                        cached = batch.run(
                            operation="qa", input_dir=str(source_dir), out_dir=str(output),
                            project_profile=str(profile), kit_root=ROOT
                        )
                        _write_profile(profile, 1)
                        config_changed = batch.run(
                            operation="qa", input_dir=str(source_dir), out_dir=str(output),
                            project_profile=str(profile), kit_root=ROOT
                        )
                    with patch.object(batch, "_tool_identity", return_value="sha256:tool-v2"):
                        tool_changed = batch.run(
                            operation="qa", input_dir=str(source_dir), out_dir=str(output),
                            project_profile=str(profile), kit_root=ROOT
                        )

            self.assertEqual(first["counts"]["processed"], 1)
            self.assertEqual(cached["counts"]["skipped"], 1)
            self.assertEqual(config_changed["counts"]["processed"], 1)
            self.assertEqual(tool_changed["counts"]["processed"], 1)
            self.assertEqual(len(calls), 3)
            self.assertNotEqual(first["items"][0]["cache_key"], config_changed["items"][0]["cache_key"])
            self.assertNotEqual(config_changed["items"][0]["cache_key"], tool_changed["items"][0]["cache_key"])

    def test_export_manifest_build_hash_is_part_of_cache_validity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "assets"
            source_dir.mkdir()
            (source_dir / "A.blend").write_bytes(b"blend")
            output = root / "out"
            calls = []

            def fake(module_name, **kwargs):
                self.assertEqual(module_name, "shared.exporter")
                calls.append(module_name)
                args = kwargs["module_args"]
                out = Path(args[args.index("--out") + 1])
                out.mkdir(parents=True, exist_ok=True)
                export_file = out / "A.fbx"
                export_file.write_bytes(b"fbx")
                manifest = out / "A.asset.manifest.json"
                manifest.write_text(json.dumps({
                    "schema_version": "1.0",
                    "build_hash": "sha256:artifact-build",
                    "export_file": "A.fbx",
                }), encoding="utf-8")
                return {
                    "status": "ok",
                    "build_hash": "sha256:artifact-build",
                    "artifacts": {
                        "export": str(export_file),
                        "manifest": str(manifest),
                    },
                    "roundtrip": {"checked": True, "passed": True},
                }

            with patch.object(batch, "_blender_identity", return_value=BLENDER_ID):
                with patch.object(batch, "run_blender_module", side_effect=fake):
                    first = batch.run(
                        operation="export", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )
                    second = batch.run(
                        operation="export", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )
                    manifest_path = Path(first["items"][0]["result"]["artifacts"]["manifest"])
                    manifest = json.loads(manifest_path.read_text())
                    manifest["build_hash"] = "sha256:tampered"
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    third = batch.run(
                        operation="export", input_dir=str(source_dir), out_dir=str(output), kit_root=ROOT
                    )

            self.assertEqual(first["counts"]["processed"], 1)
            self.assertEqual(second["counts"]["skipped"], 1)
            self.assertEqual(third["counts"]["processed"], 1)
            self.assertEqual(len(calls), 2)

    def test_pack_discovers_raw_map_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "raw"
            asset = source_dir / "Crate"
            asset.mkdir(parents=True)
            (asset / "base_color.png").write_bytes(b"png")
            output = root / "out"
            calls = []

            def fake(module_name, **kwargs):
                calls.append((module_name, kwargs["module_args"]))
                return {"status": "ok", "artifacts": {"textures": []}}

            with patch.object(batch, "_blender_identity", return_value=BLENDER_ID):
                with patch.object(batch, "run_blender_module", side_effect=fake):
                    result = batch.run(
                        operation="pack", input_dir=str(source_dir), out_dir=str(output),
                        material="Body", kit_root=ROOT
                    )
            self.assertEqual(result["counts"]["processed"], 1)
            self.assertEqual(calls[0][0], "shared.channel_pack")
            self.assertIn("Crate", calls[0][1])
            self.assertIn("Body", calls[0][1])

    def test_batch_is_bounded_before_blender_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("A.blend", "B.blend"):
                (root / name).write_bytes(name.encode())
            with patch.object(batch, "_blender_identity", side_effect=AssertionError("must not identify Blender")):
                result = batch.run(
                    operation="qa", input_dir=str(root), out_dir=str(root / "out"),
                    max_assets=1, kit_root=ROOT
                )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["discovered"], 2)
            self.assertIn("max-assets", result["error"])

    def test_batch_report_schema_and_capability_surface(self):
        capabilities = build_capabilities(ROOT)
        by_name = {row["name"]: row for row in capabilities["commands"]}
        self.assertEqual(by_name["batch"]["mode"], "host")
        by_skill = {row["name"]: row for row in capabilities["skills"]}
        self.assertEqual(by_skill["blender-batch"]["execution"], "executable")
        self.assertIn("batch", by_skill["blender-batch"]["commands"])
        self.assertIn("batch", HOST_SUBCOMMANDS)

        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema optional outside strict CI")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A.blend").write_bytes(b"blend")
            with patch.object(batch, "_blender_identity", return_value=BLENDER_ID):
                with patch.object(batch, "run_blender_module", return_value={
                    "status": "ok", "passed": True, "errors": [], "warnings": []
                }):
                    result = batch.run(
                        operation="qa", input_dir=str(root), out_dir=str(root / "out"), kit_root=ROOT
                    )
        schema = json.loads((ROOT / "schemas/batch.schema.json").read_text())
        self.assertEqual(
            validate_json_instance(result, schema, "batch", require_jsonschema=True),
            [],
        )
        self.assertEqual(
            result["telemetry"]["not_measured"],
            ["model_tokens", "api_tokens", "agent_turns"],
        )


if __name__ == "__main__":
    unittest.main()
