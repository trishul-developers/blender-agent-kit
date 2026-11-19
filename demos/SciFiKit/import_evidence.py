"""Import the independent Sci-Fi agent evidence as a reviewed demo.

This consumes the *original supplied archive*, never regenerates historical
renders/reports, and retains exact source-file hashes for provenance.
Requires Pillow. No Blender is invoked by this import.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

ARCHIVE_SHA256 = "c22b0802d2d110cca81a4d01ae5b0a3cf067aede80eb7f7f676795a4e7555d7f"
DEMO_DIR = Path(__file__).resolve().parent
BUILDER_ABSOLUTE_PATH = 'PROJECT_DIR = Path("/working_dir/c_fa16c8b573ce2f34/demo_project")'
BUILDER_PORTABLE_PATH = "PROJECT_DIR = Path(__file__).resolve().parents[1]"
SOURCE_NAMES = (
    "source/build_scifi_kit.py",
    "raw_textures/ao.png",
    "raw_textures/base_color.png",
    "raw_textures/emissive.png",
    "raw_textures/metallic.png",
    "raw_textures/normal.png",
    "raw_textures/roughness.png",
)
REPORT_NAMES = (
    "reports/doctor.json",
    "reports/inspect_bulkhead.json",
    "reports/inspect_kit.json",
    "reports/qa_bulkhead.json",
    "reports/pack_urp.json",
    "reports/export_bulkhead.json",
    "reports/lod_stats.json",
)
SHOWCASE_NAMES = (
    "01_hero_render",
    "02_technical_multiview_sheet",
    "03_lod_comparison",
    "04_collision_hierarchy_evidence",
    "05_texture_material_proof",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_evidence(archive: Path, out: Path, *, verify_archive: bool = True) -> dict:
    from PIL import Image, ImageStat

    raw_archive = archive.read_bytes()
    archive_hash = sha256(raw_archive)
    if verify_archive and archive_hash != ARCHIVE_SHA256:
        raise ValueError(f"Archive SHA256 mismatch: expected {ARCHIVE_SHA256}, got {archive_hash}")
    inventory = {}
    with ZipFile(io.BytesIO(raw_archive)) as zip_file:
        names = set(zip_file.namelist())
        required = [*SOURCE_NAMES, *REPORT_NAMES, *(f"evidences/{x}.png" for x in SHOWCASE_NAMES)]
        missing = [name for name in required if name not in names]
        if missing:
            raise ValueError(f"Missing independent agent evidence: {missing}")
        reports = {name: json.loads(zip_file.read(name)) for name in REPORT_NAMES}
        qa = reports["reports/qa_bulkhead.json"]
        export = reports["reports/export_bulkhead.json"]
        roundtrip = export["roundtrip"]
        pack = reports["reports/pack_urp.json"]
        if not (
            qa.get("status") == "ok" and qa.get("passed") is True and not qa.get("errors")
            and roundtrip.get("checked") is True and roundtrip.get("passed") is True
            and roundtrip.get("tri_count_match") is True
            and roundtrip.get("embedded_images", {}).get("passed") is True
            and pack.get("status") == "ok"
        ):
            raise ValueError("Machine evidence failed the declared QA / roundtrip / pack contract")
        if {item["slot"] for item in pack["artifacts"]["textures"]} != {
            "_BaseMap", "_MetallicGlossMap", "_BumpMap", "_OcclusionMap"
        }:
            raise ValueError("URP texture-slot evidence is incomplete")
        script_bytes = zip_file.read("source/build_scifi_kit.py")
        source = script_bytes.decode("utf-8")
        if source.count(BUILDER_ABSOLUTE_PATH) != 1:
            raise ValueError("Builder portability patch did not match exactly one original path")
        portable = source.replace(BUILDER_ABSOLUTE_PATH, BUILDER_PORTABLE_PATH).encode("utf-8")
        # Validate every input before creating output directories.
        for name in SOURCE_NAMES[1:]:
            with Image.open(io.BytesIO(zip_file.read(name))) as img:
                img.verify()
        for key in SHOWCASE_NAMES:
            with Image.open(io.BytesIO(zip_file.read(f"evidences/{key}.png"))) as img:
                img.verify()
        for name in SOURCE_NAMES[1:]:
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            value = zip_file.read(name)
            dest.write_bytes(value)
            inventory[name] = {"original_sha256": sha256(value), "published_sha256": sha256(value)}
        path = out / "source" / "build_scifi_kit.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(portable)
        inventory["source/build_scifi_kit.py"] = {
            "original_sha256": sha256(script_bytes),
            "published_sha256": sha256(portable),
            "change": "Only original absolute PROJECT_DIR replaced with script-relative project root",
        }
        for name in REPORT_NAMES:
            value = zip_file.read(name)
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(value)
            inventory[name] = {"original_sha256": sha256(value), "published_sha256": sha256(value)}
        for key in SHOWCASE_NAMES:
            original_name = f"evidences/{key}.png"
            value = zip_file.read(original_name)
            with Image.open(io.BytesIO(value)) as image:
                rgb = image.convert("RGB")
                if max(ImageStat.Stat(rgb).stddev) < 1:
                    raise ValueError(f"Original evidence sheet unexpectedly blank: {original_name}")
                rgb.thumbnail((1200, 900), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                rgb.save(output, "WEBP", quality=80, method=6)
            dest = out / "showcase" / f"{key}.webp"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(output.getvalue())
            inventory[str(dest.relative_to(out))] = {
                "source": original_name,
                "original_sha256": sha256(value),
                "published_sha256": sha256(output.getvalue()),
                "conversion": "Pillow RGB Lanczos max 1200x900; WebP quality 80",
            }
    result = {
        "schema_version": "1.0",
        "provenance": "independent agent evidence, inspected and reformatted, not rerun",
        "archive_sha256": archive_hash,
        "files": inventory,
    }
    dest = out / "evidence" / "archive_manifest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {"status": "ok", "archive_sha256": archive_hash, "published_files": len(inventory), "manifest": str(dest)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate and stage the independently supplied Sci-Fi demo")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEMO_DIR)
    args = parser.parse_args(argv)
    print(json.dumps(import_evidence(args.archive, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
