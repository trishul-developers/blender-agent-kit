"""End-to-end host regression for the SupplyCrate texture showcase.

Fixtures are synthetic and explicitly test code behavior, not production asset evidence.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from shared.channel_pack import encode_png

try:
    from PIL import Image, ImageStat
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "demos" / "SupplyCrate" / "make_sheets.py"


@unittest.skipUnless(Image is not None, "Pillow required for SupplyCrate sheet smoke test")
class SupplyCrateSheetHostTests(unittest.TestCase):
    def make_fixture(self, root):
        shutil.copy2(SOURCE, root / "make_sheets.py")
        for folder in ("raw", "build/textures", "renders"):
            (root / folder).mkdir(parents=True)
        parts = {}
        for index in (0, 1, 2):
            parts[f"crate_lod{index}"] = {
                "id": f"crate_lod{index}", "tri_count": 1000 // (index + 1),
                "material_count": 1, "file": "fixture.fbx", "roundtrip": {"passed": True},
            }
        parts["collision"] = {
            "id": "collision", "tri_count": 12, "material_count": 0,
            "file": "collision.fbx", "roundtrip": {"passed": True},
        }
        (root / "build" / "SupplyCrate.bundle.manifest.json").write_text(
            json.dumps({"parts": list(parts.values())}), encoding="utf-8"
        )
        for view in ("closeup", "front", "side", "top", "collision_outline"):
            self.write_view(root / "renders" / f"review_{view}.png")
        for lod in (0, 1, 2):
            for distance in (3, 8, 20):
                self.write_view(root / "renders" / f"review_lod{lod}_{distance}m.png")

        h = w = 24
        x = np.tile(np.linspace(0.1, 0.95, w, dtype=np.float32), (h, 1))
        y = x[::-1].T
        rgb = np.stack([x, y, 1-x], axis=-1)
        grayscale = {
            "roughness": x,
            "metallic": y,
            "ao": 0.2 + x*0.7,
        }
        (root / "raw" / "base_color.png").write_bytes(encode_png(rgb, 8))
        for name, arr in grayscale.items():
            (root / "raw" / (name + ".png")).write_bytes(encode_png(arr, 8))
        (root / "raw" / "normal.png").write_bytes(encode_png(rgb, 16))
        texture_root = root / "build" / "textures"
        prefix = "SupplyCrate__Body__"
        (texture_root / (prefix + "albedo.png")).write_bytes(encode_png(np.dstack([rgb, np.ones((h,w),np.float32)]), 8))
        (texture_root / (prefix + "metallic_smoothness.png")).write_bytes(encode_png(np.stack([y,y,y,1-x],-1), 8))
        (texture_root / (prefix + "normal.png")).write_bytes(encode_png(rgb, 16))
        (texture_root / (prefix + "ao.png")).write_bytes(encode_png(x, 8))

    @staticmethod
    def write_view(path):
        img = Image.new("RGB", (200, 100), "gray")
        img.putpixel((10, 20), (245, 10, 10))
        img.save(path)

    def test_all_five_raw_four_packed_maps_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            result = subprocess.run([sys.executable, str(root / "make_sheets.py")],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with Image.open(root / "showcase" / "demo_textures.webp") as im:
                self.assertEqual(im.size, (1044, 1176))
                self.assertGreater(max(ImageStat.Stat(im).stddev), 10)
                # Third-row right tile must exist: the original [:6] bug omitted it.
                last_tile = im.crop((710, 780, 1040, 1120))
                self.assertGreater(max(ImageStat.Stat(last_tile).stddev), 5)

    def test_missing_target_image_fails_instead_of_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            (root / "build" / "textures" / "SupplyCrate__Body__normal.png").unlink()
            result = subprocess.run([sys.executable, str(root / "make_sheets.py")],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing texture showcase source", result.stderr)
            self.assertFalse((root / "showcase" / "demo_textures.webp").is_file())


if __name__ == "__main__":
    unittest.main()
