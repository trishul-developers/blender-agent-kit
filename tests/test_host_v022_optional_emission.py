"""Optional emission packing: no synthetic emission when source is absent."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from shared.channel_pack import write_packed_profile, required_raw_map_names

ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "plugins/targets/blender-target-unity/target.json").read_text())


class OptionalEmissionTests(unittest.TestCase):
    def test_optional_emission_requires_actual_raw_source(self):
        cfg = copy.deepcopy(TARGET)
        self.assertIn("emission", required_raw_map_names(cfg, "urp"))
        pixels = np.zeros((8, 8), dtype=np.float32)
        rgb = np.zeros((8, 8, 3), dtype=np.float32)
        rgb[..., 2] = 1.0
        with tempfile.TemporaryDirectory() as directory:
            result = write_packed_profile(cfg, "urp", "Asset", "Body",
                {"base_color": rgb, "metallic": pixels, "roughness": pixels,
                 "ao": pixels, "normal": rgb}, (8, 8), Path(directory))
            slots = {x["slot"] for x in result}
            self.assertNotIn("_EmissionMap", slots)
            self.assertEqual(len(slots), 4)
            result_with_emission = write_packed_profile(cfg, "urp", "Asset", "Body",
                {"base_color": rgb, "metallic": pixels, "roughness": pixels,
                 "ao": pixels, "normal": rgb, "emission": rgb},
                (8, 8), Path(directory))
            self.assertIn("_EmissionMap", {x["slot"] for x in result_with_emission})
            self.assertEqual(len(result_with_emission), 5)
            self.assertTrue((Path(directory) / next(x["path"] for x in result_with_emission if x["slot"] == "_EmissionMap")).is_file())


if __name__ == "__main__":
    unittest.main()
