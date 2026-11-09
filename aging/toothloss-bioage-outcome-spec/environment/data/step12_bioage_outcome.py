# -*- coding: utf-8 -*-
"""
step12_bioage_outcome.py   第二篇：把「生物学衰老加速」本身当结局
=================================================================
命题：**牙齿脱落 → 生物学衰老加速**（以及炎症是否为其通路）。

与 step10 的分工
----------------
· step10 把生物年龄加速当作**中介**（缺牙 → 炎症 → 衰老 → 认知）→ 第一篇；
· step12 把生物年龄加速当作**结局**（缺牙 → 衰老加速）→ 第二篇（可独立投稿）。

本脚本做五件事
--------------
1. **逐队列关联**：`accel ~ edent_base + 协变量`，β 直接读作「无牙颌者比有牙者
   平均多老 N 年」（accel 单位为年，天然可解释，且跨队列可比）。
   · 主口径 = **去污染版** `kdm_clean_accel`（剔除炎症组分）→ 与炎症中介不重叠；
   · 敏感性同时报 `kdm_accel`（含 CRP）与 `phenoage_accel`。
2. **剂量-反应**：连续「剩余牙数」（每多 1 颗的额外衰老年数）+ 四分类
   （无牙颌 / 1–9 / 10–19，**参照 = ≥20 颗功能牙列**，即 WHO 阈值，与 ELSA `HEDNTD` 同构）。
   仅 SHARE 有牙数变量 → 该分支只在 SHARE 跑。
3. **随机效应 Meta 汇总**（DerSimonian-Laird，与 step4 同一实现）+ 森林图 + E-value。
4. **炎症中介**：缺牙 → 炎症（CRP/纤维蛋白原…）→ 衰老加速（product-of-coefficients
   + bootstrap 百分位 CI）。因结局用去污染版，**不存在「同一变量用两次」**。
5. **时序强制**：血样必须**晚于或等于**暴露年（0 ≤ 血样年 − 基线年 ≤ POST_EXPOSURE_WINDOW），
   被剔除人数在日志与结果表里显式报告。

⚠️ 三条必须写进方法学的口径
---------------------------
· 年龄加速 = 生物年龄对实龄回归的**残差**（与实龄正交）→ 模型里再放 age_c 只为与
  主分析协变量集一致，其系数应 ≈ 0，可当质控读；不放基线认知（会构成对撞因子）。
· 暴露用 **edent_base**（基线时不变），不用时变的 `edent`（避免反向因果）。
· 中介测于暴露之后（同一个血样波），属「横断面中介」→ 解释为机制提示，不宣称因果
  （已在 md 汇总的局限性里写明）。

运行
----
    python step12_bioage_outcome.py                     # 有真实血样表则真实，否则演示
    BIOAGE_BOOT=300 python step12_bioage_outcome.py
输出：output/tables/bioage_outcome_by_cohort.csv
      output/tables/bioage_outcome_metrics.csv
      output/tables/bioage_outcome_dose.csv
      output/tables/bioage_outcome_meta.csv
      output/tables/bioage_outcome_mediation.csv
      output/tables/bioage_outcome_summary.md
      output/figures/forest_bioage_outcome.png
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import HARM_LONG, OUT_TAB, OUT_FIG                        # noqa: E402
from config_biomarker import (                                        # noqa: E402
    BIOMARKER_FILE, POST_EXPOSURE_WINDOW, RANDOM_SEED, synth_marker_frame,
)
from step10_mediation import (_ols, _z, boot_ci, person_frame,        # noqa: E402
                              _usable_covs, COVS)
from step11_biologicage import compute_bioage_table                    # noqa: E402
from step4_meta import dl_meta                                         # noqa: E402

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------- 口径与常数
BIOAGE_METRICS = [
    ("kdm_clean_accel", "KDM 去污染（主口径）"),
    ("kdm_accel",       "KDM 全标志物（含炎症组分）"),
    ("phenoage_accel",  "Levine PhenoAge"),
]
PRIMARY_METRIC = "kdm_clean_accel"
MEDIATORS = ["crp", "il6", "fibrinogen", "wbc"]        # 逐个尝试（队列可得者才跑）
MIN_N = 200                                            # 最少样本量
BIOAGE_BOOT = int(os.environ.get("BIOAGE_BOOT", os.environ.get("MEDIATION_BOOT", "1000")))

# 演示模式已知真值（仅合成数据；**不得写入论文**）
DEMO_TRUTH = {"a": 0.60, "b": 0.25, "c": 0.30,
              "total": 0.45, "nie": 0.15, "prop": 0.15 / 0.45}


# ================================================================ OLS + 稳健 SE
def fit_ols(y: np.ndarray, terms: list[np.ndarray], names: list[str],
            cov_type: str = "HC3") -> dict:
    """带稳健标准误的 OLS；terms 已中心化，自动补常数项。

    返回 {name: {beta, se, p, lo, hi}}。
    """
    import statsmodels.api as sm
    n = len(y)
    X = np.column_stack([np.ones(n)] + [np.asarray(t, float) for t in terms])
    res = sm.OLS(y, X).fit(cov_type=cov_type)
    out = {}
    for i, nm in enumerate(names, start=1):
        ci = res.conf_int()[i]
        out[nm] = {"beta": float(res.params[i]), "se": float(res.bse[i]),
                   "p": float(res.pvalues[i]), "lo": float(ci[0]), "hi": float(ci[1])}
    return out


def _design_ba(pf: pd.DataFrame, outcome: str, zip_x: list[str]):
    """构造 (y, terms, names, used) —— 剔除缺失、连续协变量中心化。"""
    need = [c for c in ["edent_base", outcome] + list(zip_x) if c in pf.columns]
    d = pf.dropna(subset=need).copy()
    covs = _usable_covs(d)                       # 只留该队列有变异的协变量
    d = d.dropna(subset=covs)
    if len(d) < MIN_N or d["edent_base"].nunique() < 2:
        return None
    y = pd.to_numeric(d[outcome], errors="coerce").values.astype(float)
    terms, names = [], []
    for x in zip_x:
        v = pd.to_numeric(d[x], errors="coerce").values.astype(float)
        terms.append(v - np.nanmean(v))
        names.append(x)
    for c in covs:
        v = pd.to_numeric(d[c], errors="coerce").values.astype(float)
        terms.append(v - np.nanmean(v))
        names.append(c)
    ok = np.isfinite(y) & np.all(np.isfinite(np.column_stack(terms)), axis=1)
    y = y[ok]
    terms = [t[ok] for t in terms]
    if len(y) < MIN_N:
        return None
    return y, terms, names, d.loc[ok]


# ================================================================ 主模型：暴露→加速
def fit_exposure(pf: pd.DataFrame, outcome: str, exposure: str = "edent_base",
                 subset: pd.Series | None = None) -> dict | None:
    """单队列 OLS：outcome ~ exposure + 协变量。返回 β 的原始(年)与标准化两套。"""
    d = pf if subset is None else pf[subset]
    out = _design_ba(d, outcome, [exposure])
    if out is None:
        return None
    y, terms, names, used = out
    r = fit_ols(y, terms, names)
    # ⚠️ terms[0] 已被中心化（均值≈0），不能用来数事件数 → 必须用原始暴露列
    A_raw = pd.to_numeric(used[exposure], errors="coerce").values.astype(float)
    sd_y = float(np.std(y, ddof=1))
    beta_std = r[exposure]["beta"] / sd_y if sd_y > 0 else np.nan
    # 标准化 β 的 SE：y/sd 等比例缩放，系数 SE 同比例
    se_std = r[exposure]["se"] / sd_y if sd_y > 0 else np.nan
    return {"outcome": outcome, "exposure": exposure,
            "beta": r[exposure]["beta"], "se": r[exposure]["se"],
            "p": r[exposure]["p"], "lo": r[exposure]["lo"], "hi": r[exposure]["hi"],
            "beta_std": beta_std, "se_std": se_std,
            "sd_outcome": sd_y, "n_people": len(y),
            "n_events": int(np.nansum(A_raw)),
            "age_c_beta": r.get("age_c", {}).get("beta", np.nan),
            "cohort": str(used["cohort"].iloc[0]) if "cohort" in used.columns else "?"}


def fit_dose(pf: pd.DataFrame, outcome: str) -> list[dict]:
    """剂量-反应：连续剩余牙数 + 四分类（仅牙数可得队列）。

    分类口径取 **WHO 功能牙列阈值（≥20 颗）为参照**：
        无牙颌(0) / 1–9 / 10–19  vs  ≥20 颗
    （与 ELSA 官方 `HEDNTD` 的 None/1–9/10–19/≥20 完全同构。）

    ⚠️ 为什么不做「28 颗完整」单独一类：实测 SHARE 该组仅 2 人 →
       参照组近乎为空会让其余系数 SE 爆到 ±3 年（纯假象）。凡某报告类别
       不足 `MIN_LEVEL_N` 人即跳过并在日志说明。
    """
    MIN_LEVEL_N = 50
    rows = []
    if "teeth_base" not in pf.columns or pf["teeth_base"].notna().sum() < MIN_N:
        return rows
    cohort = str(pf["cohort"].iloc[0])
    # (a) 连续：每多 1 颗牙的额外衰老年数
    out = _design_ba(pf, outcome, ["teeth_base"])
    if out is not None:
        y, terms, names, used = out
        r = fit_ols(y, terms, names)
        rows.append({"cohort": cohort, "outcome": outcome,
                     "spec": "连续（每多 1 颗牙）", "term": "teeth_base",
                     "beta": r["teeth_base"]["beta"], "se": r["teeth_base"]["se"],
                     "p": r["teeth_base"]["p"], "lo": r["teeth_base"]["lo"],
                     "hi": r["teeth_base"]["hi"], "n_people": len(y)})
    # (b) 四分类（参照 = ≥20 颗功能牙列）
    LEVELS = ["无牙颌(0)", "1–9", "10–19"]
    cat = pf.dropna(subset=["teeth_base"]).copy()
    cat["_cat"] = np.select([cat["teeth_base"] <= 0, cat["teeth_base"] <= 9,
                             cat["teeth_base"] <= 19],
                            LEVELS, default="≥20 颗（参照）")
    covs = _usable_covs(cat)
    cat = cat.dropna(subset=covs + [outcome])
    if len(cat) < MIN_N:
        return rows
    cnt = cat["_cat"].value_counts()
    if cnt.get("≥20 颗（参照）", 0) < MIN_LEVEL_N:
        print(f"  ✗ {cohort} 剂量-反应：参照组（≥20 颗）仅 "
              f"{cnt.get('≥20 颗（参照）', 0)} 人 → 跳过分类分支")
        return rows
    y = pd.to_numeric(cat[outcome], errors="coerce").values.astype(float)
    terms, names = [], []
    for lev in LEVELS:
        if cnt.get(lev, 0) < MIN_LEVEL_N:
            print(f"  ✗ {cohort} 剂量-反应：类别「{lev}」仅 {cnt.get(lev, 0)} 人 → 该类别不报")
            continue
        v = (cat["_cat"] == lev).astype(float).values
        terms.append(v - v.mean()); names.append(lev)
    for c in covs:
        v = pd.to_numeric(cat[c], errors="coerce").values.astype(float)
        terms.append(v - np.nanmean(v)); names.append(c)
    ok = np.isfinite(y) & np.all(np.isfinite(np.column_stack(terms)), axis=1)
    if ok.sum() >= MIN_N:
        r = fit_ols(y[ok], [t[ok] for t in terms], names)
        for lev in LEVELS:
            if lev not in r:
                continue
            rows.append({"cohort": cohort, "outcome": outcome,
                         "spec": f"分类 vs ≥20 颗（{lev}）", "term": lev,
                         "beta": r[lev]["beta"], "se": r[lev]["se"], "p": r[lev]["p"],
                         "lo": r[lev]["lo"], "hi": r[lev]["hi"], "n_people": int(ok.sum())})
    return rows


# ================================================================ 中介（连续结局）
def mediate_cont(y: np.ndarray, A: np.ndarray, M: np.ndarray, C: np.ndarray) -> dict:
    """缺牙 → 炎症 M → 衰老加速 Y（product-of-coefficients）。

    M 模型: E[M|A,C] = a0 + a·A + a'C
    Y 模型: E[Y|A,M,C] = c0 + c'·A + b·M + c'C
    NIE = a·b ；NDE = c' ；TE = c' + a·b
    """
    n = len(y)
    C = np.atleast_2d(C).T if C.ndim == 1 else C
    a = float(_ols(M, np.column_stack([np.ones(n), A, C]))[1])
    by = _ols(y, np.column_stack([np.ones(n), A, M, C]))
    c_prime, b = float(by[1]), float(by[2])
    NIE = a * b
    TE = c_prime + NIE
    return {"a": a, "b": b, "NDE": c_prime, "NIE": NIE, "TE": TE,
            "prop": (NIE / TE) if abs(TE) > 1e-9 else np.nan, "n": n}


def run_mediation(pf: pd.DataFrame, mediator: str, outcome: str, seed: int,
                  B: int) -> dict | None:
    out = _design_ba(pf.dropna(subset=[mediator]) if mediator in pf.columns else pf.iloc[0:0],
                     outcome, [mediator])
    if out is None:
        return None
    y, terms, names, used = out
    M = _z(terms[0])                                     # 中介标准化（NIE 对标准与否不变）
    A = used["edent_base"].astype(float).values
    C = np.column_stack(terms[1:]) if len(terms) > 1 else np.zeros((len(y), 1))
    est = mediate_cont(y, A, M, C)
    ci = boot_ci(lambda idx: mediate_cont(y[idx], A[idx], M[idx], C[idx]), len(y), B, seed)
    est.update(ci)
    est.update(cohort=str(used["cohort"].iloc[0]), mediator=mediator, outcome=outcome,
               label=f"{used['cohort'].iloc[0]} · 缺牙→{mediator}→衰老")
    return est


# ================================================================ E-value（连续结局）
def e_value_continuous(beta_years: float, sd_outcome: float) -> dict:
    """连续结局的 E-value（VanderWeele & Ding 2017 推荐做法）。

    ① 把「年」的效应换算为标准差单位 d = |β| / sd(y)；
    ② 用 Chinn(2000) 近似 OR ≈ exp(0.91·d)；
    ③ E-value = OR + sqrt(OR·(OR−1))。
    说明：这与 step4 里对 log-RR 直接取 exp 的粗略做法不同；对连续结局应走本条。
    """
    if not np.isfinite(beta_years) or not np.isfinite(sd_outcome) or sd_outcome <= 0:
        return {"E_point": np.nan, "d": np.nan}
    d = abs(beta_years) / sd_outcome
    rr = float(np.exp(0.91 * d))
    e = rr + np.sqrt(rr * (rr - 1)) if rr > 1 else 1.0
    return {"E_point": float(e), "d": float(d), "rr_approx": rr}


# ================================================================ 森林图
def forest_plot(m: dict, path: Path, xlabel: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:                                     # noqa: BLE001
        return None
    fig, ax = plt.subplots(figsize=(8.8, 0.62 * (m["k"] + 2) + 1.3))
    y = np.arange(m["k"])[::-1]
    for yi, e, s, lab in zip(y, m["est"], m["se"], m["labels"]):
        lo, hi = e - 1.96 * s, e + 1.96 * s
        ax.plot([lo, hi], [yi, yi], color="#3b6ea5", lw=1.8)
        ax.plot([e], [yi], "s", color="#1f3b57", ms=8)
        ax.text(1.02, yi, f"{e:+.3f} ({lo:+.3f}, {hi:+.3f})",
                transform=ax.get_yaxis_transform(), va="center", fontsize=9)
    ax.axvline(0, color="#888", ls="--", lw=1)
    yd = -1.1
    ax.plot([m["ci_lo"], m["ci_hi"]], [yd, yd], color="#b3402f", lw=2.4)
    ax.plot([m["pooled"]], [yd], "D", color="#b3402f", ms=9)
    ax.text(1.02, yd, f"{m['pooled']:+.3f} ({m['ci_lo']:+.3f}, {m['ci_hi']:+.3f}), "
                      f"I²={m['I2']:.1f}%", transform=ax.get_yaxis_transform(),
            va="center", fontsize=9, color="#b3402f")
    ax.set_yticks(list(y) + [yd])
    ax.set_yticklabels(m["labels"] + ["Pooled (random-effects)"])
    ax.set_xlabel(xlabel)
    ax.set_title("牙齿脱落与生物学衰老加速：随机效应 Meta 汇总\n"
                 f"(Q = {m['Q']:.2f}, τ² = {m['tau2']:.4f}, I² = {m['I2']:.1f}%)",
                 fontsize=11.5, pad=12)
    lo_all = min(m["est"] - 1.96 * m["se"]); hi_all = max(m["est"] + 1.96 * m["se"])
    pad = 0.06 * (hi_all - lo_all) if hi_all > lo_all else 0.05
    ax.set_xlim(lo_all - pad, hi_all + pad)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ================================================================ 演示注入
def demo_inject(pf: pd.DataFrame, cohort: str, seed: int) -> pd.DataFrame:
    """演示模式：按**已知真值**给真实 ID 注入炎症与生物年龄加速。

    DGP：M = a·A + ε ；accel(年) = c·A + b·M + ε
        a = 0.60, b = 0.25, c = 0.30  →  总效应 0.45，NIE = 0.15，比例 1/3
    ⚠️ 合成数字不得写入论文。
    """
    rng = np.random.default_rng(seed + abs(hash(cohort)) % 10000)
    d = pf.copy()
    n = len(d)
    A = pd.to_numeric(d["edent_base"], errors="coerce").fillna(0).values.astype(float)
    for m, kappa in (("crp", DEMO_TRUTH["a"]), ("il6", .55),
                     ("fibrinogen", .45), ("wbc", .40)):
        d[m] = _z(kappa * A + rng.normal(0, 1, n))
    accel = (DEMO_TRUTH["c"] * A + DEMO_TRUTH["b"] * d["crp"].values
             + rng.normal(0, 1.6, n))
    d["kdm_clean_accel"] = accel
    d["bioage_accel_clean"] = accel
    d["kdm_accel"] = accel + rng.normal(0, 0.15, n)
    d["phenoage_accel"] = accel + rng.normal(0, 0.15, n)
    return d


def build_frame(df: pd.DataFrame, cohort: str, people: pd.DataFrame,
                demo: bool, seed: int, window: int = POST_EXPOSURE_WINDOW,
                bm_extra: pd.DataFrame | None = None
                ) -> tuple[pd.DataFrame, dict]:
    """人 × 1 行分析框：基线暴露 + 血样生物年龄（+ 炎症中介标志物），强制时序。

    bm_extra : 可选，血样长表（含 cohort,id + 炎症标志物列），用于**中介分析**。
               `people` 只带生物年龄列，不含原始炎症标志物，故需单独并入。
    """
    pf = person_frame(df, cohort)
    if pf.empty:
        return pd.DataFrame(), {"cohort": cohort, "reason": "长表无该队列"}
    pe_cols = ["cohort", "id", "year", "age", "kdm_accel", "kdm_clean_accel",
               "phenoage_accel", "n_markers", "n_markers_clean",
               "crp", "il6", "fibrinogen", "wbc"]
    pe = people[people["cohort"] == cohort][[c for c in pe_cols if c in people.columns]]
    pe = pe.rename(columns={"year": "blood_year", "age": "age_blood"})
    if "blood_year" not in pe.columns:
        pe["blood_year"] = np.nan
    # ⚠️ id 类型对齐：person_frame 的 id 恒为 str，血样表（CSV/各队列）可能是 int
    pf["id"] = pf["id"].astype(str)
    pe["id"] = pe["id"].astype(str)

    # ⚠️ 同一人可能有**多波血样**（如 CHARLS 2011+2015）。
    #    绝不能 drop_duplicates("id") 随便留一行（会留下**与暴露同年**的 2011 血样，
    #    造成 delta=0 的同期假象）。正确做法：先并入，算 delta = 血样年 − 基线暴露年，
    #    只保留 delta ∈ [0, window] 的波，同一人有多波合格时取**最早**的那波。
    m = pf.merge(pe, on=["cohort", "id"], how="inner")
    n0 = len(m)
    if m["blood_year"].notna().any():
        m["blood_delta"] = m["blood_year"] - m["year_base"]
        # ⚠️ 必须 **严格 > 0**：delta = 0 表示血样与暴露**同年**（如 CHARLS 2011 血样 vs
        #    2011 基线暴露）→ 那是同期横断面，不能当「暴露 → 后续衰老」的前瞻证据。
        ok = m["blood_delta"].between(1, window)
        m = m[ok].copy()
        # 同人多波合格 → 取**最早**的合格血样波（保留最短但非零的暴露-血样间隔）
        m = m.sort_values(["id", "blood_delta"]).drop_duplicates("id", keep="first")
    else:
        m["blood_delta"] = 0.0
        m = m.drop_duplicates("id", keep="first")
    # 牙数（仅 SHARE）→ 基线时不变剂量
    if "remaining_teeth" in df.columns:
        rt = (df[(df["cohort"] == cohort) & df["remaining_teeth"].notna()]
              .sort_values("year").groupby("id")["remaining_teeth"].first())
        m["teeth_base"] = m["id"].map(rt).clip(0, 28)
    # 实龄用血样时点，并中心化（accel 已与实龄正交，此项系数≈0，可作质控）
    if "age_blood" in m.columns:
        m["age_c"] = m["age_blood"] - m["age_blood"].mean()
    # 炎症中介标志物（真实模式）：timing 筛完后，按 (id, 血样年) 精确并入，
    # 避免多波血样造成「炎症波 ≠ 生物年龄波」的错配。
    if bm_extra is not None and not bm_extra.empty:
        ex = bm_extra[bm_extra["cohort"] == cohort].copy()
        if not ex.empty:
            ex["id"] = ex["id"].astype(str)
            keys = ["id"] + (["year"] if "year" in ex.columns else [])
            add = [c for c in ex.columns if c not in ("cohort", "id", "wave", "year")
                   and c not in m.columns]
            if add:
                ex2 = ex[["cohort"] + keys + add].rename(columns={"year": "blood_year"})
                m = m.merge(ex2.drop_duplicates(["cohort"] + keys),
                            on=["cohort"] + keys, how="left")
    m["cohort"] = cohort
    if demo:
        m = demo_inject(m, cohort, seed)
    info = {"cohort": cohort, "n_merged": n0, "n_kept": len(m),
            "n_dropped_timing": int(n0 - len(m)),
            "n_median_delta": float(np.nanmedian(m["blood_delta"])) if len(m) else np.nan}
    return m, info


# ================================================================ 汇总 md
def _write_md(tc, tm, td, tmed, tmet, demo: bool, ev: dict):
    src = "⚠️ **合成演示数据（数字不得写入论文）**" if demo else "真实协调化数据"
    L = ["# 第二篇：牙齿脱落 → 生物学衰老加速（结果汇总）", "",
         f"**数据来源**：{src}", "",
         "**效应口径**：β = 无牙颌者相比有牙者的**额外生物学衰老年数**（accel 单位为年）；",
         "年龄加速已按实龄正交化（生物年龄对实龄回归的残差）。", "",
         "> ⚠️ 本表为流水线自动产物。中介为**横断面**（炎症与生物年龄测于同一血样波），",
         "> 只能解读为机制提示，不宣称因果。", ""]
    _CN = "一二三四五六七八九十"
    sec = [0]     # 动态章节号（避免因某节为空而跳号）
    skipped = []

    def _head(title: str):
        sec[0] += 1
        L.extend([f"## {_CN[sec[0]-1]}、{title}", ""])

    if not tc.empty:
        _head("逐队列主模型（accel ~ 无牙颌 + 协变量）")
        L += ["| 队列 | 口径 | β 年 (95%CI) | p | n | 无牙颌数 | 实龄系数(质控≈0) |",
              "|---|---|---|---|---|---|---|"]
        for _, r in tc.iterrows():
            f = lambda v: f"{v:+.3f}" if np.isfinite(v) else "—"
            L.append(f"| {r['cohort']} | {r['outcome']} | "
                     f"{f(r['beta'])} ({f(r['lo'])}, {f(r['hi'])}) | {r['p']:.3g} | "
                     f"{r['n_people']:,} | {r['n_events']:,} | {f(r['age_c_beta'])} |")
        L.append("")
    if not tm.empty:
        _head("随机效应 Meta 汇总（主口径 KDM 去污染）")
        L += ["| 指标 | Pooled β | SE | 95%CI | p | k | Q | τ² | I²(%) |",
              "|---|---|---|---|---|---|---|---|---|"]
        for _, r in tm.iterrows():
            L.append(f"| {r['label']} | {r['pooled']:+.3f} | {r['se_pool']:.3f} | "
                     f"{r['ci_lo']:+.3f} ~ {r['ci_hi']:+.3f} | {r['p']:.3g} | {r['k']} | "
                     f"{r['Q']:.2f} | {r['tau2']:.4f} | {r['I2']:.1f} |")
        L.append("")
    if np.isfinite(ev.get("E_point", np.nan)):
        L += [f"**E-value**（主口径 pooled β）：点估计 **{ev['E_point']:.2f}**"
              f"（标准化 d = {ev['d']:.3f}）—— 需多强的未测混杂才能解释掉该关联。", ""]
    if not td.empty:
        _head("剂量-反应（仅牙数可得队列）")
        L += ["| 队列 | 规格 | β 年 (95%CI) | p | n |", "|---|---|---|---|---|"]
        for _, r in td.iterrows():
            L.append(f"| {r['cohort']} | {r['spec']} | "
                     f"{r['beta']:+.3f} ({r['lo']:+.3f}, {r['hi']:+.3f}) | "
                     f"{r['p']:.3g} | {r['n_people']:,} |")
        L.append("")
    else:
        skipped.append("剂量-反应（牙数 `remaining_teeth` 可得队列）")
    if not tmed.empty:
        _head("炎症中介（缺牙 → 炎症 → 衰老加速）")
        L += ["| 队列·通路 | a | b | NIE (95%CI) | NDE | 总效应 | 中介比例 |",
              "|---|---|---|---|---|---|---|"]
        for _, r in tmed.iterrows():
            f = lambda v: f"{v:+.3f}" if np.isfinite(v) else "—"
            prop = f"{r['prop']:.2f}" if np.isfinite(r.get("prop", np.nan)) else "—"
            L.append(f"| {r['label']} | {f(r['a'])} | {f(r['b'])} | "
                     f"{f(r['NIE'])} ({f(r.get('NIE_lo'))}, {f(r.get('NIE_hi'))}) | "
                     f"{f(r['NDE'])} | {f(r['TE'])} | {prop} |")
        L.append("")
    if not tmet.empty:
        _head("口径敏感性（换生物年龄算法）")
        L += ["| 队列 | 口径 | β 年 (95%CI) | p | n |", "|---|---|---|---|---|"]
        for _, r in tmet.iterrows():
            L.append(f"| {r['cohort']} | {r['outcome']} | "
                     f"{r['beta']:+.3f} ({r['lo']:+.3f}, {r['hi']:+.3f}) | {r['p']:.3g} | "
                     f"{r['n_people']:,} |")
        L.append("")
    if skipped:
        L += ["## 本次跳过的分析", "",
              "| 分析 | 原因 |", "|---|---|"]
        for s in skipped:
            L.append(f"| {s} | 当前血样表内无该队列/该变量（不影响已列出的分析） |")
        L.append("")
    L += ["---", "",
          "*方法：逐队列 OLS（HC3 稳健标准误）+ DerSimonian-Laird 随机效应 Meta；"
          "bootstrap 百分位 95% CI（个体层重抽样）；血样强制晚于暴露年。*"]
    (OUT_TAB / "bioage_outcome_summary.md").write_text("\n".join(L), encoding="utf-8")


# ================================================================ main
def main(demo: bool | None = None, seed: int = RANDOM_SEED, boot: int | None = None):
    B = boot or BIOAGE_BOOT
    OUT_TAB.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(HARM_LONG, low_memory=False)
    print(f"读取主长表 {HARM_LONG.name}（n={len(df):,}）")

    demo = (not BIOMARKER_FILE.exists()) if demo is None else demo
    if demo:
        print("⚠️ 演示模式：血样表不存在 → 合成标志物 + **已知真值**结局"
              "（数字不得写入论文）")
        people = None
    else:
        bio_path = OUT_TAB / "bioage_by_cohort.csv"
        if bio_path.exists():
            people = pd.read_csv(bio_path)
            print(f"读取已算好的生物年龄 {bio_path.name}（n={len(people):,}）")
        else:
            bm = pd.read_csv(BIOMARKER_FILE)
            print(f"读取血样表 {BIOMARKER_FILE.name}（n={len(bm):,}）→ 现算生物年龄")
            people, _ = compute_bioage_table(bm, allow_flagged=False)

    cohorts = sorted(df["cohort"].unique())
    # 真实模式下，中介分析需要原始炎症标志物（people 只带生物年龄列）
    bm_extra = None
    if not demo:
        try:
            bmx = pd.read_csv(BIOMARKER_FILE)
            mcols = ["cohort", "id"] + [c for c in MEDIATORS if c in bmx.columns]
            bm_extra = bmx[mcols].copy()
            print(f"中介用标志物来自 {BIOMARKER_FILE.name}："
                  f"{[c for c in MEDIATORS if c in bmx.columns]}")
        except Exception as e:                                    # noqa: BLE001
            print(f"⚠️ 无法读取中介标志物（{e}）→ 跳过中介分析")
    frames, infos = {}, []
    for coh in cohorts:
        if demo:
            pf0 = person_frame(df, coh)
            if pf0.empty:
                print(f"  [{coh:6s}] 长表无该队列 → 跳过"); continue
            meta = pf0[["cohort", "id", "age"]].copy()
            bmc = synth_marker_frame(meta, seed=seed)
            people_coh, _ = compute_bioage_table(bmc, allow_flagged=True)
            people_coh["bioage_accel_clean"] = people_coh["kdm_clean_accel"]
        else:
            people_coh = people
        m, info = build_frame(df, coh, people_coh, demo=demo, seed=seed,
                              bm_extra=bm_extra)
        infos.append(info)
        if m.empty:
            print(f"  [{coh:6s}] 无可用分析框（{info.get('reason', '时序/合并后为空')}）")
            continue
        frames[coh] = m
        print(f"  [{coh:6s}] n={len(m):>6,}（合并后剔除时序不符 "
              f"{info.get('n_dropped_timing', 0):,}）  无牙颌={int(m['edent_base'].fillna(0).sum()):>5,}  "
              f"血样滞后中位={info.get('n_median_delta', float('nan')):.0f} 年", flush=True)

    # ---------------- 一、逐队列主模型（多口径） ----------------
    rows_c, rows_m = [], []
    for coh, pf in frames.items():
        for metric, _lab in BIOAGE_METRICS:
            if metric not in pf.columns or pf[metric].notna().sum() < MIN_N:
                continue
            r = fit_exposure(pf, metric)
            if r is not None:
                rows_c.append(r)
    tc = pd.DataFrame(rows_c)
    tmet = tc[tc["outcome"] != PRIMARY_METRIC].copy() if not tc.empty else pd.DataFrame()
    prim = tc[tc["outcome"] == PRIMARY_METRIC].copy() if not tc.empty else pd.DataFrame()

    # ---------------- 二、剂量-反应 ----------------
    rows_d = []
    for coh, pf in frames.items():
        rows_d += fit_dose(pf, PRIMARY_METRIC)
    td = pd.DataFrame(rows_d)

    # ---------------- 三、Meta 汇总 ----------------
    rows_meta = []
    if not prim.empty:
        for scale, (bcol, scol) in (("年（原始）", ("beta", "se")),
                                    ("标准差单位", ("beta_std", "se_std"))):
            sub = prim.dropna(subset=[bcol, scol])
            if len(sub) < 2:
                continue
            mm = dl_meta(sub[bcol].values, sub[scol].values, sub["cohort"].tolist())
            rows_meta.append({"label": f"主口径 KDM 去污染 · {scale}",
                              "pooled": mm["pooled"], "se_pool": mm["se_pool"],
                              "ci_lo": mm["ci_lo"], "ci_hi": mm["ci_hi"], "p": mm["p"],
                              "k": mm["k"], "Q": mm["Q"], "tau2": mm["tau2"],
                              "I2": mm["I2"]})
    tm = pd.DataFrame(rows_meta)

    ev = {"E_point": np.nan, "d": np.nan}
    fig = None
    if not prim.empty and len(prim) >= 2:
        mm = dl_meta(prim["beta"].values, prim["se"].values, prim["cohort"].tolist())
        sd_pool = float(np.average(prim["sd_outcome"], weights=prim["n_people"]))
        ev = e_value_continuous(mm["pooled"], sd_pool)
        fig = forest_plot(mm, OUT_FIG / "forest_bioage_outcome.png",
                          "额外生物学衰老年数（年），无牙颌 vs 有牙")

    # ---------------- 四、炎症中介 ----------------
    rows_med = []
    for coh, pf in frames.items():
        for med in MEDIATORS:
            if med not in pf.columns or pf[med].notna().sum() < MIN_N:
                continue
            r = run_mediation(pf, med, PRIMARY_METRIC, seed, B)
            if r is not None:
                rows_med.append(r)
                print(f"  ✓ 中介 {r['label']:<30} n={r['n']:>5,}  "
                      f"NIE={r['NIE']:+.4f} [{r.get('NIE_lo', float('nan')):+.4f},"
                      f"{r.get('NIE_hi', float('nan')):+.4f}]  比例="
                      f"{r['prop'] if np.isfinite(r['prop']) else float('nan'):.2f}")
    tmed = pd.DataFrame(rows_med)

    # ---------------- 输出 ----------------
    tc.to_csv(OUT_TAB / "bioage_outcome_by_cohort.csv", index=False, encoding="utf-8-sig")
    tmet.to_csv(OUT_TAB / "bioage_outcome_metrics.csv", index=False, encoding="utf-8-sig")
    td.to_csv(OUT_TAB / "bioage_outcome_dose.csv", index=False, encoding="utf-8-sig")
    tm.to_csv(OUT_TAB / "bioage_outcome_meta.csv", index=False, encoding="utf-8-sig")
    tmed.to_csv(OUT_TAB / "bioage_outcome_mediation.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(infos).to_csv(OUT_TAB / "bioage_outcome_sampleflow.csv",
                               index=False, encoding="utf-8-sig")
    _write_md(tc, tm, td, tmed, tmet, demo, ev)

    print("\n—— 主模型（KDM 去污染）——")
    if not prim.empty:
        print(prim[["cohort", "beta", "se", "p", "n_people", "n_events"]]
              .to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    else:
        print("  （无可用队列）")
    if not tm.empty:
        print("\n—— Meta 汇总 ——")
        print(tm.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    if np.isfinite(ev.get("E_point", np.nan)):
        print(f"\nE-value: {ev['E_point']:.2f}（d = {ev['d']:.3f}）")
    print(f"\n已输出：\n  {OUT_TAB/'bioage_outcome_by_cohort.csv'}"
          f"\n  {OUT_TAB/'bioage_outcome_meta.csv'}"
          f"\n  {OUT_TAB/'bioage_outcome_mediation.csv'}"
          f"\n  {OUT_TAB/'bioage_outcome_summary.md'}" + (f"\n  {fig}" if fig else ""))
    return tc, tm, td, tmed


if __name__ == "__main__":
    main()
