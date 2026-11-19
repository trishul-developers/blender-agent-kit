"""Configuration regressions discovered by the independent Blender Agent Kit trial."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from shared.target_loader import validate_target_dict, deep_merge_dict, load_target


ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "plugins/targets/blender-target-unity/target.json").read_text(encoding="utf-8"))


class ParentPairValidation(unittest.TestCase):
    def test_valid_nested_parent_pairs(self):
        cfg = copy.deepcopy(TARGET)
        cfg["qa"]["asset_classes"]["test_bulkhead"] = {
            "required_parent_pairs": [{"child": "Socket_Overhead", "parent": "Header"}]
        }
        self.assertEqual(validate_target_dict(cfg), [])

    def test_malformed_list_pairs_fail_before_blender(self):
        cfg = copy.deepcopy(TARGET)
        cfg["qa"]["asset_classes"]["test_bulkhead"] = {
            "required_parent_pairs": [["Socket_Overhead", "Header"]]
        }
        failures = validate_target_dict(cfg)
        self.assertTrue(any("required_parent_pairs[0]" in err for err in failures), failures)
        with self.assertRaisesRegex(ValueError, "required_parent_pairs"):
            load_target("unity", overlay={"qa": {"asset_classes": {
                "test_bulkhead": {"required_parent_pairs": [["Child", "Parent"]]}
            }}}, kit_root=ROOT)

    def test_invalid_empty_parent_rejected(self):
        cfg = copy.deepcopy(TARGET)
        cfg["qa"]["asset_classes"]["test_bulkhead"] = {
            "required_parent_pairs": [{"child": "X", "parent": ""}]
        }
        self.assertTrue(any("required_parent_pairs" in x for x in validate_target_dict(cfg)))

    def test_overlay_does_not_modify_base_target(self):
        cfg = copy.deepcopy(TARGET)
        merged = deep_merge_dict(cfg, {"qa": {"asset_classes": {"test_bulkhead": {
            "required_parent_pairs": [{"child": "A", "parent": "B"}]
        }}}})
        self.assertNotIn("test_bulkhead", cfg["qa"]["asset_classes"])
        self.assertEqual(validate_target_dict(merged), [])


if __name__ == "__main__":
    unittest.main()
