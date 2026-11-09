# -*- coding: utf-8 -*-
"""Figure 2 for the Aging Cell submission: by-cohort forest plot of the association
between edentulism and biological age acceleration, with random-effects pooled
estimates.

Numbers are the FINAL fully adjusted estimates (covariate set:
age_c, female, edu_years, married, rural, ever_smoke; ELSA additionally lacks rural).
Figure text is English only (DejaVu Sans has no CJK glyphs).

Output:
    output/manuscript/submission_agingcell/figures/Figure2.png  (300 dpi)
    output/manuscript/submission_agingcell/figures/Figure2.pdf
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path("output/manuscript/submission_agingcell/figures")
OUT.mkdir(parents=True, exist_ok=True)

# ---- Final fully adjusted cohort estimates (years) --------------------------
# source: output/tables/bioage_sensitivity_covariates.csv (step = "+ 婚姻 城乡 吸烟")
COHORTS = [
    # label,      beta,   lo,     hi,     n
    ("HRS",       3.483,  2.38,   4.59,   9526),
    ("ELSA",      2.943,  0.85,   5.03,   4390),
    ("CHARLS",    0.044, -0.91,   1.00,   11384),
]
# Random-effects pools (DerSimonian-Laird)
POOLS = [
    ("Western cohorts (HRS, ELSA)", 3.366, 2.391, 4.340, 0.0),
]
POOL_ALL = ("All three cohorts", 2.104, -0.399, 4.606, 91.3)

RED, BLUE, DARK, GREY = "#b3402f", "#3b6ea5", "#1f3b57", "#888888"

rows = list(COHORTS)
n_rows = len(rows) + 1 + 1                      # cohorts + Western pool + overall pool
fig, ax = plt.subplots(figsize=(7.4, 0.62 * n_rows + 1.5))

ypos = []
y = len(rows) - 1
for (lab, b, lo, hi, n) in rows:
    ax.plot([lo, hi], [y, y], color=BLUE, lw=1.9, solid_capstyle="round")
    ax.plot([b], [y], "s", color=DARK, ms=8)
    ax.text(1.03, y, f"{b:+.2f} ({lo:+.2f}, {hi:+.2f})", transform=ax.get_yaxis_transform(),
            va="center", fontsize=8.6, family="DejaVu Sans")
    ax.text(1.03, y - 0.34, f"n = {n:,}", transform=ax.get_yaxis_transform(),
            va="center", fontsize=7.4, color="#555555", family="DejaVu Sans")
    ypos.append((y, lab, n))
    y -= 1

# Western-only pool (primary pooling for the paper)
ylab, pb, plo, phi, i2 = POOLS[0]
ax.plot([plo, phi], [y, y], color=RED, lw=2.5, solid_capstyle="round")
ax.plot([pb], [y], "D", color=RED, ms=9)
ax.text(1.03, y, f"{pb:+.2f} ({plo:+.2f}, {phi:+.2f})", transform=ax.get_yaxis_transform(),
        va="center", fontsize=8.6, color=RED, family="DejaVu Sans")
ax.text(1.03, y - 0.34, f"I² = {i2:.1f}%", transform=ax.get_yaxis_transform(),
        va="center", fontsize=7.4, color=RED, family="DejaVu Sans")
ypos.append((y, ylab, None))
y -= 1

# All-three pool
ylab, pb, plo, phi, i2 = POOL_ALL
ax.plot([plo, phi], [y, y], color=RED, lw=2.5, solid_capstyle="round", alpha=0.75)
ax.plot([pb], [y], "D", color=RED, ms=9, alpha=0.75)
ax.text(1.03, y, f"{pb:+.2f} ({plo:+.2f}, {phi:+.2f})", transform=ax.get_yaxis_transform(),
        va="center", fontsize=8.6, color=RED, family="DejaVu Sans")
ax.text(1.03, y - 0.34, f"I² = {i2:.1f}%", transform=ax.get_yaxis_transform(),
        va="center", fontsize=7.4, color=RED, family="DejaVu Sans")
ypos.append((y, ylab, None))

ax.axvline(0, color=GREY, ls="--", lw=1)

all_lo = min(r[2] for r in rows + [POOLS[0], POOL_ALL])
all_hi = max(r[3] for r in rows + [POOLS[0], POOL_ALL])
pad = 0.10 * (all_hi - all_lo)
ax.set_xlim(all_lo - pad, all_hi + pad)
ax.set_ylim(-1.35, len(rows) + 0.85)

labs_order = [p[1] for p in ypos]
ax.set_yticks([p[0] for p in ypos])
ax.set_yticklabels(labs_order, fontsize=9.5, family="DejaVu Sans")
ax.tick_params(axis="x", labelsize=8.6)
for t in ax.get_xticklabels():
    t.set_family("DejaVu Sans")

ax.set_xlabel("Additional years of biological age acceleration\n(edentulous versus dentate)",
              fontsize=9.5, labelpad=7, family="DejaVu Sans")
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)

fig.tight_layout()
fig.savefig(OUT / "Figure2.png", dpi=300, facecolor="white", bbox_inches="tight")
fig.savefig(OUT / "Figure2.pdf", facecolor="white", bbox_inches="tight")
plt.close(fig)
print("wrote", OUT / "Figure2.png")
print("wrote", OUT / "Figure2.pdf")
