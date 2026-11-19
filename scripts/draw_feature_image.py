#!/usr/bin/env python
"""Draw met-bazarr's README banner: continuous fields breaking into chunks.

Three stacked layers stand for meteorological fields at different levels (say
humidity near the ground, temperature, and wind aloft). On the left they are
continuous, as they arrive from the source archive. Moving right, each layer
cracks along a regular grid; the pieces separate, gain a little thickness and
shrink, ending as an ordered set of independent, compressed chunks.

The fields are synthetic (a few large-scale waves plus some highs and lows),
so the image says nothing about any real store; it only shows the idea.

    uv run --with matplotlib python scripts/draw_feature_image.py docs/img/feature.png

matplotlib is not a met-bazarr dependency; `--with` installs it for this run only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from matplotlib.transforms import Affine2D  # noqa: E402

BG = "#0a0e17"
TITLE = "#ffffff"
SUBTITLE = "#9db0c7"
NOTE = "#6f7d93"
FONT = "DejaVu Sans"

NI, NJ = 18, 7  # tiles along x and along depth
T = 24  # field pixels per tile side
NX, NY = NI * T, NJ * T

SX = 2.05  # screen px per field pixel along x
DEPTH = (0.85, 0.5)  # screen offset per field pixel of depth
LEVEL_DZ = 112  # screen px between levels
X0, Y0 = 70, 48  # screen position of the bottom layer's front-left corner
I0 = 5.0  # columns left of this stay a continuous field
GAP = 10.0  # field pixels between fully separated chunks
SHRINK = 0.34  # how much smaller the chunks end up: the compression
THICKNESS = 5.0  # screen px of a fully separated chunk's edge

LAYERS = [  # (seed, colour map), bottom to top
    (3, "YlGnBu_r"),  # humidity near the surface
    (5, "plasma"),  # temperature
    (8, "viridis"),  # wind speed aloft
]


def synthetic_field(seed: int) -> np.ndarray:
    """A smooth, weather-like field on [0, 1]: waves plus highs and lows."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:NY, 0:NX] / NY
    f = np.zeros((NY, NX))
    for _ in range(6):
        kx, ky = rng.uniform(0.5, 3.0), rng.uniform(0.5, 2.5)
        phase = rng.uniform(0, 6)
        f += rng.uniform(0.3, 1.0) * np.sin(
            2 * np.pi * (kx * xx / 2.6 + ky * yy) + phase
        )
    for _ in range(4):
        cx, cy = rng.uniform(0, NX / NY), rng.uniform(0, 1)
        s = rng.uniform(0.12, 0.3)
        sign = rng.choice([-1, 1])
        f += sign * 1.6 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s))
    return (f - f.min()) / (f.max() - f.min())


def smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def separation(i: int) -> float:
    """0 for a column still part of the continuous field, 1 for a separate chunk."""
    return smoothstep((i - I0) / (NI - 1 - I0))


def draw(out: Path) -> None:
    fig = plt.figure(figsize=(16, 6), dpi=100, facecolor=BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1600)
    ax.set_ylim(0, 600)
    ax.axis("off")

    # Each column's left edge: gaps open up as the columns separate, so the
    # chunks stay on a regular grid rather than scattering.
    xs = [0.0]
    for i in range(1, NI):
        g = separation(i)
        xs.append(xs[-1] + T + GAP * g + 2.2 * GAP * g**2)

    tiles = []
    for k, (seed, cmap) in enumerate(LAYERS):
        field = synthetic_field(seed)
        for j in range(NJ):
            for i in range(NI):
                g = separation(i)
                cu = xs[i] + T / 2
                cv = (j + 0.5) * T + g * (j - (NJ - 1) / 2) * GAP * 0.9
                tiles.append((k, j, i, cu, cv, g, field, cmap))

    # Lower layers first, then far rows before near ones.
    tiles.sort(key=lambda t: (t[0], -t[1], t[2]))
    oblique = np.array([[SX, DEPTH[0], 0], [0, DEPTH[1], 0], [0, 0, 1]], float)
    square = np.array([[0, 0], [T, 0], [T, T], [0, T]], float)
    for k, j, i, cu, cv, g, field, cmap in tiles:
        sub = field[j * T : (j + 1) * T, i * T : (i + 1) * T]
        scale = 1 - SHRINK * g
        size = T * scale
        lift = g * 26 * (k + 0.6)
        to_screen = Affine2D().scale(scale).translate(cu - size / 2, cv - size / 2)
        to_screen += Affine2D(oblique).translate(X0, Y0 + k * LEVEL_DZ + lift)
        z = 10 + k
        corners = to_screen.transform(square)
        if g > 0.02:
            colour = np.array(plt.get_cmap(cmap)(float(sub.mean()))[:3])
            th = THICKNESS * g
            down = np.array([0, th])
            front = [corners[0], corners[1], corners[1] - down, corners[0] - down]
            side = [corners[1], corners[2], corners[2] - down, corners[1] - down]
            ax.add_patch(
                Polygon(front, closed=True, fc=0.45 * colour, ec="none", zorder=z)
            )
            ax.add_patch(
                Polygon(side, closed=True, fc=0.32 * colour, ec="none", zorder=z)
            )
        pad = 0.6 if g <= 0.02 else 0.0  # overlap neighbours to hide seams
        ax.imshow(
            sub,
            cmap=cmap,
            vmin=0,
            vmax=1,
            extent=(-pad, T + pad, -pad, T + pad),
            origin="lower",
            transform=to_screen + ax.transData,
            interpolation="bilinear",
            zorder=z,
        )
        if g > 0.02:
            edge = (1, 1, 1, 0.12 + 0.35 * g)
            ax.add_patch(
                Polygon(
                    corners,
                    closed=True,
                    fill=False,
                    ec=edge,
                    lw=0.5 + 0.5 * g,
                    zorder=z,
                )
            )

    ax.text(
        70,
        540,
        "met-bazarr",
        color=TITLE,
        fontsize=40,
        fontweight="bold",
        fontfamily=FONT,
    )
    ax.text(
        72,
        505,
        "meteorological fields, made into chunked, compressed Zarr stores",
        color=SUBTITLE,
        fontsize=17,
        fontfamily=FONT,
    )
    ax.text(
        70,
        14,
        "ERA5 · Met Office UM · …   (GRIB, NetCDF, PP)",
        color=NOTE,
        fontsize=13,
        fontfamily=FONT,
    )
    ax.text(
        1530,
        14,
        "one compressed chunk per hour, region and level band",
        color=NOTE,
        fontsize=13,
        fontfamily=FONT,
        ha="right",
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG, dpi=200)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    draw(Path(sys.argv[1] if len(sys.argv) > 1 else "docs/img/feature.png"))
