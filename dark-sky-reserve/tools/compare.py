#!/usr/bin/env python3
"""
Compare a screenshot of the renderer against the source photograph.

This is the tool the palette was actually tuned with, and it is here
because "does it look right" is not a question you can answer by eye at
these light levels - everything below the skyline is within a few percent
of black, and the eye has no absolute reference down there.

A perspective frame is not linear in elevation or azimuth, so every pixel
of the render is mapped to a real (azimuth, elevation) direction and the
photograph is sampled along the same rays. Only then is a brightness
ratio meaningful. A ratio of 1.0 means the render put the same light in
that part of the sphere as the camera recorded.

Take a screenshot with P (or the Save a frame button), then:

    python3 tools/compare.py shot.png [yaw_deg] [pitch_deg] [fov_y_deg]

Yaw and pitch are shown in the readout; the default field of view is 68.
"""

import sys

import numpy as np
from PIL import Image
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'assets', 'source_panorama.jpg')

HORIZON, DEG_PER_PX = 334, 180.0 / 792.0

BANDS = [("ground -40..-20", -40, -20), ("ground -20..-9", -20, -9),
         ("ground  -9..-2", -9, -2.0), ("sky    +1..+8", 1.0, 8),
         ("sky    +8..+22", 8, 22), ("sky   +22..+50", 22, 50)]


def main(shot, yaw_deg=0.0, pitch_deg=0.0, fov_y=68.0):
    photo = np.asarray(Image.open(SRC).convert('RGB'), np.float32) / 255.0
    ph, pw, _ = photo.shape
    ren = np.asarray(Image.open(shot).convert('RGB'), np.float32) / 255.0
    h, w, _ = ren.shape

    ty = np.tan(np.radians(fov_y) / 2.0)
    tx = ty * (w / h)
    cx, cy = np.meshgrid(((np.arange(w) + 0.5) / w * 2 - 1) * tx,
                         (1 - (np.arange(h) + 0.5) / h * 2) * ty, indexing='xy')
    d = np.stack([cx, cy, -np.ones_like(cx)], axis=-1)
    d /= np.linalg.norm(d, axis=-1, keepdims=True)

    p = np.radians(pitch_deg)
    dy = d[..., 1] * np.cos(p) - d[..., 2] * np.sin(p)
    dz = d[..., 1] * np.sin(p) + d[..., 2] * np.cos(p)
    y_ = np.radians(yaw_deg)
    wx = d[..., 0] * np.cos(y_) + dz * np.sin(y_)
    wz = -d[..., 0] * np.sin(y_) + dz * np.cos(y_)

    el = np.degrees(np.arcsin(np.clip(dy, -1, 1)))
    az = np.degrees(np.arctan2(wx, -wz))

    pu = np.clip(((az / 360.0 + 0.5) * pw).astype(np.int32), 0, pw - 1)
    pv = np.clip((HORIZON - el / DEG_PER_PX).astype(np.int32), 0, ph - 1)
    matched = photo[pv, pu]

    print("%-16s %-26s %-26s %s" % ("band", "render", "photograph", "ratio"))
    for name, lo, hi in BANDS:
        m = (el >= lo) & (el < hi)
        if m.sum() < 200:
            continue
        r, q = ren[m].mean(axis=0), matched[m].mean(axis=0)
        print("%-16s %-26s %-26s %s" % (
            name, np.round(r, 4), np.round(q, 4),
            np.round(r / np.maximum(q, 1e-4), 3)))


if __name__ == '__main__':
    main(sys.argv[1], *(float(x) for x in sys.argv[2:]))
