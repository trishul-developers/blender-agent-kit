"""Host-side, Blender-independent review contact-sheet compositor.

A JSON sheet spec owns layout; renderer and QA own the underlying evidence.
Requires Pillow only when composing (no bpy import).
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path



def _load_image(path: Path):
    """Load ordinary images and explicitly preserve 16-bit PNG channels.

    Pillow converts some 16-bit RGB/RGBA PNG inputs to 8-bit on load. The kit
    produces unfiltered 16-bit PNGs, so decode those channel high bytes
    directly rather than depending on implicit Pillow conversion.
    """
    from PIL import Image

    header = path.read_bytes()[:26]
    if not (len(header) >= 26 and header[:8] == bytes.fromhex("89504e470d0a1a0a")):
        with Image.open(path) as source:
            source.load()
            return source.copy()
    depth, color = header[24], header[25]
    if depth != 16 or color not in (0, 2, 6):
        with Image.open(path) as source:
            source.load()
            return source.copy()
    data = path.read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    if width * height > 100_000_000:
        raise ValueError(f"16-bit PNG too large: {path}")
    channels = {0: 1, 2: 3, 6: 4}[color]
    stride = width * channels * 2
    pos, chunks = 8, []
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        if pos + 12 + length > len(data):
            raise ValueError(f"Truncated 16-bit PNG: {path}")
        if kind == b"IDAT":
            chunks.append(data[pos + 8:pos + 8 + length])
        pos += 12 + length
        if kind == b"IEND":
            break
    raw = zlib.decompress(b"".join(chunks))
    if len(raw) != height * (stride + 1):
        raise ValueError(f"Unsupported 16-bit PNG scanline geometry: {path}")
    previous = bytearray(stride)
    high = bytearray(width * height * channels)
    cursor, outpos = 0, 0
    for _ in range(height):
        method = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        if method not in (0, 1, 2, 3, 4):
            raise ValueError(f"Unsupported PNG filter {method}: {path}")
        if method:
            for i in range(stride):
                left = row[i - channels * 2] if i >= channels * 2 else 0
                above = previous[i]
                upper_left = previous[i - channels * 2] if i >= channels * 2 else 0
                if method == 1:
                    predictor = left
                elif method == 2:
                    predictor = above
                elif method == 3:
                    predictor = (left + above) // 2
                else:
                    p = left + above - upper_left
                    da, db, dc = abs(p - left), abs(p - above), abs(p - upper_left)
                    predictor = left if da <= db and da <= dc else above if db <= dc else upper_left
                row[i] = (row[i] + predictor) & 255
        # For display only, scale 16-bit samples to high bytes; the source PNG
        # itself is untouched and still available for bit-depth verification.
        high[outpos:outpos + width * channels] = row[::2]
        outpos += width * channels
        previous = row
    mode = {0: "L", 2: "RGB", 6: "RGBA"}[color]
    return Image.frombytes(mode, (width, height), bytes(high))


def _font(size: int):
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "SegoeUI.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _short_text(draw, value: str, font, max_width: int) -> str:
    if draw.textlength(value, font=font) <= max_width:
        return value
    while value and draw.textlength(value + "...", font=font) > max_width:
        value = value[:-1]
    return value + "..."


def compose(spec: dict, *, base_dir: Path, out_file: Path) -> dict:
    from PIL import Image, ImageDraw, ImageStat

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
    font = _font(int(spec.get("font_size", max(12, min(24, label_h // 2)))))
    subtitle_font = _font(int(spec.get("subtitle_font_size", max(10, min(17, label_h // 3)))))
    title = str(spec.get("title", "")).strip()
    description = str(spec.get("subtitle", "")).strip()
    banner_height = int(spec.get("title_height", 94 if title else 0))
    if banner_height < 0 or banner_height > 500 or (title and banner_height < 28):
        raise ValueError("Invalid title_height")
    header_font = _font(int(spec.get("title_font_size", 30)))
    rows = (len(images) + cols - 1) // cols
    card_h = tile_h + label_h
    width = cols * tile_w + (cols + 1) * gap
    height = rows * card_h + (rows + 1) * gap + banner_height
    if width * height > 100_000_000:
        raise ValueError("Review sheet exceeds 100 megapixels")
    sheet = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(sheet)
    if title:
        draw.text((gap + 8, 10), _short_text(draw, title, header_font, width - gap * 3), font=header_font, fill=(237, 240, 244))
        if description:
            draw.text((gap + 8, 52), _short_text(draw, description, subtitle_font, width - gap * 3), font=subtitle_font, fill=(171, 183, 195))
    records = []
    for idx, item in enumerate(images):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"Tile {idx} missing image path")
        input_path = (base_dir / item["path"]).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"Missing review tile: {input_path}")
        source = _load_image(input_path)
        if source.width < 1 or source.height < 1:
            raise ValueError(f"Empty review image: {input_path}")
        mode = item.get("mode", "rgb")
        if mode == "split_alpha":
            if "A" not in source.getbands():
                raise ValueError(f"split_alpha requires RGBA: {input_path}")
            foreground = source.convert("RGB")
            alpha = source.getchannel("A").convert("RGB")
            image = Image.new("RGB", (source.width * 2, source.height))
            image.paste(foreground, (0, 0))
            image.paste(alpha, (source.width, 0))
        elif mode == "alpha":
            if "A" not in source.getbands():
                raise ValueError(f"alpha mode requires RGBA: {input_path}")
            image = source.getchannel("A").convert("RGB")
        elif mode == "rgb":
            image = source.convert("RGB")
        else:
            raise ValueError(f"Unsupported tile mode: {mode}")
        if max(ImageStat.Stat(image).stddev) <= 0 and not spec.get("allow_flat_tiles", False):
            raise ValueError(f"Refusing completely flat review tile: {input_path}")
        # Fit without cropping: information-bearing review views should remain intact.
        image.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
        px = gap + (idx % cols) * (tile_w + gap)
        py = banner_height + gap + (idx // cols) * (card_h + gap)
        sheet.paste(image, (px + (tile_w - image.width) // 2, py + (tile_h - image.height) // 2))
        title = str(item.get("label", input_path.stem))
        subtitle = str(item.get("evidence", ""))
        if label_h:
            draw.text((px + 8, py + tile_h + 5), _short_text(draw, title, font, tile_w - 16), font=font, fill=(237, 240, 244))
            if subtitle:
                draw.text((px + 8, py + tile_h + 5 + min(30, label_h // 2)), _short_text(draw, subtitle, subtitle_font, tile_w - 16), font=subtitle_font, fill=(171, 183, 195))
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
