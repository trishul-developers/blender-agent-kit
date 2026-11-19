"""Validate provenance-preserving Sci-Fi evidence import without Blender or original archive."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

try:
    from PIL import Image
except ImportError:
    Image = None

from demos.SciFiKit.import_evidence import (
    BUILDER_ABSOLUTE_PATH, REPORT_NAMES, SHOWCASE_NAMES, SOURCE_NAMES,
    import_evidence,
)


@unittest.skipUnless(Image is not None, "Pillow needed for archive importer")
class SciFiArchiveImportTests(unittest.TestCase):
    def sample_archive(self, path):
        img = Image.new("RGB", (64, 64), (12, 23, 34))
        for x in range(32):
            for y in range(64):
                img.putpixel((x, y), (60, 180, 230))
        out = io.BytesIO()
        img.save(out, "PNG")
        png = out.getvalue()
        qa = {"status": "ok", "passed": True, "errors": []}
        export = {"roundtrip": {
            "checked": True, "passed": True, "tri_count_match": True,
            "embedded_images": {"passed": True},
        }}
        pack = {"status": "ok", "artifacts": {"textures": [
            {"slot": slot} for slot in
            ("_BaseMap", "_MetallicGlossMap", "_BumpMap", "_OcclusionMap")
        ]}}
        with ZipFile(path, "w") as z:
            for name in SOURCE_NAMES:
                value = (BUILDER_ABSOLUTE_PATH + "\n").encode() if name.endswith(".py") else png
                z.writestr(name, value)
            for name in REPORT_NAMES:
                report = qa if name.endswith("qa_bulkhead.json") else export if name.endswith("export_bulkhead.json") else pack if name.endswith("pack_urp.json") else {}
                z.writestr(name, json.dumps(report))
            for name in SHOWCASE_NAMES:
                z.writestr(f"evidences/{name}.png", png)

    def test_stages_verified_images_and_portable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "trial.zip"
            self.sample_archive(archive)
            result = import_evidence(archive, root / "dest", verify_archive=False)
            self.assertEqual(result["status"], "ok")
            path = root / "dest" / "source" / "build_scifi_kit.py"
            text = path.read_text()
            self.assertNotIn("/working_dir/c_fa16c8b573ce2f34/demo_project", text)
            self.assertIn("Path(__file__).resolve().parents[1]", text)
            manifest = json.loads((root / "dest/evidence/archive_manifest.json").read_text())
            self.assertIn("original_sha256", manifest["files"]["source/build_scifi_kit.py"])
            for name in SHOWCASE_NAMES:
                with Image.open(root / "dest/showcase" / (name + ".webp")) as image:
                    self.assertEqual(image.format, "WEBP")

    def test_exact_archive_hash_is_required_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "trial.zip"
            self.sample_archive(archive)
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                import_evidence(archive, root / "dest")

    def test_missing_original_inputs_are_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "trial.zip"
            with ZipFile(archive, "w") as z:
                z.writestr("source/build_scifi_kit.py", BUILDER_ABSOLUTE_PATH)
            with self.assertRaisesRegex(ValueError, "Missing independent agent evidence"):
                import_evidence(archive, root / "dest", verify_archive=False)


if __name__ == "__main__":
    unittest.main()
