# -*- coding: utf-8 -*-
"""
step11_biologicage.py   生物学衰老层：生物年龄计算与年龄加速
============================================================
输入： harmonized_biomarkers.csv（cohort,id,wave,year + 标准化标志物列）
输出： output/tables/bioage_by_cohort.csv   逐人生物年龄与年龄加速
       output/tables/bioage_qc.csv          各队列各指标的质控（与实龄 r / R² / n）
       output/tables/biomarker_variable_dictionary.csv   变量字典（含核实状态）
       output/figures/bioage_vs_age.png     生物年龄 vs 实龄散点（质控图）

实现三条路线
------------
1. **KDM（Klemera-Doubal 2006）** —— 主推。
   对每个标志物 j 在样本内回归实龄，取 (q_j 截距, k_j 斜率, s_j RMSE)，再算
        BA_E = Σ (x_j - q_j)(k_j/s_j²) / Σ (k_j²/s_j²)
        BA   = [Σ (x_j - q_j)(k_j/s_j²) + CA/s_BA²] / [Σ (k_j²/s_j²) + 1/s_BA²]
   优点：**不需要任何外部系数**，可自适应任意标志物组合（这正是我们能用的原因）。
   参考：Klemera & Doubal 2006; Levine 2018; Belsky 2015; BMC Public Health 2026（含 CA 修正项）
2. **Levine PhenoAge (2018)** —— 需要 9 组分齐全；系数逐字核对自原文与 PLoS Med 勘误。
3. **去污染版（clean）** —— 从标志物集合里**剔除炎症组分**（CRP/IL-6/WBC/淋巴%/纤维蛋白原），
   用于与炎症中介**并列**的中介分析，避免「同一变量用两次」（见变量字典 §4.1）。

⚠️ 关于 Crimmins(2021) 22 标记扩展生物年龄：其**官方系数未公开**，本工程不臆造。
   若日后取得，填入本文件 `CRIMMINS_COEF` 即自动启用（当前为空 → 自动跳过并提示）。
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import OUT_TAB, OUT_FIG                                   # noqa: E402
from config_biomarker import (                                        # noqa: E402
    BIOMARKER_FILE, PHENOAGE_COMPONENTS, PHENOAGE_COEF,
    INFLAMMATION_MARKERS, NONINFLAMMATION_MARKERS, MARKER_LABEL,
    BIOMARKERS, RANDOM_SEED, available_markers, demo_biomarkers,
)

warnings.filterwarnings("ignore")

# Crimmins(2021) 22 标记系数表（**空** = 未取得官方系数，自动跳过）
CRIMMINS_COEF: dict[str, float] = {}

MIN_MARKERS_KDM = 4          # 少于此数的标志物不构成 KDM
MIN_N_FOR_FIT = 200          # 拟合 q/k/s 的最少样本量

# ============================================================ KDM 输入前处理
# 为什么需要（2026-10-10 在**真实 HRS 2016 VBS** 上实测得出）：
#   KDM 假设「标志物 = q + k·BA + ε」，而 CRP / IL-6 / TNF-R1 / BNP / 铁蛋白 等
#   是强右偏分布，少数极值把 s_j 撑大、并让 k_j 估计失真 → 权重被稀释。
#   实测（HRS VBS，n≈9,873）：
#       原始           r(KDM, 实龄) = 0.409
#       仅 1/99 缩尾    r = 0.469
#       缩尾 + 右偏取对数 r = 0.542   ← 逼近监督上限（18 项全用 OLS 回归实龄的 R = 0.653）
#   ⚠️ 本变换**只作用于 KDM**；PhenoAge 一律用原始列（其公式本身已含 ln(CRP)）。
KDM_WINSOR = (1.0, 99.0)     # 百分位缩尾；None 关闭
KDM_LOG_SKEW = 1.0           # 偏度超过此值且取值全正 → 取自然对数


def preprocess_for_kdm(df: pd.DataFrame, markers: list[str],
                       winsor: tuple | None = KDM_WINSOR
                       ) -> tuple[pd.DataFrame, dict]:
    """KDM 专用的标志物前处理：缩尾 + 右偏取对数。返回 (处理后的表, 处理说明)。"""
    out = df.copy()
    info: dict[str, str] = {}
    for m in markers:
        if m not in out.columns:
            continue
        x = pd.to_numeric(out[m], errors="coerce").astype(float)
        if winsor is not None and x.notna().sum() > MIN_N_FOR_FIT:
            lo, hi = np.nanpercentile(x.dropna(), winsor)
            x = x.clip(lo, hi)
        if x.notna().sum() > MIN_N_FOR_FIT:
            pos = x.dropna()
            if (pos > 0).all():
                sk = float(pos.skew())
                if sk > KDM_LOG_SKEW:
                    x = np.log(x.clip(lower=1e-4))
                    info[m] = f"ln（偏度 {sk:.2f}）"
        out[m] = x
    return out, info

# 是否把**核心体测**（SBP / 峰流速 / 握力）并入 KDM 标志物池。
# 默认 False → 生物年龄保持**血液口径**（与 Crimmins 22 项可比）；
# 设 BIOAGE_INCLUDE_PHYSICAL=1 → 生成"生理-血样混合 BA"（须在 Methods 声明为功能维度扩展）。
INCLUDE_PHYSICAL = os.environ.get("BIOAGE_INCLUDE_PHYSICAL", "0") == "1"


# ============================================================ 单位换算
def normalise_units(df: pd.DataFrame) -> pd.DataFrame:
    """把各队列原始单位换算到内部统一口径。

    目前只处理已知会"串单位"的三项（其余队列文档单位已与内部口径一致）：
      · 白蛋白：若中位数 < 10 则判为 g/dL → ×10 转 g/L
        （HRS VBS `PALB` 官方单位 **g/dL**，实测均值 ≈ 3.93；内部口径为 g/L）
      · 肌酐：若中位数 < 20 则判为 mg/dL → ×88.42 转 μmol/L
        （HRS VBS `PCR` 官方单位 **mg/dL**，实测均值 ≈ 0.96）
      · 血糖：若中位数 < 30 且 > 1.5 视为 mmol/L（不动）；若 > 30 判为 mg/dL → ×0.05551
        （HRS VBS `PGLUFF` 官方单位 **mg/dL**，实测均值 ≈ 111.9）

    ⚠️ **KDM 对每个标志物的线性缩放不变**（BA_E 用 k_j²/s_j² 加权，量纲自动约掉），
    所以单位问题**只影响 PhenoAge**（白蛋白系数 −0.0336，若差 10 倍则 xb 偏差 ≈ 1.19，致命）。
    CRp 内部统一为 mg/L（PhenoAge 内部再转 mg/dL）。
    """
    d = df.copy()
    # 白蛋白：g/dL → g/L（HRS VBS 为 g/dL；CHARLS/NHANES 原始即 g/L，不受影响）
    if "albumin" in d.columns:
        med = d["albumin"].median(skipna=True)
        if pd.notna(med) and med < 10:                     # 显然不是 g/L
            d["albumin"] = d["albumin"] * 10.0
    if "creatinine" in d.columns:
        med = d["creatinine"].median(skipna=True)
        if pd.notna(med) and med < 20:                     # 显然不是 μmol/L
            d["creatinine"] = d["creatinine"] * 88.42
    if "glucose" in d.columns:
        med = d["glucose"].median(skipna=True)
        if pd.notna(med) and med > 30:                     # mg/dL
            d["glucose"] = d["glucose"] * 0.05551
    return d


# ============================================================ KDM
def kdm_bioage(df: pd.DataFrame, markers: list[str], age_col: str = "age",
               min_markers: int = MIN_MARKERS_KDM,
               use_ca_correction: bool = True) -> tuple[pd.Series, dict]:
    """Klemera-Doubal 生物年龄。返回 (BA 序列, 拟合参数 dict)。"""
    n = len(df)
    if n == 0 or not markers:
        return pd.Series(np.nan, index=df.index), {"markers": [], "note": "无可用标志物"}
    age = pd.to_numeric(df[age_col], errors="coerce").values.astype(float)
    used, q, k, s = [], {}, {}, {}
    for m in markers:
        x = pd.to_numeric(df[m], errors="coerce").values.astype(float)
        ok = np.isfinite(x) & np.isfinite(age)
        if ok.sum() < MIN_N_FOR_FIT:
            continue
        slope, intercept = np.polyfit(age[ok], x[ok], 1)
        resid = x[ok] - (slope * age[ok] + intercept)
        s_j = float(np.sqrt(np.sum(resid ** 2) / max(1, ok.sum() - 2)))
        if not np.isfinite(slope) or slope == 0 or s_j <= 1e-12:
            continue
        used.append(m); q[m] = float(intercept); k[m] = float(slope); s[m] = s_j

    if len(used) < min_markers:
        return pd.Series(np.nan, index=df.index), {
            "markers": used, "note": f"可用标志物 {len(used)} < {min_markers}，KDM 不可算"}

    num = np.zeros(n); den = np.zeros(n); cnt = np.zeros(n, dtype=int)
    for m in used:
        x = pd.to_numeric(df[m], errors="coerce").values.astype(float)
        ok = np.isfinite(x)
        w = k[m] / (s[m] ** 2)
        num[ok] += (x[ok] - q[m]) * w
        den[ok] += (k[m] ** 2) / (s[m] ** 2)
        cnt[ok] += 1

    with np.errstate(divide="ignore", invalid="ignore"):
        ba_e = np.where(den > 0, num / den, np.nan)

    if use_ca_correction:
        s_ba2 = float(np.nanvar(ba_e))
        if not np.isfinite(s_ba2) or s_ba2 <= 0:
            ba = ba_e
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                ba = (num + age / s_ba2) / (den + 1 / s_ba2)
    else:
        ba = ba_e

    ba = np.where(cnt >= min_markers, ba, np.nan)
    fit = {"markers": used, "q": q, "k": k, "s": s,
           "n_markers": len(used), "use_ca_correction": use_ca_correction}
    return pd.Series(ba, index=df.index), fit


# ============================================================ PhenoAge
def phenoage(df: pd.DataFrame, age_col: str = "age") -> pd.Series:
    """Levine PhenoAge (2018)。缺任一组分即返回 NaN 序列。"""
    c = PHENOAGE_COEF
    miss = [m for m in PHENOAGE_COMPONENTS if m not in df.columns]
    if miss:
        return pd.Series(np.nan, index=df.index)
    g = lambda m: pd.to_numeric(df[m], errors="coerce").values.astype(float)
    alb, cre, glu = g("albumin"), g("creatinine"), g("glucose")
    crp, lym, mcv = g("crp"), g("lymph_pct"), g("mcv")
    rdw, alp, wbc = g("rdw"), g("alp"), g("wbc")
    age = pd.to_numeric(df[age_col], errors="coerce").values.astype(float)

    with np.errstate(divide="ignore", invalid="ignore"):
        ln_crp = np.log(np.where(crp > 0, crp * 0.1, np.nan))      # mg/L → mg/dL 再取 ln
    xb = (c["intercept"]
          + c["albumin_gL"] * alb
          + c["creatinine_umolL"] * cre
          + c["glucose_mmolL"] * glu
          + c["ln_crp_mgdl"] * ln_crp
          + c["lymph_pct"] * lym
          + c["mcv_fL"] * mcv
          + c["rdw_pct"] * rdw
          + c["alp_UL"] * alp
          + c["wbc_1e3uL"] * wbc
          + c["age_years"] * age)

    gamma = c["gamma"]
    k = (np.exp(gamma * c["horizon_months"]) - 1.0) / gamma        # ≈197.22
    with np.errstate(over="ignore", invalid="ignore"):
        M = 1.0 - np.exp(-k * np.exp(xb))
    M = np.clip(M, 1e-12, 1 - 1e-12)
    pa = c["age_intercept"] + np.log(c["age_inner"] * np.log(1.0 - M)) / c["age_slope"]
    return pd.Series(pa, index=df.index)


# ============================================================ 年龄加速
def age_acceleration(bioage: pd.Series, age: pd.Series) -> tuple[pd.Series, dict]:
    """年龄加速 = 生物年龄对实龄回归的残差（与实龄正交，是文献标准的 Accel 定义）。"""
    b = pd.to_numeric(bioage, errors="coerce").values.astype(float)
    a = pd.to_numeric(age, errors="coerce").values.astype(float)
    ok = np.isfinite(b) & np.isfinite(a)
    accel = np.full(len(b), np.nan)
    info = {"r": np.nan, "r2": np.nan, "n": int(ok.sum()), "rmse": np.nan}
    if ok.sum() < MIN_N_FOR_FIT:
        return pd.Series(accel, index=bioage.index), info
    slope, intercept = np.polyfit(a[ok], b[ok], 1)
    pred = slope * a[ok] + intercept
    accel[ok] = b[ok] - pred
    r = float(np.corrcoef(a[ok], b[ok])[0, 1])
    info.update(r=r, r2=r ** 2, rmse=float(np.sqrt(np.mean((b[ok] - pred) ** 2))),
                slope=float(slope), intercept=float(intercept))
    info["age_diff_mean"] = float(np.nanmean((b - a)[ok]))       # BA − CA 均值
    return pd.Series(accel, index=bioage.index), info


# ============================================================ 主计算
def compute_bioage_table(bm: pd.DataFrame, allow_flagged: bool = False
                         ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """对血样长表逐队列计算全部生物年龄指标。

    allow_flagged : 是否纳入 status="flagged" 的标志物。
        **真实数据必须 False**（未核实变量名不得进入正式分析）；
        演示模式（合成数据）传 True，否则 HRS 因变量名待核而全部被剔除。

    返回 (逐人表, 质控表)。逐人表列：
      cohort,id,wave,year,age,kdm,kdm_clean,kdm_accel,kdm_clean_accel,
      phenoage,phenoage_accel,n_markers,n_markers_clean
    """
    bm = normalise_units(bm)
    if "age" not in bm.columns:
        raise ValueError("生物标志物表缺少 age 列（实龄）—— KDM/PhenoAge 都需要它")

    people, qc = [], []
    # ⚠️ 按 (cohort, wave) 分组：同一队列若有多波血样（如 CHARLS 2011/2015），
    #    不同波次的测定批次不同（实验室/年代），合并拟合会把**批次漂移**误当衰老差异
    #    → 必须逐波各自拟合 KDM（KDM 本就是队内拟合，波内拟合不违背其定义）。
    grp = bm.groupby(["cohort", "wave"], dropna=False) if "wave" in bm.columns \
        else bm.groupby(["cohort"], dropna=False)
    for key, sub in grp:
        coh = key[0] if isinstance(key, tuple) else key
        wav = key[1] if isinstance(key, tuple) and len(key) > 1 else np.nan
        tag = f"{coh}·w{wav}" if pd.notna(wav) else coh
        sub = sub.copy()
        avail = [m for m in available_markers(coh, include_flagged=allow_flagged,
                                              include_optional=INCLUDE_PHYSICAL)
                 if m in sub.columns]
        clean_markers = [m for m in avail if m not in INFLAMMATION_MARKERS]

        # KDM 专用前处理（缩尾 + 右偏取对数）；PhenoAge 仍用原始列
        sub_kdm, prep_info = preprocess_for_kdm(sub, avail)
        if prep_info:
            print(f"  [{tag:10s}] KDM 前处理：" +
                  "；".join(f"{k} {v}" for k, v in prep_info.items()), flush=True)

        sub["kdm"], fit_all = kdm_bioage(sub_kdm, avail)
        sub["kdm_clean"], fit_clean = kdm_bioage(sub_kdm, clean_markers)
        sub["phenoage"] = phenoage(sub)

        sub["kdm_accel"], q_kdm = age_acceleration(sub["kdm"], sub["age"])
        sub["kdm_clean_accel"], q_clean = age_acceleration(sub["kdm_clean"], sub["age"])
        sub["phenoage_accel"], q_pa = age_acceleration(sub["phenoage"], sub["age"])

        sub["n_markers"] = len(fit_all["markers"])
        sub["n_markers_clean"] = len(fit_clean["markers"])

        keep = ["cohort", "id", "wave", "year", "age",
                "kdm", "kdm_clean", "kdm_accel", "kdm_clean_accel",
                "phenoage", "phenoage_accel", "n_markers", "n_markers_clean"]
        people.append(sub[[c for c in keep if c in sub.columns]])

        for name, info, nm in (("KDM(全)", q_kdm, len(fit_all["markers"])),
                               ("KDM(去污染)", q_clean, len(fit_clean["markers"])),
                               ("PhenoAge", q_pa, len(PHENOAGE_COMPONENTS))):
            qc.append({"cohort": coh, "wave": wav, "metric": name, "n": info.get("n", 0),
                       "n_markers": nm, "r_with_age": info.get("r", np.nan),
                       "R2": info.get("r2", np.nan), "RMSE": info.get("rmse", np.nan),
                       "BA_minus_CA": info.get("age_diff_mean", np.nan),
                       "note": fit_all.get("note", "") if name.startswith("KDM(全)")
                               else fit_clean.get("note", "") if name.startswith("KDM(去")
                               else ("缺组分" if np.isnan(info.get("r", np.nan)) else "")})
        print(f"  [{tag:10s}] n={len(sub):>6,}  KDM标志物={len(fit_all['markers']):>2}  "
              f"去污染={len(fit_clean['markers']):>2}  "
              f"r(KDM,age)={q_kdm.get('r', float('nan')):.3f}  "
              f"r(clean,age)={q_clean.get('r', float('nan')):.3f}  "
              f"r(PhenoAge,age)={q_pa.get('r', float('nan')):.3f}", flush=True)

    return pd.concat(people, ignore_index=True), pd.DataFrame(qc)


# ============================================================ 变量字典
def variable_dictionary() -> pd.DataFrame:
    rows = []
    for coh, d in BIOMARKERS.items():
        for k, v in d.items():
            if k.startswith("_"):
                continue
            rows.append({"cohort": coh, "marker": k, "label": MARKER_LABEL.get(k, k),
                         "variable": v.get("var"), "unit": v.get("unit"),
                         "status": v.get("status"), "note": v.get("note", "")})
        rows.append({"cohort": coh, "marker": "(队列血样)", "label": d.get("_wave", ""),
                     "variable": "", "unit": "", "status": "info",
                     "note": d.get("_source", "")})
    return pd.DataFrame(rows)


def _qc_figure(people: pd.DataFrame):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    d = people.dropna(subset=["age", "kdm_clean"])
    if len(d) < 50:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6))
    for ax, (col, lab) in zip(axes, [("kdm_clean", "KDM（去污染）"),
                                     ("phenoage", "PhenoAge")]):
        s = d.dropna(subset=[col])
        if len(s) < 50:
            ax.set_visible(False); continue
        ax.scatter(s["age"], s[col], s=5, alpha=.25, color="#3b6ea5", edgecolors="none")
        lo, hi = s["age"].min(), s["age"].max()
        ax.plot([lo, hi], [lo, hi], "--", color="#b3402f", lw=1.3, label="y = x")
        r = np.corrcoef(s["age"], s[col])[0, 1]
        ax.set_title(f"{lab}（r = {r:.3f}, n = {len(s):,}）", fontsize=11)
        ax.set_xlabel("实龄 Chronological age (years)")
        ax.set_ylabel("生物年龄 Biological age (years)")
        ax.legend(frameon=False)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.tight_layout()
    p = OUT_FIG / "bioage_vs_age.png"
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


# ============================================================ main
def main(demo: bool | None = None, seed: int = RANDOM_SEED):
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    if demo is None:
        demo = not BIOMARKER_FILE.exists()
    if demo:
        print("⚠️ 演示模式：BIOMARKER_FILE 不存在，改用**合成**血样数据（数字不得写入论文）")
        bm = demo_biomarkers(seed=seed)
    else:
        bm = pd.read_csv(BIOMARKER_FILE)
        print(f"读取 {BIOMARKER_FILE}（n={len(bm):,}）")

    people, qc = compute_bioage_table(bm, allow_flagged=demo)
    people.to_csv(OUT_TAB / "bioage_by_cohort.csv", index=False, encoding="utf-8-sig")
    qc.to_csv(OUT_TAB / "bioage_qc.csv", index=False, encoding="utf-8-sig")
    variable_dictionary().to_csv(OUT_TAB / "biomarker_variable_dictionary.csv",
                                 index=False, encoding="utf-8-sig")
    fig = _qc_figure(people)

    print("\n—— 生物年龄质控（与实龄的相关）——")
    print(qc.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\n已输出：\n  {OUT_TAB/'bioage_by_cohort.csv'}\n  {OUT_TAB/'bioage_qc.csv'}"
          f"\n  {OUT_TAB/'biomarker_variable_dictionary.csv'}"
          + (f"\n  {fig}" if fig else ""))
    if CRIMMINS_COEF:
        print("提示：已检测到 CRIMMINS_COEF，可扩展 22 标记口径。")
    else:
        print("提示：CRIMMINS_COEF 为空（官方系数未公开）→ 未启用 22 标记扩展口径，"
              "已用 KDM 替代。")
    return people, qc


if __name__ == "__main__":
    main()
