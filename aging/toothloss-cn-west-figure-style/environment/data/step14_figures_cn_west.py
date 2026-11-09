# -*- coding: utf-8 -*-
"""step14_figures_cn_west.py —— 第二篇的中西方差异图组（Figure 2 / Figure 3）。

配套 `china_west_narrative.md` 的图表规划：
  Figure 2  协变量阶梯图（横轴调整层级，纵轴 β，三队列三色线 + 95%CI）
  Figure 3  机制对比三联图（A CRP 分布 / B 缺牙→CRP 效应 / C 效应量对比）

样式与 `step6_figures.py` 保持一致（白底、DejaVu Sans、无网格线噪点）。
⚠️ 所有数字来自真实数据；不使用演示模式。
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

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

warnings.filterwarnings("ignore")

from config import OUT_FIG  # noqa: E402
from step13_sensitivity import (  # noqa: E402
    load_frames, build_analysis_frame, fit_one, PRIMARY_METRIC, COV_LADDER,
)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

C_HRS = "#b3402f"      # 美国（暖色）
C_ELSA = "#e0a060"     # 英国（浅暖）
C_CHARLS = "#5f5e5a"   # 中国（灰）
COH_COLOR = {"HRS": C_HRS, "ELSA": C_ELSA, "CHARLS": C_CHARLS}
C_GREY = "#666666"


# ======================================================================
# Figure 2 —— 协变量阶梯
# ======================================================================
COV_LADDER_EN = [
    ("Unadjusted",        []),
    ("+ age",             ["age_c"]),
    ("+ sex, education",  ["age_c", "female", "edu_years"]),
    ("+ marital, area,\nsmoking", ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]),
]


def figure2_covariate_ladder(m: pd.DataFrame) -> str:
    """横轴 = 调整层级；纵轴 = β（年）；三队列三色线 + 95%CI 误差棒。"""
    labels = [lab for lab, _ in COV_LADDER_EN]
    xs = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.4, 4.6))

    for coh in ["HRS", "ELSA", "CHARLS"]:
        betas, los, his = [], [], []
        for _, covs in COV_LADDER_EN:
            r = fit_one(m[m.cohort == coh], PRIMARY_METRIC, covs)
            if r is None:
                betas.append(np.nan); los.append(np.nan); his.append(np.nan)
            else:
                betas.append(r["beta"]); los.append(r["lo"]); his.append(r["hi"])
        betas = np.array(betas, float)
        err = np.array([betas - np.array(los, float), np.array(his, float) - betas])
        ax.errorbar(xs, betas, yerr=err, marker="o", ms=6.5, lw=1.9,
                    capsize=3.5, color=COH_COLOR[coh], label=coh,
                    markeredgecolor="white", markeredgewidth=0.8)

    ax.axhline(0, color="#999999", ls="--", lw=1)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=8.8)
    ax.set_ylabel("β for edentulism (years of biological ageing)", fontsize=10)
    ax.set_title("Effect of edentulism on biological ageing across adjustment levels",
                 fontsize=11.5, pad=10)
    ax.legend(frameon=False, fontsize=9.5, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    p = OUT_FIG / "figure2_covariate_ladder.png"
    fig.savefig(p, dpi=300)
    plt.close(fig)
    return str(p)


# ======================================================================
# Figure 3 —— 机制对比三联图
# ======================================================================
def _crp_effect(m: pd.DataFrame, adjust_age: bool = True) -> dict:
    """队列内 lnCRP ~ 无牙颌 (+ ln(age))，返回 % 变化及 95%CI（逐队自比，单位无关）。

    `adjust_age=True` 为论文主口径：调整年龄后中西方差异才凸显
    （实测 CHARLS +21.8% → +11.3%，而西方 +26.1/40.0% → +28.0/28.5%）。
    """
    import statsmodels.formula.api as smf
    fml = "lncrp ~ edent_base" + (" + lnage" if adjust_age else "")
    out = {}
    for coh in ["HRS", "ELSA", "CHARLS"]:
        s = m[(m.cohort == coh)].dropna(subset=["crp", "edent_base", "age"])
        s = s[s.crp > 0].copy()
        if len(s) < 300:
            continue
        s["lncrp"] = np.log(s.crp)
        s["lnage"] = np.log(s["age"])
        r = smf.ols(fml, data=s).fit(cov_type="HC1")
        ci = r.conf_int().loc["edent_base"]
        out[coh] = dict(b=float(r.params["edent_base"]),
                        lo=float(ci[0]), hi=float(ci[1]),
                        pct=(np.exp(r.params["edent_base"]) - 1) * 100,
                        lo_pct=(np.exp(ci[0]) - 1) * 100,
                        hi_pct=(np.exp(ci[1]) - 1) * 100,
                        p=float(r.pvalues["edent_base"]), n=len(s))
    return out


def _mechanism_frame(pf: pd.DataFrame, bm: pd.DataFrame) -> pd.DataFrame:
    """带炎症标志物的分析框（Figure 3 专用）。

    `build_analysis_frame` 只保留 accel 与协变量，不含 crp/wbc。
    这里重建一次并保留炎症列，时序口径与主分析一致。
    """
    from step13_sensitivity import POST_EXPOSURE_WINDOW
    base_cols = ["edent_base", "age", "age_c", "female", "edu_years",
                 "married", "rural", "ever_smoke", "year"]
    exp = pf.dropna(subset=["edent_base"]).copy()
    exp = exp.sort_values(["cohort", "id", "year"])
    exp = exp.drop_duplicates(["cohort", "id"], keep="first")
    exp = exp[["cohort", "id"] + [c for c in base_cols if c in exp.columns]]
    exp = exp.rename(columns={"year": "year_base"})

    keep = ["cohort", "id", "wave", "year", PRIMARY_METRIC] + \
           [c for c in ["crp", "wbc", "il6", "fibrinogen"] if c in bm.columns]
    b = bm[[c for c in keep if c in bm.columns]].copy()
    m = b.merge(exp, on=["cohort", "id"], how="inner")
    m["blood_delta"] = m["year"] - m["year_base"]
    m = m[m["blood_delta"].between(1, POST_EXPOSURE_WINDOW)]
    m = m.sort_values(["cohort", "id", "blood_delta"]).drop_duplicates(["cohort", "id"], keep="first")
    return m.reset_index(drop=True)


def figure3_mechanism(m: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4))
    cohs = ["HRS", "ELSA", "CHARLS"]

    # ---- A. CRP 分布（箱线，原始 mg/L）----
    ax = axes[0]
    data, labs, colors = [], [], []
    for coh in cohs:
        s = m[m.cohort == coh]["crp"].dropna()
        s = s[(s > 0) & (s < 50)]
        if len(s) < 100:
            continue
        data.append(s.values); labs.append(coh); colors.append(COH_COLOR[coh])
    bp = ax.boxplot(data, patch_artist=True, widths=0.55,
                    showfliers=False, medianprops=dict(color="white", lw=1.8))
    ax.set_xticks(range(1, len(labs) + 1))
    ax.set_xticklabels(labs, fontsize=9.5)
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c); patch.set_alpha(0.85); patch.set_edgecolor(c)
    for i, d in enumerate(data, start=1):
        ax.text(i, np.median(d), "%.2f" % np.median(d), ha="center", va="bottom",
                fontsize=8.6, color="white", fontweight="bold")
    ax.set_ylabel("CRP (mg/L)", fontsize=10)
    ax.set_title("A. Inflammatory background", fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)

    # ---- B. 缺牙 → CRP 效应（% 变化，调整年龄）----
    ax = axes[1]
    ce = _crp_effect(m, adjust_age=True)
    xs = np.arange(len(ce))
    bs = [ce[c]["pct"] for c in ce]
    los = [ce[c]["lo_pct"] for c in ce]
    his = [ce[c]["hi_pct"] for c in ce]
    err = [np.array(bs) - np.array(los), np.array(his) - np.array(bs)]
    ax.bar(xs, bs, color=[COH_COLOR[c] for c in ce], width=0.55, alpha=0.9)
    ax.errorbar(xs, bs, yerr=err, fmt="none", ecolor="#333333", capsize=4, lw=1.4)
    for x, b in zip(xs, bs):
        ax.text(x, b + 1.2, "+%.1f%%" % b, ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(xs); ax.set_xticklabels(list(ce.keys()), fontsize=9.5)
    ax.set_ylabel("Change in CRP associated with edentulism (%)\nage-adjusted", fontsize=9.5)
    ax.set_title("B. Edentulism–inflammation coupling", fontsize=10.5)
    ax.axhline(0, color="#999999", lw=1)
    ax.spines[["top", "right"]].set_visible(False)

    # ---- C. accel 效应量（来自敏感性主口径）----
    ax = axes[2]
    covs = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
    bs, los, his, labs = [], [], [], []
    for coh in cohs:
        r = fit_one(m[m.cohort == coh], PRIMARY_METRIC, covs)
        if r is None:
            continue
        bs.append(r["beta"]); los.append(r["lo"]); his.append(r["hi"]); labs.append(coh)
    xs = np.arange(len(labs))
    err = [np.array(bs) - np.array(los), np.array(his) - np.array(bs)]
    ax.bar(xs, bs, color=[COH_COLOR[c] for c in labs], width=0.55, alpha=0.9)
    ax.errorbar(xs, bs, yerr=err, fmt="none", ecolor="#333333", capsize=4, lw=1.4)
    for x, b in zip(xs, bs):
        ax.text(x, b + (0.12 if b >= 0 else -0.28), "%+.2f" % b, ha="center",
                fontsize=9, fontweight="bold")
    ax.axhline(0, color="#999999", ls="--", lw=1)
    ax.set_xticks(xs); ax.set_xticklabels(labs, fontsize=9.5)
    ax.set_ylabel("β for edentulism (years)", fontsize=10)
    ax.set_title("C. Biological ageing effect", fontsize=10.5)
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("China versus Western cohorts: effect size tracks inflammatory coupling",
                 fontsize=12.5, y=1.005)
    fig.tight_layout()
    p = OUT_FIG / "figure3_china_west_mechanism.png"
    fig.savefig(p, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(p)


# ======================================================================
def main() -> None:
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    print("=" * 66)
    print("step14 中西方差异图组")
    print("=" * 66)
    pf, bm = load_frames()
    m = build_analysis_frame(pf, bm)
    print("分析框 n=%d" % len(m))

    print("[1/2] Figure 2 协变量阶梯 ……")
    print("  →", figure2_covariate_ladder(m))
    print("[2/2] Figure 3 机制三联图 ……")
    mm = _mechanism_frame(pf, bm)
    print("     机制框 n=%d" % len(mm))
    print("  →", figure3_mechanism(mm))
    print("\n完成。")


if __name__ == "__main__":
    main()
