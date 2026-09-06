#!/usr/bin/env python3
"""
Turn the source 360 photograph into the two things the renderer actually needs:

  1. assets/sky.jpg   - a true 2:1 equirectangular sky dome. The source photo is
                        a 1584x672 panorama: full 360 across, but vertically
                        cropped to +/-76.4 deg, with the horizon on row 334.
                        We keep every sky pixel as-is, synthesise the missing
                        zenith cap, and replace everything below the horizon
                        with a haze fade (the engine draws its own ground).

  2. assets/sky_light.json
                      - order-2 spherical harmonics of the sky's radiance, plus
                        a few palette statistics pulled from the photograph's
                        ground pixels. The grass shader lights itself from these,
                        which is why the field ends up the same colour as the
                        photo instead of a colour someone guessed.

Run:  python3 tools/build_sky.py
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SRC = os.environ.get("SKY_SRC", os.path.join(ROOT, "assets", "source_panorama.jpg"))
OUT_IMG = os.path.join(ROOT, "assets", "sky.jpg")
OUT_LIGHT = os.path.join(ROOT, "assets", "sky_light.json")

OUT_W, OUT_H = 2048, 1024          # 2:1 equirectangular
JPEG_QUALITY = 90


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * (c ** (1.0 / 2.4)) - 0.055)


def find_horizon(a):
    """Sharpest brightness drop in the middle third of the frame."""
    rows = a.mean(axis=(1, 2))
    lo, hi = int(len(rows) * 0.40), int(len(rows) * 0.60)
    return lo + int(np.argmin(np.diff(rows[lo:hi])))


def blur_wrap(row, sigma):
    """Three box passes ~= a gaussian, wrapping around the 360 seam."""
    r = int(max(1, round(sigma * 1.2)))
    if r < 1:
        return row
    n = row.shape[0]
    out = row
    for _ in range(3):
        pad = np.concatenate([out[-r:], out, out[:r + 1]], axis=0)
        c = np.cumsum(pad, axis=0)
        out = (c[2 * r + 1:] - c[:-(2 * r + 1)]) / float(2 * r + 1)
    return out


def sample_rows(src, rows):
    """Bilinear vertical sampling of the source at fractional row indices."""
    h = src.shape[0]
    r = np.clip(rows, 0.0, h - 1.001)
    i0 = np.floor(r).astype(np.int32)
    f = (r - i0)[:, None, None]
    return src[i0] * (1.0 - f) + src[i0 + 1] * f


def main():
    if not os.path.exists(SRC):
        sys.exit("missing source panorama: %s" % SRC)

    img = Image.open(SRC).convert("RGB")
    src = np.asarray(img).astype(np.float32) / 255.0
    sh, sw, _ = src.shape

    horizon = find_horizon(src)
    deg_per_px = 180.0 / (sw / 2.0)          # a full equirect would be sw/2 tall
    top_el = horizon * deg_per_px            # elevation of the source's top row
    print("source %dx%d  horizon row %d  covers +%.1f/-%.1f deg  (%.4f deg/px)"
          % (sw, sh, horizon, top_el, (sh - 1 - horizon) * deg_per_px, deg_per_px))

    # ---- resample horizontally to the output width ------------------------
    wide = np.asarray(
        img.resize((OUT_W, sh), Image.LANCZOS)
    ).astype(np.float32) / 255.0

    # ---- reference colours -------------------------------------------------
    zenith_flat = wide[0:24].mean(axis=(0, 1)) * 0.82
    # Sampled clear of the skyline itself. The last few rows above the
    # horizon already contain the dark edge of the photographer's ground,
    # and dragging that into the dome draws a black hairline right across
    # the sky where our own ground is supposed to meet it.
    horizon_band = wide[horizon - 17:horizon - 5].mean(axis=0)          # (W,3)
    horizon_band = np.asarray(
        Image.fromarray((np.clip(horizon_band, 0, 1) * 255).astype(np.uint8)[None, :, :])
        .filter(ImageFilter.GaussianBlur(9))
    ).astype(np.float32)[0] / 255.0

    out = np.zeros((OUT_H, OUT_W, 3), np.float32)
    el = (0.5 - (np.arange(OUT_H) + 0.5) / OUT_H) * 180.0                # +90 .. -90

    # Everything below this is the photographer's ground, not sky.
    SKYLINE = 5.0 * deg_per_px                                           # ~1.14 deg

    # ---- 1. the photographed sky, kept verbatim ---------------------------
    keep = (el <= top_el) & (el >= SKYLINE)
    out[keep] = sample_rows(wide, horizon - el[keep] / deg_per_px)

    # ---- 2. synthesised zenith cap ----------------------------------------
    # Above the crop we fold the top of the photograph back on itself with a
    # per-row horizontal roll (kills the mirror seam), then blur each row by
    # exactly the amount that row is already stretched by the equirect
    # projection (1/cos(elevation)). That turns the folded stars into the
    # smooth glow they would become at the pole anyway, instead of a band of
    # visible dashes. The shader draws real, round zenith stars procedurally
    # in 3D on top - see starfield() in the sky pass.
    cap = el > top_el
    if cap.any():
        idx = np.nonzero(cap)[0]
        # 0 at the join with the photograph, 1 at the pole
        d = np.clip((el[idx] - top_el) / (90.0 - top_el), 0.0, 1.0)
        folded = sample_rows(wide, d * 58.0)
        stretch = 1.0 / np.maximum(np.cos(np.radians(el[idx])), 1e-3)
        stretch0 = 1.0 / np.cos(np.radians(top_el))
        for k, dv in enumerate(d):
            folded[k] = np.roll(folded[k], int(dv * 613.0), axis=0)
            sigma = 1.5 + 0.55 * max(stretch[k] - stretch0, 0.0)
            folded[k] = blur_wrap(folded[k], sigma)
        folded *= (1.0 - 0.55 * d)[:, None, None]
        w = (np.clip((d - 0.12) / 0.55, 0, 1) ** 1.3 * 0.92)[:, None, None]
        out[idx] = folded * (1.0 - w) + zenith_flat[None, None, :] * w

    # ---- 3. below the horizon: haze fade ----------------------------------
    # The engine draws real ground here; this only has to be a believable
    # colour for distance fog to land on, and to stop any seam at the skyline.
    below = el < SKYLINE
    if below.any():
        idx = np.nonzero(below)[0]
        fade = np.exp(np.minimum(el[idx] - SKYLINE, 0.0) / 7.0)[:, None, None]
        out[idx] = horizon_band[None, :, :] * fade

    # ---- 4. gentle lift of the deep shadows --------------------------------
    # JPEG blocks badly on near-black starfields. A small toe keeps the sky
    # clean; the shader pulls the black point back down on load.
    out = np.clip(out, 0.0, 1.0)
    out = out * 0.955 + 0.020

    Image.fromarray((linear_to_srgb(srgb_to_linear(out)) * 255.0 + 0.5).astype(np.uint8)).save(
        OUT_IMG, quality=JPEG_QUALITY, subsampling=0, optimize=True
    )
    print("wrote %s (%.0f KB)" % (OUT_IMG, os.path.getsize(OUT_IMG) / 1024.0))

    # ---- 5. spherical harmonics of the sky --------------------------------
    lin = srgb_to_linear(out)
    ss = 4
    small = lin.reshape(OUT_H // ss, ss, OUT_W // ss, ss, 3).mean(axis=(1, 3))
    h, w, _ = small.shape
    theta = (np.arange(h) + 0.5) / h * np.pi                 # 0 at zenith
    phi = (np.arange(w) + 0.5) / w * 2.0 * np.pi - np.pi
    st, ct = np.sin(theta), np.cos(theta)
    T, P = np.meshgrid(theta, phi, indexing="ij")
    # y up, x east, z south - matches the renderer's world axes
    dx = np.sin(T) * np.sin(P)
    dy = np.cos(T)
    dz = -np.sin(T) * np.cos(P)
    dw = (st[:, None] * (np.pi / h) * (2.0 * np.pi / w)) * np.ones((1, w))

    basis = [
        0.282095 * np.ones_like(dx),
        0.488603 * dy, 0.488603 * dz, 0.488603 * dx,
        1.092548 * dx * dy, 1.092548 * dy * dz,
        0.315392 * (3.0 * dz * dz - 1.0),
        1.092548 * dx * dz,
        0.546274 * (dx * dx - dy * dy),
    ]
    sh_coeffs = [[float(v) for v in (b[:, :, None] * small * dw[:, :, None]).sum(axis=(0, 1))]
                 for b in basis]

    # average radiance of the sky hemisphere, and of the horizon ring
    sky_only = small[: h // 2]
    avg_sky = [float(v) for v in sky_only.mean(axis=(0, 1))]
    ring = small[int(h * 0.47):int(h * 0.50)].mean(axis=(0, 1))

    # ---- 6. palette measured off the photograph's own grass ---------------
    ground = srgb_to_linear(src[int(sh * 0.60):int(sh * 0.80)])
    pct = {p: [float(v) for v in np.percentile(ground, p, axis=(0, 1))]
           for p in (10, 25, 50, 75, 90, 98)}

    # brightest patch of sky = the galactic core, used as the scene's key light
    lum = lin[: OUT_H // 2].mean(axis=2)
    k = 48
    hh, ww = lum.shape[0] // k, lum.shape[1] // k
    blocks = lum[: hh * k, : ww * k].reshape(hh, k, ww, k).mean(axis=(1, 3))
    by, bx = np.unravel_index(int(np.argmax(blocks)), blocks.shape)
    core_az = ((bx * k + k * 0.5) / OUT_W) * 360.0 - 180.0
    core_el = (0.5 - (by * k + k * 0.5) / OUT_H) * 180.0

    data = {
        "_comment": "generated by tools/build_sky.py - do not edit by hand",
        "source": {"width": sw, "height": sh, "horizonRow": horizon,
                   "degPerPixel": deg_per_px, "topElevationDeg": top_el},
        "sh": sh_coeffs,
        "avgSkyRadiance": avg_sky,
        "horizonRadiance": [float(v) for v in ring],
        "coreAzimuthDeg": core_az,
        "coreElevationDeg": core_el,
        "groundPercentiles": pct,
        "blackLift": 0.020,
        "blackScale": 0.955,
    }
    with open(OUT_LIGHT, "w") as f:
        json.dump(data, f, indent=1)
    print("wrote %s" % OUT_LIGHT)
    print("  galactic core at az %.1f el %.1f" % (core_az, core_el))
    print("  sky avg radiance %s" % np.round(avg_sky, 5))
    print("  grass median     %s" % np.round(pct[50], 5))


if __name__ == "__main__":
    main()
