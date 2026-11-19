"""Host tests for generic, data-driven review sheet composition."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

from tools.review_compose import compose


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
