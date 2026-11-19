"""Host-side, Blender-independent review contact-sheet compositor.

A JSON sheet spec owns layout; renderer and QA own the underlying evidence.
Requires Pillow only when composing (no bpy import).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compose(spec: dict, *, base_dir: Path, out_file: Path) -> dict:
    from PIL import Image, ImageDraw, ImageFont, ImageStat

    if spec.get("schema_version") != "1.0":
        raise ValueError("Unsupported review sheet schema_version (expected 1.0)")
    images = spec.get("tiles")
    if not isinstance(images, list) or not images:
        raise ValueError("Review sheet requires a nonempty tiles list")
    cols = int(spec.get("columns", 2))
    tile_w, tile_h = [int(value) for value in spec.get("tile_size", [480, 270])]
    gap, label_h = int(spec.get("gap", 8)), int(spec.get("label_height", 54))
    if not (1 <= cols <= 12 and 16 <= tile_w <= 4096 and 16 <= tile_h <= 4096 and 0 <= gap <= 128 and 0 <= label_h <= 200):
        raise ValueError("Invalid contact sheet geometry")
    background = tuple(spec.get("background", [24, 27, 31]))
    if len(background) != 3 or any(not 0 <= int(v) <= 255 for v in background):
        raise ValueError("Invalid background RGB")
    font = ImageFont.load_default()
    rows = (len(images) + cols - 1) // cols
    card_h = tile_h + label_h
    width = cols * tile_w + (cols + 1) * gap
    height = rows * card_h + (rows + 1) * gap
    if width * height > 100_000_000:
        raise ValueError("Review sheet exceeds 100 megapixels")
    sheet = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(sheet)
    records = []
    for idx, item in enumerate(images):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"Tile {idx} missing image path")
        input_path = (base_dir / item["path"]).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"Missing review tile: {input_path}")
        with Image.open(input_path) as source:
            source.load()
            if source.width < 1 or source.height < 1:
                raise ValueError(f"Empty review image: {input_path}")
            image = source.convert("RGB")
        if max(ImageStat.Stat(image).stddev) <= 0 and not spec.get("allow_flat_tiles", False):
            raise ValueError(f"Refusing completely flat review tile: {input_path}")
        # Fit without cropping: information-bearing review views should remain intact.
        image.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
        px = gap + (idx % cols) * (tile_w + gap)
        py = gap + (idx // cols) * (card_h + gap)
        sheet.paste(image, (px + (tile_w - image.width) // 2, py + (tile_h - image.height) // 2))
        title = str(item.get("label", input_path.stem))
        subtitle = str(item.get("evidence", ""))
        if label_h:
            draw.text((px + 8, py + tile_h + 5), title, font=font, fill=(237, 240, 244))
            if subtitle:
                draw.text((px + 8, py + tile_h + 23), subtitle, font=font, fill=(171, 183, 195))
        records.append({"source": str(input_path), "label": title, "evidence": subtitle})
    if out_file.suffix.lower() not in (".webp", ".png", ".jpg", ".jpeg"):
        raise ValueError("Review sheet must be WebP, PNG or JPEG")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = "JPEG" if out_file.suffix.lower() in (".jpg", ".jpeg") else out_file.suffix[1:].upper()
    sheet.save(out_file, format=fmt, quality=int(spec.get("quality", 85)))
    with Image.open(out_file) as verified:
        verified.verify()
    return {"status": "ok", "path": str(out_file), "width": width, "height": height, "tile_count": len(images), "tiles": records}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compose a generic contact sheet from review evidence")
    parser.add_argument("--spec", type=Path, required=True, help="JSON layout specification")
    parser.add_argument("--out", type=Path, required=True, help="WebP/PNG/JPEG sheet")
    parser.add_argument("--base-dir", type=Path, help="Image source root; defaults to spec directory")
    parser.add_argument("--result-json", type=Path, help="Optional machine-readable result report")
    args = parser.parse_args(argv)
    spec_path = args.spec.resolve()
    result = compose(json.loads(spec_path.read_text(encoding="utf-8")),
                     base_dir=(args.base_dir or spec_path.parent).resolve(), out_file=args.out.resolve())
    result_text = json.dumps(result, indent=2)
    if args.result_json:
        args.result_json.parent.mkdir(parents=True, exist_ok=True)
        args.result_json.write_text(result_text + "\n", encoding="utf-8")
    print(result_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
