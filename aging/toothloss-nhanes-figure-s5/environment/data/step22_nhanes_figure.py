#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
step22_nhanes_figure.py
=======================
A 档同源加强：Figure S5 —— NHANES 独立第四队列。

Panel A  森林图：牙周暴露（mPD / mLA / 任何 >=4mm 位点）与余留牙数 -> WBC / NLR / 白蛋白
Panel B  剂量-反应：余留牙数五分位 -> WBC（以 Q1 = 牙最多为参照）
Panel C  与主线三队列的炎症背景对比（描述性条形）

要求：300 dpi、纯英文（DejaVu Sans 无中文字形）。

输出：
  output/figures/nhanes_oral_inflammation.png
  output/figures/nhanes_oral_inflammation.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "output" / "tables"
FIG = ROOT / "output" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.dpi": 300,
    "figure.dpi": 300,
})

C_WEST = "#2b6cb0"
C_CN = "#c53030"
C_GREY = "#4a5568"


def forest(ax, rows, title, xpad=None):
    """rows: list of (label, beta, lo, hi, p, colour)"""
    y = np.arange(len(rows))[::-1]
    all_lo = min(r[2] for r in rows)
    all_hi = max(r[3] for r in rows)
    span = all_hi - all_lo
    pad = xpad if xpad is not None else span * 0.34
    for i, (lab, b, lo, hi, p, c) in zip(y, rows):
        ax.plot([lo, hi], [i, i], color=c, lw=1.7, solid_capstyle="round", zorder=3)
        ax.plot([b], [i], "o", color=c, ms=5.5, zorder=4,
                markerfacecolor=c if p < .05 else "white",
                markeredgecolor=c, markeredgewidth=1.3)
        star = "***" if p < .001 else "**" if p < .01 else "*" if p < .05 else ""
        ax.text(all_hi + pad * 0.15, i, f"{b:+.2f}{star}", va="center", ha="left",
                fontsize=7.6, color=c)
    ax.axvline(0, color="#888", lw=0.9, ls="--", zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=7.8)
    ax.set_title(title, fontsize=9.2, fontweight="bold", loc="left", pad=7)
    ax.tick_params(axis="x", labelsize=7.6)
    ax.set_xlim(all_lo - span * 0.06, all_hi + pad)
    ax.spines["left"].set_visible(False)


def main() -> int:
    t1 = pd.read_csv(TAB / "nhanes_main_models.csv")
    t2 = pd.read_csv(TAB / "nhanes_dose_response.csv")

    fig = plt.figure(figsize=(7.4, 7.4))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1.0],
                          hspace=0.46, wspace=0.62)

    # ---------------- Panel A1: 牙周 -> 三个结局
    ax1 = fig.add_subplot(gs[0, 0])
    order = [("WBC", "Perio (mPD)"), ("NLR", "Perio (mPD)"), ("ALB", "Perio (mPD)"),
             ("WBC", "Perio (mLA)"), ("NLR", "Perio (mLA)"), ("ALB", "Perio (mLA)")]
    rows = []
    for y_, m_ in order:
        r = t1[(t1["outcome"] == y_) & (t1["model"] == m_)]
        if len(r):
            r = r.iloc[0]
            rows.append((f"{y_} ~ {m_.replace('Perio ','')}",
                         r["beta"], r["ci_low"], r["ci_high"], r["p"], C_GREY))
    forest(ax1, rows, "A. Periodontal measures")
    ax1.set_xlabel("Change per 1 mm (95% CI)", fontsize=7.8)

    # ---------------- Panel A2: 余留牙数 / 无牙颌
    ax2 = fig.add_subplot(gs[0, 1])
    rows = []
    for y_ in ("WBC", "NLR", "ALB"):
        r = t1[(t1["outcome"] == y_) & (t1["model"] == "Teeth lost (per tooth) (per 10 teeth)")]
        if len(r):
            r = r.iloc[0]
            rows.append((f"{y_} ~ teeth /10", r["beta"],
                         r["ci_low"], r["ci_high"], r["p"], C_WEST))
    for y_ in ("WBC", "NLR", "ALB"):
        r = t1[(t1["outcome"] == y_) & (t1["model"] == "Edentulism")]
        if len(r):
            r = r.iloc[0]
            c = C_WEST if r["p"] < .05 else C_GREY
            rows.append((f"{y_} ~ edentulism", r["beta"],
                         r["ci_low"], r["ci_high"], r["p"], c))
    forest(ax2, rows, "B. Remaining teeth and edentulism")
    ax2.set_xlabel("Change (95% CI)", fontsize=7.8)

    # ---------------- Panel C: 剂量-反应
    ax3 = fig.add_subplot(gs[1, 0])
    qs, bs, los, his = [], [], [], []
    for _, r in t2[(t2["outcome"] == "WBC") & (t2["term"] == "d")].iterrows():
        # ⚠️ model 形如 "Teeth quintile Q2 vs Q1"，直接抽全部数字会得到 "21"
        # -> 必须只取 "vs" 之前的五分位编号
        head = r["model"].split("vs")[0]
        q = int("".join(ch for ch in head if ch.isdigit()))
        qs.append(q); bs.append(r["beta"]); los.append(r["ci_low"]); his.append(r["ci_high"])
    idx = np.argsort(qs)
    qs = np.array(qs)[idx]; bs = np.array(bs)[idx]
    los = np.array(los)[idx]; his = np.array(his)[idx]
    xq = np.concatenate([[1], qs])
    bq = np.concatenate([[0.0], bs])
    loq = np.concatenate([[0.0], los])
    hiq = np.concatenate([[0.0], his])
    ax3.axhline(0, color="#888", lw=0.9, ls="--")
    # 参照组 Q1 在 0 处（无误差棒），Q2-Q5 为估计点
    ax3.errorbar(xq, bq, yerr=[bq - loq, hiq - bq], fmt="o-", color=C_WEST,
                 ecolor=C_WEST, elinewidth=1.3, capsize=3, ms=5.5, lw=1.5, zorder=4,
                 markerfacecolor="white", markeredgecolor=C_WEST, markeredgewidth=1.3)
    ax3.plot([1], [0.0], "o", color=C_GREY, ms=5.5, zorder=5)
    ylo = min(loq.min(), 0.0)
    yhi = max(hiq.max(), 0.0)
    ypad = (yhi - ylo) * 0.20
    ax3.set_ylim(ylo - ypad, yhi + ypad * 0.9)
    ax3.text(0.03, 0.06, "Reference: Q1 (most teeth)", transform=ax3.transAxes,
             fontsize=7.2, color=C_GREY, va="bottom", ha="left")
    tr = t2[(t2["outcome"] == "WBC") & (t2["term"] == "q_num")]
    if len(tr):
        p0 = tr.iloc[0]["p"]
        b0 = tr.iloc[0]["beta"]
        ax3.text(0.97, 0.97, f"$P_{{trend}}$ = {p0:.1e}", transform=ax3.transAxes,
                 fontsize=7.4, color=C_WEST, fontweight="bold", va="top", ha="right")
        ax3.text(0.97, 0.895, f"trend {b0:+.3f} / quintile", transform=ax3.transAxes,
                 fontsize=7.0, color=C_WEST, va="top", ha="right")
    ax3.set_xticks([1, 2, 3, 4, 5])
    ax3.set_xticklabels([f"Q{i}" for i in range(1, 6)], fontsize=7.6)
    ax3.set_xlim(0.7, 5.3)
    ax3.set_xlabel("Quintile of remaining teeth (Q1 = most)", fontsize=7.8)
    ax3.set_ylabel("$\\beta$ for WBC (10$^9$/L)", fontsize=7.8)
    ax3.set_title("C. Dose-response: remaining teeth and WBC",
                  fontsize=9.2, fontweight="bold", loc="left", pad=7)
    ax3.tick_params(axis="y", labelsize=7.6)

    # ---------------- Panel D: 四队列炎症背景（CRP 与 WBC 并列，不重叠）
    ax4 = fig.add_subplot(gs[1, 1])
    labels = ["HRS\n(US)", "ELSA\n(England)", "CHARLS\n(China)", "NHANES\n(US, clinical)"]
    crp = [2.35, 1.90, 1.40, np.nan]          # 主线三队列 CRP 中位 (mg/L)
    wbc = [6.50, 6.20, 5.70, 6.60]            # NHANES 为本队列中位
    x = np.arange(len(labels))
    cols = [C_WEST, C_WEST, C_CN, "#805ad5"]
    wide = 0.34
    xl, xr = x - wide / 2 - 0.015, x + wide / 2 + 0.015

    # WBC 用次轴（右），CRP 用主轴（左），左右并排
    ax4b = ax4.twinx()
    ax4b.spines["top"].set_visible(False)
    ax4b.bar(xr, wbc, width=wide, color="#cbd5e0", zorder=1)
    for xi, c in zip(xr, wbc):
        ax4b.text(xi, c + 0.16, f"{c:.1f}", ha="center", va="bottom",
                  fontsize=6.6, color="#4a5568", zorder=6)
    ax4.bar(xl, [c if not np.isnan(c) else 0 for c in crp], width=wide,
            color=cols, alpha=0.97, zorder=2)
    for xi, c in zip(xl, crp):
        if np.isnan(c):
            ax4.annotate("n/a", xy=(xi, 0.0), xytext=(xi, 0.10),
                         ha="center", va="bottom", fontsize=6.2, color=C_GREY,
                         zorder=10)
        else:
            ax4.text(xi, c + 0.06, f"{c:.2f}", ha="center", va="bottom",
                     fontsize=6.6, color="#2d3748", fontweight="bold", zorder=10)
    ax4.set_xticks(x)
    ax4.set_xticklabels(labels, fontsize=7.3)
    ax4.set_ylabel("Median CRP (mg/L)", fontsize=7.6)
    ax4.set_ylim(0, 3.05)
    ax4b.set_ylabel("Median WBC (10$^9$/L)", fontsize=7.6, color="#4a5568")
    ax4b.set_ylim(0, 9.6)
    ax4b.tick_params(axis="y", labelsize=7.0, colors="#4a5568")
    ax4.set_title("D. Background inflammation across cohorts",
                  fontsize=9.2, fontweight="bold", loc="left", pad=7)
    ax4.tick_params(axis="y", labelsize=7.6)
    ax4.text(0.5, 1.035, "coloured = CRP (left)   |   grey = WBC (right)",
             transform=ax4.transAxes, ha="center", va="bottom",
             fontsize=6.6, color=C_GREY)

    fig.suptitle(
        "NHANES independent validation: periodontal disease and tooth loss "
        "with systemic inflammation",
        fontsize=10.2, fontweight="bold", y=0.985,
    )
    fig.text(0.012, 0.012,
             "Point estimates from OLS with HC1 robust standard errors, adjusted for age, sex, "
             "education, marital status, race and survey cycle.\n"
             "Filled markers denote p < 0.05. NHANES 2011-2014 (n = 3,028 for periodontal "
             "models; n = 4,667 for dentition models).",
             fontsize=6.8, color=C_GREY, va="bottom")

    out_png = FIG / "nhanes_oral_inflammation.png"
    out_pdf = FIG / "nhanes_oral_inflammation.pdf"
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"写入: {out_png}")
    print(f"写入: {out_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
