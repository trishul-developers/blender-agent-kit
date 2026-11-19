"""Compose repo-page contact sheets from kit outputs (host Python + Pillow + numpy)."""
import json
import struct
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
R, RAW, BUILD, OUT = HERE / "renders", HERE / "raw", HERE / "build", HERE / "showcase"
OUT.mkdir(exist_ok=True)
BG = (24, 27, 31)


def font(size):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def read_png_16rgb(path):
    """Minimal reader for the kit's own filter-0 16-bit RGB PNG (Pillow cannot open 16-bit RGB)."""
    b = path.read_bytes()[8:]
    pos, idat, ihdr = 0, b"", None
    while pos < len(b):
        n, t = struct.unpack(">I4s", b[pos:pos + 8])
        d = b[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", d)
        elif t == b"IDAT":
            idat += d
        pos += 12 + n
    w, h, depth, ctype = ihdr[:4]
    ch = {2: 3, 0: 1, 6: 4}[ctype]
    raw = np.frombuffer(zlib.decompress(idat), np.uint8).reshape(h, 1 + w * ch * depth // 8)
    assert (raw[:, 0] == 0).all()
    a = raw[:, 1:].reshape(h, w, ch, depth // 8)
    arr = (a[..., 0].astype(np.uint16) << 8 | a[..., 1]) if depth == 16 else a[..., 0]
    return arr, depth


def load(path):
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        arr, depth = read_png_16rgb(path)
        return Image.fromarray((arr >> 8).astype(np.uint8), "RGB")


def label(img, text, sub=None, h=44):
    w = img.width
    canvas = Image.new("RGB", (w, img.height + h), BG)
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((14, img.height + 6), text, font=font(20), fill=(235, 238, 242))
    if sub:
        d.text((14, img.height + 26), sub, font=font(13), fill=(150, 158, 168))
    return canvas


def grid(tiles, cols, gap=6):
    rows = (len(tiles) + cols - 1) // cols
    w, h = tiles[0].size
    sheet = Image.new("RGB", (cols * w + (cols + 1) * gap, rows * h + (rows + 1) * gap), BG)
    for i, t in enumerate(tiles):
        sheet.paste(t, (gap + (i % cols) * (w + gap), gap + (i // cols) * (h + gap)))
    return sheet


manifest = json.loads((BUILD / "SupplyCrate.bundle.manifest.json").read_text(encoding="utf-8"))
parts = {p["id"]: p for p in manifest["parts"]}


def crop(img):
    # review frames are 16:9 with the prop centred; crop to the prop area for contact sheets
    w, h = img.size
    return img.crop((int(w * 0.22), int(h * 0.12), int(w * 0.78), int(h * 0.88))).resize((560, 428), Image.LANCZOS)


# 1) LOD + collision workflow
tiles = []
for lod in (0, 1, 2):
    p = parts[f"crate_lod{lod}"]
    tiles.append(label(crop(Image.open(R / f"review_lod{lod}_3m.png").convert("RGB")), f"LOD{lod}",
                       f"{p['tri_count']:,} tris | {p['material_count']} material | {p['file']} | round-trip {'PASS' if p['roundtrip']['passed'] else 'FAIL'}"))
c = parts["collision"]
tiles.append(label(crop(Image.open(R / "review_collision_outline.png").convert("RGB")), "Collision proxy",
                   f"{c['tri_count']} tris | 0 materials | {c['file']} | round-trip {'PASS' if c['roundtrip']['passed'] else 'FAIL'}"))
grid(tiles, 2).save(OUT / "demo_lod_collision.webp", "WEBP", quality=82, method=6)

# 2) range grid LOD x distance
tiles = []
for lod in (0, 1, 2):
    for dist in (3, 8, 20):
        im = Image.open(R / f"review_lod{lod}_{dist}m.png").convert("RGB").resize((426, 240), Image.LANCZOS)
        tiles.append(label(im, f"LOD{lod} @ {dist} m", f"{parts[f'crate_lod{lod}']['tri_count']:,} tris", h=44))
grid(tiles, 3).save(OUT / "demo_lod_range_grid.webp", "WEBP", quality=82, method=6)

# 3) texture set
tiles = []
for name, note in (("base_color", "sRGB albedo"), ("roughness", "linear"), ("metallic", "linear"), ("ao", "linear"), ("normal", "OpenGL, 16-bit")):
    im = load(RAW / f"{name}.png").resize((340, 340), Image.LANCZOS)
    tiles.append(label(im, name, note))
packed = [("albedo", "_BaseMap"), ("metallic_smoothness", "_MetallicGlossMap")]
for k, slot in packed:
    im = load(BUILD / "textures" / f"SupplyCrate__Body__{k}.png").resize((340, 340), Image.LANCZOS)
    tiles.append(label(im, f"packed: {k}", f"Unity URP {slot}"))
grid(tiles[:6], 3).save(OUT / "demo_textures.webp", "WEBP", quality=82, method=6)

# 4) hero + ortho set
hero = Image.open(R / "review_closeup.png").convert("RGB")
hero.save(OUT / "demo_hero_closeup.webp", "WEBP", quality=82, method=6)
tiles = [label(Image.open(R / f"review_{v}.png").convert("RGB").resize((426, 240), Image.LANCZOS), v) for v in ("front", "side", "top")]
grid(tiles, 3).save(OUT / "demo_orthographic.webp", "WEBP", quality=82, method=6)
print(sorted(p.name for p in OUT.iterdir()))
