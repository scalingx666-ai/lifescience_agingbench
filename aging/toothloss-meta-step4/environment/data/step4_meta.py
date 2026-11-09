# -*- coding: utf-8 -*-
"""
Step 4  随机效应 Meta 汇总 + 森林图 + E-value
=============================================
· DerSimonian-Laird 随机效应模型汇总各队列的 edent:time_c 系数
· 报告 pooled β、95%CI、I²、tau²、Q
· 森林图（含 I²、异质性）与 E-value（未测混杂稳健性）
输出：output/tables/meta_pooled.csv, output/figures/forest_edent_cognition.png
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from config import OUT_TAB, OUT_FIG

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

def dl_meta(est, se, labels):
    est, se = np.asarray(est, float), np.asarray(se, float)
    ok = np.isfinite(est) & np.isfinite(se) & (se > 0)
    est, se, labels = est[ok], se[ok], [l for l, o in zip(labels, ok) if o]
    w = 1 / se**2
    fe = np.sum(w * est) / np.sum(w)
    Q = np.sum(w * (est - fe)**2)
    k = len(est)
    C = np.sum(w) - np.sum(w**2) / np.sum(w)
    tau2 = max(0.0, (Q - (k - 1)) / C) if C > 0 else 0.0
    I2 = max(0.0, (Q - (k - 1)) / Q) * 100 if Q > 0 else 0.0
    wr = 1 / (se**2 + tau2)
    pooled = np.sum(wr * est) / np.sum(wr)
    se_pool = np.sqrt(1 / np.sum(wr))
    z = pooled / se_pool
    from scipy import stats
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return dict(est=est, se=se, labels=labels, fe=fe, pooled=pooled, se_pool=se_pool,
                z=z, p=p, Q=Q, tau2=tau2, I2=I2, k=k,
                ci_lo=pooled - 1.96 * se_pool, ci_hi=pooled + 1.96 * se_pool)

def e_value(est, ci_hi_edge, outcome="continuous"):
    """E-value：把风险比近似为 RR，估计需要多强的未测混杂才能解释掉该关联"""
    rr = np.exp(abs(est)) if outcome != "continuous" else np.exp(abs(est))
    def _e(r):
        return r + np.sqrt(r * (r - 1))
    return _e(rr), _e(np.exp(abs(ci_hi_edge)))

def forest_plot(m, pooled_label="Pooled (random-effects)"):
    fig, ax = plt.subplots(figsize=(8.6, 0.62 * (m["k"] + 2) + 1.2))
    y = np.arange(m["k"])[::-1]
    for yi, e, s, lab in zip(y, m["est"], m["se"], m["labels"]):
        lo, hi = e - 1.96 * s, e + 1.96 * s
        ax.plot([lo, hi], [yi, yi], color="#3b6ea5", lw=1.8)
        ax.plot([e], [yi], "s", color="#1f3b57", ms=8)
        ax.text(1.02, yi, f"{e:+.4f} ({lo:+.4f}, {hi:+.4f})",
                transform=ax.get_yaxis_transform(), va="center", fontsize=9)
    ax.axvline(0, color="#888", ls="--", lw=1)
    # 汇总菱形
    yd = -1.1
    ax.plot([m["ci_lo"], m["ci_hi"]], [yd, yd], color="#b3402f", lw=2.4)
    ax.plot([m["pooled"]], [yd], "D", color="#b3402f", ms=9)
    ax.text(1.02, yd, f"{m['pooled']:+.4f} ({m['ci_lo']:+.4f}, {m['ci_hi']:+.4f}), I²={m['I2']:.1f}%",
            transform=ax.get_yaxis_transform(), va="center", fontsize=9, color="#b3402f")
    ax.set_yticks(list(y) + [yd])
    ax.set_yticklabels(m["labels"] + [pooled_label])
    ax.set_xlabel("Additional annual change in standardized episodic memory (SD/year), "
                  "edentulous vs dentate")
    # 异质性统计量放进标题（而不是手工摆一个 ax.text）——从结构上排除与 x 轴标签重叠的可能
    ax.set_title(f"Edentulism and the rate of episodic-memory decline:\n"
                 f"random-effects meta-analysis of four cohorts\n"
                 f"(heterogeneity: Q = {m['Q']:.2f}, τ² = {m['tau2']:.5f}, "
                 f"I² = {m['I2']:.1f}%)", fontsize=11.5, pad=12)
    ax.set_xlim(min(m["est"] - 1.96 * m["se"]) - .02, max(m["est"] + 1.96 * m["se"]) + .02)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    p = OUT_FIG / "forest_edent_cognition.png"
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p

def main():
    coh = pd.read_csv(OUT_TAB / "model_by_cohort.csv")
    m = dl_meta(coh["beta"].values, coh["se"].values, coh["cohort"].tolist())
    tab = pd.DataFrame([{
        "k 队列数": m["k"],
        "Pooled β": round(m["pooled"], 4),
        "SE": round(m["se_pool"], 4),
        "95%CI": f"{m['ci_lo']:.4f} ~ {m['ci_hi']:.4f}",
        "p": f"{m['p']:.3g}",
        "Q": round(m["Q"], 3), "tau²": round(m["tau2"], 5), "I²(%)": round(m["I2"], 1),
    }])
    tab.to_csv(OUT_TAB / "meta_pooled.csv", index=False, encoding="utf-8-sig")
    fig_p = forest_plot(m)

    ev, ev_ci = e_value(m["pooled"], m["ci_hi"])
    print(tab.to_string(index=False))
    print(f"\nE-value: 点估计 {ev:.2f} ；CI 边界 {ev_ci:.2f}")
    print(f"森林图: {fig_p}")
    return m, tab

if __name__ == "__main__":
    main()
