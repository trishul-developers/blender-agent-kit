"""Host-only discovery must be deterministic, complete, and Blender-free."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.capabilities import build_capabilities
from shared.command_registry import COMMANDS, HOST_SUBCOMMANDS
from shared.contract import build_contract
from tools.validate_skills import validate_json_instance

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "skills/core/blender-core/scripts/run.py"


def _entrypoint():
    spec = importlib.util.spec_from_file_location("bak_discovery_entry", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DiscoveryTests(unittest.TestCase):
    def test_capabilities_are_deterministic_and_cover_registry(self):
        first = build_capabilities(ROOT)
        second = build_capabilities(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(
            [row["name"] for row in first["commands"]],
            sorted(COMMANDS),
        )
        by_target = {row["name"]: row for row in first["targets"]}
        self.assertEqual(by_target["unity"]["default_policy"], "realtime-default")
        self.assertIn("urp", by_target["unity"]["texture_profiles"])
        by_skill = {row["name"]: row for row in first["skills"]}
        self.assertEqual(by_skill["blender-batch"]["execution"], "guidance-only")
        self.assertEqual(by_skill["blender-asset-qa"]["execution"], "executable")

    def test_discovery_payloads_match_public_json_schemas(self):
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.skipTest("jsonschema optional outside strict CI")
        cap_schema = json.loads((ROOT / "schemas/capabilities.schema.json").read_text())
        contract_schema = json.loads((ROOT / "schemas/contract.schema.json").read_text())
        self.assertEqual(
            validate_json_instance(
                build_capabilities(ROOT), cap_schema, "capabilities", require_jsonschema=True
            ),
            [],
        )
        self.assertEqual(
            validate_json_instance(
                build_contract(), contract_schema, "contract", require_jsonschema=True
            ),
            [],
        )

    def test_default_contract_resolves_policy_without_reading_blender(self):
        contract = build_contract(target="unity", asset_class="solid_prop")
        self.assertEqual(contract["status"], "ok")
        self.assertEqual(contract["target"]["default_policy"], "realtime-default")
        self.assertEqual(contract["asset_class"], "solid_prop")
        self.assertEqual(contract["qa"]["lod"]["max_tris"]["lod0"], 15000)
        self.assertEqual(contract["qa"]["materials"]["max_slots"], 2)
        self.assertEqual(contract["qa"]["pivot"]["rule"], "bottom_center_z0")
        self.assertEqual(
            contract["naming"]["collider_patterns"],
            ["{name}_COL_{index:02d}", "COLLISION_{name}"],
        )
        self.assertEqual(contract["textures"]["profile"], "urp")
        self.assertIn("metallic_smoothness", contract["textures"]["maps"])
        self.assertTrue(contract["export"]["roundtrip"]["enabled_by_default"])
        self.assertEqual(contract["review"]["default_style"], "technical")
        self.assertEqual(contract["review"]["selected_style"], "technical")
        self.assertEqual(
            contract["review"]["available_styles"],
            ["showcase", "technical"],
        )
        self.assertEqual(
            contract["review"]["style_settings"]["engine"],
            "BLENDER_EEVEE",
        )

    def test_contract_includes_project_override_and_review_preset(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile.json"
            profile.write_text(json.dumps({
                "name": "discovery-test",
                "version": "1.0.0",
                "target_overrides": {
                    "unity": {
                        "qa": {
                            "asset_classes": {
                                "tiny_prop": {
                                    "reject_boundary_edges": True,
                                    "require_non_overlapping_uv1": False,
                                    "pivot_rule": "none",
                                    "max_tris": {"lod0": 321},
                                    "max_material_slots": 1
                                }
                            }
                        }
                    }
                },
                "review_presets": {
                    "proof": {
                        "resolution": [640, 360],
                        "orthographic_views": ["front", "side"]
                    }
                }
            }), encoding="utf-8")
            contract = build_contract(
                target="unity",
                project_profile=str(profile),
                asset_class="tiny_prop",
                preset="proof",
            )
        self.assertEqual(contract["project_profile"], "discovery-test")
        self.assertEqual(contract["qa"]["lod"]["max_tris"]["lod0"], 321)
        self.assertEqual(contract["review"]["selected_preset"], "proof")
        self.assertEqual(contract["review"]["settings"]["resolution"], [640, 360])

    def test_run_py_host_discovery_never_launches_blender(self):
        entry = _entrypoint()
        self.assertEqual(HOST_SUBCOMMANDS, {"capabilities", "contract", "deliver"})
        with patch("shared.runner.find_blender", side_effect=AssertionError("Blender discovery forbidden")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = entry.main(["capabilities", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertIn("contract", {row["name"] for row in payload["commands"]})

    def test_host_result_json_uses_same_payload(self):
        entry = _entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "contract.json"
            stream = io.StringIO()
            with patch("shared.runner.find_blender", side_effect=AssertionError("Blender discovery forbidden")):
                with contextlib.redirect_stdout(stream):
                    rc = entry.main([
                        "contract", "--target", "unity", "--asset-class", "solid_prop",
                        "--result-json", str(dest),
                    ])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(stream.getvalue()), json.loads(dest.read_text()))
            self.assertEqual(json.loads(dest.read_text())["target"]["name"], "unity")

    def test_invalid_host_flag_is_structured_error(self):
        entry = _entrypoint()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = entry.main(["capabilities", "--not-a-real-flag"])
        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "ArgumentError")

    def test_invalid_contract_is_structured_error(self):
        entry = _entrypoint()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = entry.main(["contract", "--asset-class", "does-not-exist"])
        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "KeyError")
        self.assertIn("does-not-exist", payload["error"])


if __name__ == "__main__":
    unittest.main()
