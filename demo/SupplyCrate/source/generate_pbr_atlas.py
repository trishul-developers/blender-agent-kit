#!/usr/bin/env python3
"""Deterministic 2048x2048 procedural PBR atlas generator for SupplyCrate (Independent Trial).

Generates canonical raw PBR maps for Blender Agent Kit (`run.py pack`):
  - base_color.png (8-bit RGB, sRGB)
  - metallic.png   (8-bit grayscale, linear)
  - roughness.png  (8-bit grayscale, linear)
  - ao.png         (8-bit grayscale, linear)
  - normal.png     (16-bit RGB, OpenGL +Y tangent-space normal)

Atlas UV layout (normalized U in [0,1], V in [0,1], where V=0 is bottom, V=1 is top;
in image pixel coordinates y=0 is top = V=1):
  - Top-left     (U: 0.00..0.50, V: 0.50..1.00): Weathered wood planks (with horizontal plank seams)
  - Top-right    (U: 0.50..1.00, V: 0.50..1.00): Stenciled wood panel (front/back center panel with cargo markings)
  - Bottom-left  (U: 0.00..0.50, V: 0.00..0.50): Painted/chipped dark gunmetal steel (brackets, straps, latches, handles)
  - Bottom-right (U: 0.50..1.00, V: 0.00..0.50): Timber framing & skid wood (darker grain, ground grime) + brass/zinc fasteners
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def _value_noise_2d(h: int, w: int, grid_h: int, grid_w: int, rng: np.random.Generator) -> np.ndarray:
    """Tileable bilinear-interpolated value noise in [0, 1]."""
    grid = rng.random((grid_h, grid_w), dtype=np.float32)
    y = np.linspace(0, grid_h, h, endpoint=False, dtype=np.float32)
    x = np.linspace(0, grid_w, w, endpoint=False, dtype=np.float32)
    y0 = np.floor(y).astype(np.int32) % grid_h
    x0 = np.floor(x).astype(np.int32) % grid_w
    y1 = (y0 + 1) % grid_h
    x1 = (x0 + 1) % grid_w
    fy = (y - np.floor(y))
    fx = (x - np.floor(x))
    # Smoothstep
    fy = fy * fy * (3.0 - 2.0 * fy)
    fx = fx * fx * (3.0 - 2.0 * fx)
    c00 = grid[y0[:, None], x0[None, :]]
    c10 = grid[y0[:, None], x1[None, :]]
    c01 = grid[y1[:, None], x0[None, :]]
    c11 = grid[y1[:, None], x1[None, :]]
    top = c00 * (1.0 - fx[None, :]) + c10 * fx[None, :]
    bot = c01 * (1.0 - fx[None, :]) + c11 * fx[None, :]
    return top * (1.0 - fy[:, None]) + bot * fy[:, None]


def fbm_noise(h: int, w: int, octaves: list[tuple[int, int, float]], rng: np.random.Generator) -> np.ndarray:
    acc = np.zeros((h, w), dtype=np.float32)
    total_w = 0.0
    for gh, gw, weight in octaves:
        acc += _value_noise_2d(h, w, gh, gw, rng) * weight
        total_w += weight
    return acc / max(total_w, 1e-6)


def write_png_16bit_rgb(path: Path, arr_01: np.ndarray) -> None:
    """Write an uncompressed/zlib-compressed true 16-bit RGB PNG (big-endian)."""
    arr16 = np.clip(np.round(arr_01 * 65535.0), 0, 65535).astype(">u2")
    h, w, c = arr16.shape
    assert c == 3
    raw_rows = []
    for row in range(h):
        raw_rows.append(b"\x00" + arr16[row].tobytes())
    raw_data = b"".join(raw_rows)
    compressed = zlib.compress(raw_data, level=6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 16, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    path.write_bytes(png)


def _wood_region(h: int, w: int, rng: np.random.Generator, planks: int = 5, darker: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate weathered timber wood grain (base_rgb, metallic, roughness, ao, height)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = xx / w
    v = yy / h

    # Elongated anisotropic fibers along X (horizontal planks)
    warp = fbm_noise(h, w, [(8, 4, 0.5), (16, 8, 0.35), (32, 16, 0.15)], rng)
    fine_grain = fbm_noise(h, w, [(128, 16, 0.45), (256, 32, 0.35), (512, 64, 0.20)], rng)
    rings = np.sin((v * 55.0 + warp * 4.5) * np.pi) * 0.5 + 0.5
    grain = np.clip(0.55 * fine_grain + 0.45 * rings, 0.0, 1.0)

    # Plank segmentation along Y
    plank_idx = np.floor(v * planks).astype(np.int32)
    plank_local_v = (v * planks) - plank_idx
    plank_tint = rng.uniform(-0.08, 0.08, size=planks).astype(np.float32)[np.clip(plank_idx, 0, planks - 1)]

    # Plank seams (dark groove + AO drop + height depression)
    seam_dist = np.minimum(plank_local_v, 1.0 - plank_local_v)
    seam_mask = np.clip(seam_dist / 0.032, 0.0, 1.0)
    seam_mask = seam_mask * seam_mask * (3.0 - 2.0 * seam_mask)

    # Dirt & weathering grime
    grime = fbm_noise(h, w, [(6, 6, 0.5), (18, 18, 0.3), (48, 48, 0.2)], rng)
    scratches = fbm_noise(h, w, [(64, 8, 0.6), (128, 12, 0.4)], rng)
    scratch_mask = np.clip((scratches - 0.72) * 5.0, 0.0, 1.0)

    # Base wood palette (warm weathered spruce/pine or darker timber framing)
    if darker:
        c_light = np.array([0.42, 0.30, 0.19], dtype=np.float32)
        c_dark = np.array([0.21, 0.14, 0.08], dtype=np.float32)
    else:
        c_light = np.array([0.56, 0.43, 0.28], dtype=np.float32)
        c_dark = np.array([0.31, 0.21, 0.13], dtype=np.float32)

    base = c_dark[None, None, :] * (1.0 - grain[:, :, None]) + c_light[None, None, :] * grain[:, :, None]
    base = np.clip(base + plank_tint[:, :, None], 0.04, 0.95)

    # Apply grime darkening and lighter edge scuffs
    dirt_factor = np.clip((grime - 0.42) * 0.9, 0.0, 0.45)
    base *= (1.0 - dirt_factor[:, :, None])
    base = base * (1.0 - 0.35 * scratch_mask[:, :, None]) + np.array([0.62, 0.52, 0.39], dtype=np.float32) * (0.35 * scratch_mask[:, :, None])

    # Darken plank seams
    base *= (0.28 + 0.72 * seam_mask[:, :, None])

    # Subtle edge darkening around quadrant border for ambient crevice feel
    edge_dist = np.minimum(np.minimum(u, 1.0 - u), np.minimum(v, 1.0 - v))
    edge_ao = np.clip(edge_dist / 0.04, 0.55, 1.0)

    metallic = np.zeros((h, w), dtype=np.float32)
    roughness = np.clip(0.66 + 0.22 * (1.0 - grain) + 0.14 * dirt_factor - 0.15 * scratch_mask, 0.38, 0.96)
    ao = np.clip((0.35 + 0.65 * seam_mask) * edge_ao * (0.85 + 0.15 * grain), 0.15, 1.0)
    height = np.clip(0.25 + 0.55 * seam_mask + 0.18 * grain - 0.08 * scratch_mask, 0.0, 1.0)
    return base, metallic, roughness, ao, height


def _add_stencil_overlay(base: np.ndarray, roughness: np.ndarray, height: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Paint weathered industrial stencil markings onto the top-right wood panel quadrant."""
    h, w, _ = base.shape
    mask_img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask_img)

    # Try DejaVuSans-Bold if present, fallback to default
    font_lg = None
    font_sm = None
    for fpath in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if Path(fpath).is_file():
            font_lg = ImageFont.truetype(fpath, int(h * 0.095))
            font_sm = ImageFont.truetype(fpath, int(h * 0.048))
            break
    if font_lg is None:
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    # Stencil frame bars
    pad_x = int(w * 0.08)
    draw.rectangle([pad_x, int(h * 0.12), w - pad_x, int(h * 0.155)], fill=230)
    draw.rectangle([pad_x, int(h * 0.845), w - pad_x, int(h * 0.88)], fill=230)

    # Diagonal hazard stripes in bottom strip
    stripe_y0, stripe_y1 = int(h * 0.72), int(h * 0.81)
    for sx in range(pad_x, w - pad_x, int(w * 0.08)):
        poly = [
            (sx, stripe_y1),
            (sx + int(w * 0.038), stripe_y1),
            (sx + int(w * 0.068), stripe_y0),
            (sx + int(w * 0.030), stripe_y0),
        ]
        draw.polygon(poly, fill=220)

    # Stencil typography
    draw.text((int(w * 0.10), int(h * 0.22)), "SUPPLY // 04-B", fill=245, font=font_lg)
    draw.text((int(w * 0.10), int(h * 0.39)), "GROSS WT: 48 KG", fill=230, font=font_sm)
    draw.text((int(w * 0.10), int(h * 0.50)), "FIELD LOGISTICS UNIT", fill=215, font=font_sm)
    draw.text((int(w * 0.10), int(h * 0.60)), "KEEP DRY  •  THIS SIDE UP", fill=215, font=font_sm)

    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=0.8))
    stencil = np.asarray(mask_img, dtype=np.float32) / 255.0

    # Chipping wear so stencil looks painted over rough wood
    wear = fbm_noise(h, w, [(12, 12, 0.45), (36, 36, 0.35), (96, 96, 0.20)], rng)
    chipped = np.clip(stencil * np.clip((wear - 0.28) * 2.3, 0.0, 1.0), 0.0, 0.92)

    # Off-white/amber stencil paint on top half, hazard yellow on stripes
    paint_color = np.zeros_like(base)
    paint_color[:, :] = np.array([0.84, 0.81, 0.73], dtype=np.float32)
    paint_color[stripe_y0:stripe_y1, :] = np.array([0.86, 0.64, 0.14], dtype=np.float32)

    out_base = base * (1.0 - chipped[:, :, None]) + paint_color * chipped[:, :, None]
    out_rough = roughness * (1.0 - 0.35 * chipped) + 0.52 * (0.35 * chipped)
    out_height = np.clip(height + 0.03 * chipped, 0.0, 1.0)
    return out_base, out_rough, out_height


def _metal_region(h: int, w: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate painted/weathered industrial dark steel with bare metallic edge chips and subtle rust."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = xx / w
    v = yy / h

    brushed = fbm_noise(h, w, [(16, 128, 0.5), (32, 256, 0.35), (64, 512, 0.15)], rng)
    mottle = fbm_noise(h, w, [(8, 8, 0.5), (24, 24, 0.3), (64, 64, 0.2)], rng)
    chips_n = fbm_noise(h, w, [(20, 20, 0.45), (64, 64, 0.35), (128, 128, 0.20)], rng)
    rust_n = fbm_noise(h, w, [(12, 12, 0.5), (40, 40, 0.5)], rng)

    # Edge-chipping mask stronger near quadrant edges and high-frequency peaks
    edge_d = np.minimum(np.minimum(u, 1.0 - u), np.minimum(v, 1.0 - v))
    edge_bias = np.clip(1.0 - edge_d / 0.09, 0.0, 1.0)
    bare_metal = np.clip((chips_n + 0.45 * edge_bias - 0.68) * 6.0, 0.0, 1.0)
    rust_mask = np.clip((rust_n - 0.67) * 5.0, 0.0, 1.0) * (1.0 - bare_metal) * 0.75

    # Dark olive-charcoal powder coat vs bright bare steel vs oxide rust
    coat_col = np.array([0.14, 0.16, 0.15], dtype=np.float32) * (0.85 + 0.30 * mottle[:, :, None])
    steel_col = np.array([0.62, 0.64, 0.66], dtype=np.float32) * (0.85 + 0.30 * brushed[:, :, None])
    rust_col = np.array([0.36, 0.17, 0.08], dtype=np.float32) * (0.80 + 0.40 * rust_n[:, :, None])

    base = coat_col * (1.0 - bare_metal[:, :, None]) + steel_col * bare_metal[:, :, None]
    base = base * (1.0 - rust_mask[:, :, None]) + rust_col * rust_mask[:, :, None]

    # Metallic: powder-coated steel ~0.35 (semi-metallic paint), bare steel ~0.94, rust ~0.05
    metallic = np.clip(0.35 * (1.0 - bare_metal) + 0.94 * bare_metal - 0.30 * rust_mask, 0.04, 0.98)
    roughness = np.clip(0.46 + 0.18 * mottle - 0.22 * bare_metal + 0.32 * rust_mask, 0.18, 0.92)
    ao = np.clip(0.84 + 0.16 * mottle - 0.12 * rust_mask, 0.35, 1.0)
    height = np.clip(0.58 + 0.08 * brushed - 0.14 * bare_metal + 0.06 * rust_mask, 0.0, 1.0)
    return base, metallic, roughness, ao, height


def height_to_normal_opengl(height: np.ndarray, strength: float = 3.2) -> np.ndarray:
    """Convert scalar heightmap in [0, 1] to OpenGL (+Y up) tangent-space normal RGB in [0, 1]."""
    # Sobel-like central differences with edge clamping
    hp = np.pad(height, 1, mode="edge")
    # dx: positive right (+X)
    dx = (
        (hp[0:-2, 2:] + 2.0 * hp[1:-1, 2:] + hp[2:, 2:])
        - (hp[0:-2, 0:-2] + 2.0 * hp[1:-1, 0:-2] + hp[2:, 0:-2])
    ) * 0.25
    # dy: in image space row increases downward (-V), so +V is (row-1) - (row+1)
    dy_v = (
        (hp[0:-2, 0:-2] + 2.0 * hp[0:-2, 1:-1] + hp[0:-2, 2:])
        - (hp[2:, 0:-2] + 2.0 * hp[2:, 1:-1] + hp[2:, 2:])
    ) * 0.25

    nx = -dx * strength
    ny = -dy_v * strength
    nz = np.ones_like(height, dtype=np.float32)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz + 1e-8)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len
    normal = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], axis=-1)
    return np.clip(normal, 0.0, 1.0)


def generate_atlas(out_dir: Path, size: int = 2048, seed: int = 42) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    half = size // 2

    base = np.zeros((size, size, 3), dtype=np.float32)
    metallic = np.zeros((size, size), dtype=np.float32)
    roughness = np.zeros((size, size), dtype=np.float32)
    ao = np.ones((size, size), dtype=np.float32)
    height = np.full((size, size), 0.5, dtype=np.float32)

    # Q1: Top-Left (y: 0..half, x: 0..half) -> UV (0..0.5, 0.5..1.0): Weathered wood planks
    b1, m1, r1, a1, h1 = _wood_region(half, half, rng, planks=5, darker=False)
    base[:half, :half] = b1
    metallic[:half, :half] = m1
    roughness[:half, :half] = r1
    ao[:half, :half] = a1
    height[:half, :half] = h1

    # Q2: Top-Right (y: 0..half, x: half..size) -> UV (0.5..1.0, 0.5..1.0): Stenciled wood panel
    b2, m2, r2, a2, h2 = _wood_region(half, half, rng, planks=5, darker=False)
    b2, r2, h2 = _add_stencil_overlay(b2, r2, h2, rng)
    base[:half, half:] = b2
    metallic[:half, half:] = m2
    roughness[:half, half:] = r2
    ao[:half, half:] = a2
    height[:half, half:] = h2

    # Q3: Bottom-Left (y: half..size, x: 0..half) -> UV (0..0.5, 0..0.5): Weathered dark steel
    b3, m3, r3, a3, h3 = _metal_region(half, half, rng)
    base[half:, :half] = b3
    metallic[half:, :half] = m3
    roughness[half:, :half] = r3
    ao[half:, :half] = a3
    height[half:, :half] = h3

    # Q4: Bottom-Right (y: half..size, x: half..size) -> UV (0.5..1.0, 0..0.5): Darker framing/skid wood + brass strip at bottom-right corner
    b4, m4, r4, a4, h4 = _wood_region(half, half, rng, planks=4, darker=True)
    # Add brushed galvanized/brass fastener patch in bottom-right sub-quadrant (last 25% of Q4)
    sub = half // 4
    bf_noise = fbm_noise(sub, sub, [(8, 8, 0.6), (32, 32, 0.4)], rng)
    b4[-sub:, -sub:] = np.array([0.72, 0.62, 0.42], dtype=np.float32) * (0.85 + 0.25 * bf_noise[:, :, None])
    m4[-sub:, -sub:] = 0.90
    r4[-sub:, -sub:] = np.clip(0.28 + 0.16 * bf_noise, 0.18, 0.50)
    a4[-sub:, -sub:] = 0.92
    h4[-sub:, -sub:] = 0.65 + 0.08 * bf_noise

    base[half:, half:] = b4
    metallic[half:, half:] = m4
    roughness[half:, half:] = r4
    ao[half:, half:] = a4
    height[half:, half:] = h4

    normal = height_to_normal_opengl(height, strength=3.4)

    # Save canonical raw PNGs
    Image.fromarray(np.clip(np.round(base * 255.0), 0, 255).astype(np.uint8), mode="RGB").save(out_dir / "base_color.png")
    Image.fromarray(np.clip(np.round(metallic * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "metallic.png")
    Image.fromarray(np.clip(np.round(roughness * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "roughness.png")
    Image.fromarray(np.clip(np.round(ao * 255.0), 0, 255).astype(np.uint8), mode="L").save(out_dir / "ao.png")
    write_png_16bit_rgb(out_dir / "normal.png", normal)

    meta = {
        "seed": seed,
        "resolution": [size, size],
        "normal_convention": "opengl",
        "normal_bit_depth": 16,
        "maps": {
            "base_color": str(out_dir / "base_color.png"),
            "metallic": str(out_dir / "metallic.png"),
            "roughness": str(out_dir / "roughness.png"),
            "ao": str(out_dir / "ao.png"),
            "normal": str(out_dir / "normal.png"),
        },
        "stats": {
            "metallic_min_max": [float(metallic.min()), float(metallic.max())],
            "roughness_min_max": [float(roughness.min()), float(roughness.max())],
            "ao_min_max": [float(ao.min()), float(ao.max())],
            "normal_mean_rgb": [float(normal[:, :, 0].mean()), float(normal[:, :, 1].mean()), float(normal[:, :, 2].mean())],
        },
    }
    (out_dir / "atlas_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    p = argparse.ArgumentParser(description="Generate procedural 2048x2048 PBR atlas for SupplyCrate")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--size", type=int, default=2048)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    meta = generate_atlas(args.out, size=args.size, seed=args.seed)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
