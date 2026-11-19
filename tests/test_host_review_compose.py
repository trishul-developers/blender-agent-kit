"""Host tests for generic, data-driven review sheet composition."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

from tools.review_compose import compose, _load_image

from shared.channel_pack import encode_png
import numpy as np


@unittest.skipUnless(Image is not None, "Pillow not installed (optional host composer)")
class ReviewComposeHostTests(unittest.TestCase):
    def test_two_by_two_sheet_and_machine_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(4):
                image = Image.new("RGB", (120, 80))
                image.putpixel((i, 0), (240, 60, 20))
                image.putpixel((10, 10), (0, 0, 255))
                image.save(root / f"view{i}.png")
            spec = {
                "schema_version": "1.0", "columns": 2,
                "tile_size": [120, 80], "gap": 4, "label_height": 40,
                "tiles": [
                    {"path": f"view{i}.png", "label": f"LOD{i}", "evidence": f"{1000-i*200} tris"}
                    for i in range(4)
                ],
            }
            path = root / "sheet.webp"
            result = compose(spec, base_dir=root, out_file=path)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["tile_count"], 4)
            with Image.open(path) as image:
                self.assertEqual(image.size, (252, 252))
                self.assertEqual(image.format, "WEBP")

    def test_title_and_readable_sheet_typography(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = Image.new("RGB", (64, 64), (30, 40, 80))
            sample.putpixel((0, 0), (255, 0, 0))
            sample.save(root / "shot.png")
            spec = {
                "schema_version": "1.0", "title": "LOD Comparison",
                "subtitle": "Machine evidence, not manually fabricated",
                "title_height": 110, "columns": 1, "font_size": 20,
                "tile_size": [280, 170], "label_height": 62,
                "tiles": [{"path": "shot.png", "label": "LOD0", "evidence": "4204 triangles"}],
            }
            result = compose(spec, base_dir=root, out_file=root / "title.webp")
            self.assertEqual(result["height"], 110 + 170 + 62 + 8 * 2)
            with Image.open(root / "title.webp") as img:
                self.assertEqual(img.size, (296, result["height"]))

    def test_16bit_normal_and_alpha_split_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normal = np.zeros((8, 8, 3), dtype=np.float32)
            normal[..., 0] = np.linspace(0.1, 0.9, 8)
            normal[..., 1] = 0.5
            normal[..., 2] = 1.0
            (root / "normal.png").write_bytes(encode_png(normal, 16))
            decoded = _load_image(root / "normal.png")
            self.assertEqual(decoded.mode, "RGB")
            self.assertGreater(decoded.getpixel((7, 0))[0], decoded.getpixel((0, 0))[0])
            rgba = Image.new("RGBA", (10, 10), (130, 100, 90, 0))
            for x in range(5, 10):
                for y in range(10):
                    rgba.putpixel((x, y), (130, 100, 90, 255))
            rgba.save(root / "gloss.png")
            spec = {
                "schema_version": "1.0", "columns": 2,
                "tile_size": [100, 60], "label_height": 40,
                "tiles": [
                    {"path": "normal.png", "label": "16-bit normal"},
                    {"path": "gloss.png", "mode": "split_alpha", "label": "RGB | alpha"},
                ],
            }
            result = compose(spec, base_dir=root, out_file=root / "maps.webp")
            self.assertEqual(result["tile_count"], 2)

    def test_missing_tile_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                compose({"schema_version": "1.0", "tiles": [{"path": "missing.png"}]},
                        base_dir=root, out_file=root / "sheet.webp")

    def test_flat_tile_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new("RGB", (20, 20), "black").save(root / "flat.png")
            with self.assertRaisesRegex(ValueError, "flat"):
                compose({"schema_version": "1.0", "tiles": [{"path": "flat.png"}]},
                        base_dir=root, out_file=root / "sheet.webp")

    def test_invalid_layout_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "geometry"):
                compose({"schema_version": "1.0", "columns": 0, "tiles": [{"path": "a.png"}]},
                        base_dir=root, out_file=root / "sheet.webp")


if __name__ == "__main__":
    unittest.main()
