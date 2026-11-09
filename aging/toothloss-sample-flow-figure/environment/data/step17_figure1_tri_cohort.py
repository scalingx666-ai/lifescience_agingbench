# -*- coding: utf-8 -*-
"""step17_figure1_tri_cohort.py —— 第二篇 Figure 1（三队列版样本流程图）
================================================================================
用户指令（2026-10-10）：Figure 1 须重做为**三队列版**（旧 fig1 是五队列认知版）。

数据源：`output/tables/sample_flow_tri_cohort.csv`（由 step16 生成，
        与 step13.build_analysis_frame() 逐步对齐，末节点 n 与主模型精确一致）。

图内文字**全英文**（DejaVu Sans 无中文字形，且便于直接投稿）。
版式：左→右三列（HRS / ELSA / CHARLS），每列自上而下六步，
      末节点用色块突出「分析样本」。横向箭头表示流向，排除框挂在右侧。

输出：output/figures/figure1_sample_flow_tri_cohort.png（300 dpi）
      output/figures/figure1_sample_flow_tri_cohort.pdf
运行：python step17_figure1_tri_cohort.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
warnings.filterwarnings("ignore")
from config import OUT_TAB, OUT_FIG  # noqa: E402

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.unicode_minus": False,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})

C_BOX = "#3b6ea5"       # 主流程框
C_BOX_EDGE = "#264d73"
C_EXCL = "#b3402f"      # 排除框
C_EXCL_EDGE = "#83301f"
C_FINAL = "#1f6b3a"     # 分析样本框
C_FINAL_EDGE = "#124a26"
C_EXCL_BG = "#fbeceb"
C_GREY = "#555555"

STEPS = [
    ("S1_baseline_ids",   "Baseline interview\nparticipants"),
    ("S3_matched_blood",  "With linked\nblood sample"),
    ("S4_timing_ok",      "Blood strictly after\nexposure (1–12 y)"),
    ("S6_outcome_ok",     "Biological age\ncomputable"),
    ("S7_covariates_ok",  "Complete covariates\n(analytic sample)"),
]
EXCL = [
    ("S3_dropped", "No blood sample"),
    ("S4_dropped", "Contemporaneous or\noutside window"),
    ("S6_dropped", "Insufficient biomarkers\nfor KDM"),
    ("S7_dropped", "Missing covariates"),
]


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "—"


def draw(flow: pd.DataFrame) -> None:
    cohorts = ["HRS", "ELSA", "CHARLS"]
    labels = {"HRS": "HRS\n(United States)", "ELSA": "ELSA\n(England)",
              "CHARLS": "CHARLS\n(China)"}

    n_step = len(STEPS)
    fig_w = 13.6
    fig_h = 6.2
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    col_w = 17.5            # 主框宽
    excl_w = 11.0           # 排除框宽
    gap = 1.3
    box_h = 9.6
    top = 72.0              # 第一个框顶
    v_gap = 3.0

    # 列起点：每列占 (col_w + gap + excl_w) = 29.8
    starts = [1.5, 35.5, 69.5]

    def ytop(i):
        return top - i * (box_h + v_gap)

    def box(x, y, w, h, text, fc, ec, tc="white", fs=9.6, bold=False, radius=0.9):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
            linewidth=1.4, facecolor=fc, edgecolor=ec, zorder=3))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                color=tc, fontsize=fs, zorder=4,
                fontweight=("bold" if bold else "normal"), linespacing=1.35)

    def arrow(x0, y0, x1, y1, color=C_GREY, lw=1.5, style="-|>", rad=0.0):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style,
                                     mutation_scale=13, color=color, lw=lw,
                                     connectionstyle=f"arc3,rad={rad}", zorder=2))

    row = {c: flow[flow.cohort == c].iloc[0] for c in cohorts}

    for start, coh in zip(starts, cohorts):
        r = row[coh]
        cx = start + col_w / 2
        # 队列标题（放在首个主框正上方；顶部留白给大标题）
        ax.text(cx, top + box_h + 2.4, labels[coh], ha="center", va="bottom",
                fontsize=11.0, fontweight="bold", color=C_BOX_EDGE, linespacing=1.3)

        for i, (key, lab) in enumerate(STEPS):
            y = ytop(i)
            n = r.get(key, np.nan)
            is_final = (i == n_step - 1)
            txt = f"{lab}\nn = {fmt(n)}"
            box(start, y, col_w, box_h, txt,
                C_FINAL if is_final else C_BOX,
                C_FINAL_EDGE if is_final else C_BOX_EDGE,
                fs=10.2 if is_final else 9.8, bold=is_final)
            if i > 0:
                arrow(cx, ytop(i - 1), cx, y + box_h,
                      color=C_FINAL_EDGE if is_final else C_BOX_EDGE, lw=1.7)
            # 排除框：挂在主框右侧、垂直居中
            if i < len(EXCL):
                ekey, elab = EXCL[i]
                en = r.get(ekey, np.nan)
                ex = start + col_w + gap
                ey = y + (box_h - box_h) / 2
                box(ex, ey, excl_w, box_h,
                    f"{elab}\nn = {fmt(en)}", C_EXCL_BG, C_EXCL_EDGE,
                    tc=C_EXCL_EDGE, fs=8.2)
                arrow(start + col_w, y + box_h / 2, ex, ey + box_h / 2,
                      color=C_EXCL_EDGE, lw=1.2, style="-|>")

    # ---- 顶部大标题（置于列头之上的独立一行） ----
    ax.text(50, 97.5, "Sample flow: tooth loss (baseline) to biological age acceleration (follow-up blood sample)",
            ha="center", va="center", fontsize=12.4, fontweight="bold", color="#1a1a1a")

    # ---- 底部注释（分两行，确保不越界） ----
    note = ("Exclusions are applied sequentially and are cohort-specific. "
            "The analytic sample (green) is identical to that of the primary model in Table 2.\n"
            "ELSA did not collect area of residence; its models therefore adjusted for five covariates rather than six.")
    ax.text(50, 4.0, note, ha="center", va="center", fontsize=8.4,
            color=C_GREY, linespacing=1.5)

    fig.subplots_adjust(left=0.012, right=0.988, top=0.99, bottom=0.01)
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    png = OUT_FIG / "figure1_sample_flow_tri_cohort.png"
    pdf = OUT_FIG / "figure1_sample_flow_tri_cohort.pdf"
    fig.savefig(png, dpi=300)
    fig.savefig(pdf)
    plt.close(fig)
    print(f"[ok] {png}")
    print(f"[ok] {pdf}")


def main() -> None:
    f = OUT_TAB / "sample_flow_tri_cohort.csv"
    if not f.exists():
        raise SystemExit("先运行 step16_tri_cohort_extras.py 生成样本流表")
    flow = pd.read_csv(f)
    draw(flow)


if __name__ == "__main__":
    main()
