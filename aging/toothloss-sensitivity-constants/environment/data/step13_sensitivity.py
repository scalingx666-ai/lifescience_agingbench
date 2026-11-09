# -*- coding: utf-8 -*-
"""step13_sensitivity.py —— 第二篇（缺牙 → 生物衰老加速）的敏感性分析全套。

用户指令（2026-10-10）：
  ① 主推「中国 vs 西方差异」作为叙事亮点
  ② 定稿协变量集与敏感性分析

设计原则
--------
- **不重算生物年龄**：直接读 `harmonized_biomarkers.csv` 里已算好的 accel 列
  （由 step11 按 (cohort, wave) 分组拟合，已修批次效应）。
- **协变量分层推进**：粗模型（仅 age_c）→ 最小充分集 → 充分集，
  看效应量是否被调整"吃掉"。
- **暴露/时序口径敏感性**：A. 主口径（delta 1–12）；B. 严格 delta≥1 且排除前 2 年
  （反向因果窗口）；C. 仅 delta=0+1（同期/近端）做对照；D. 最早血样 vs 最晚血样。
- **异质性分位检验**：把「中国 vs 西方」当作预设假说，用交互项与分层 Meta 量化。

输出
----
  output/tables/bioage_sensitivity_covariates.csv    协变量阶梯
  output/tables/bioage_sensitivity_exposure.csv      暴露/时序口径
  output/tables/bioage_sensitivity_subgroup.csv      亚组（年龄/性别/教育/城乡）
  output/tables/bioage_sensitivity_summary.md        可读汇总

⚠️ 本脚本不含任何演示模式数字；所有结果来自真实长表。
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

warnings.filterwarnings("ignore")

from config import DATA_HARM, OUT_TAB  # noqa: E402
from config_biomarker import POST_EXPOSURE_WINDOW  # noqa: E402

__all__ = ["POST_EXPOSURE_WINDOW", "build_analysis_frame", "fit_one",
           "load_frames", "PRIMARY_METRIC", "COV_LADDER", "run_meta"]

OUT_TABLES = OUT_TAB
BIOAGE_INPUT = DATA_HARM / "harmonized_biomarkers.csv"
PRIMARY_METRIC = "bioage_accel_clean"      # 血样长表里的列名（= step12 的 kdm_clean_accel）
BIOAGE_METRICS = [
    ("bioage_accel_clean", "KDM 去污染（主口径）"),
    ("kdm_accel",          "KDM 全标志物（含炎症组分）"),
    ("phenoage_accel",     "Levine PhenoAge"),
]

MIN_N = 200          # 单格最少样本
MIN_SUBGROUP = 300   # 亚组最少样本


# ------------------------------------------------------------------ 数据装配
def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (person_frame, biomarker_frame)，均已按 id 规范化为 str。"""
    bm = pd.read_csv(BIOAGE_INPUT, low_memory=False)
    bm["id"] = bm["id"].astype(str)
    pf = pd.read_csv(BIOAGE_INPUT.parent / "harmonized_long_anchored.csv", low_memory=False)
    pf["id"] = pf["id"].astype(str)
    return pf, bm


def build_analysis_frame(pf: pd.DataFrame, bm: pd.DataFrame,
                         window: int = POST_EXPOSURE_WINDOW,
                         strict_min_delta: int = 1) -> pd.DataFrame:
    """人 × 1 行：(基线暴露) + (暴露后血样 accel)。

    与 step12 的口径保持一致：
      - 基线暴露 = 该人**最早**一波的 edent_base
      - 血样滞后 delta = blood_year - year_base，必须 `strict_min_delta <= delta <= window`
      - 同一人多波合格时取**最早**那波（keep='first'）
    """
    base_cols = ["edent_base", "age", "age_c", "female", "edu_years",
                 "married", "rural", "ever_smoke", "year"]
    exp = pf.dropna(subset=["edent_base"]).copy()
    exp = exp.sort_values(["cohort", "id", "year"])
    exp = exp.drop_duplicates(["cohort", "id"], keep="first")
    exp = exp[["cohort", "id"] + [c for c in base_cols if c in exp.columns]]
    exp = exp.rename(columns={"year": "year_base"})

    bio_cols = ["cohort", "id", "wave", "year"] + [m for m, _ in BIOAGE_METRICS]
    bio_cols = [c for c in bio_cols if c in bm.columns]
    b = bm[bio_cols].copy()

    m = b.merge(exp, on=["cohort", "id"], how="inner")
    if m.empty:
        return m
    m["blood_delta"] = m["year"] - m["year_base"]
    ok = m["blood_delta"].between(strict_min_delta, window)
    m = m[ok].copy()
    if m.empty:
        return m
    m = m.sort_values(["cohort", "id", "blood_delta"])
    m = m.drop_duplicates(["cohort", "id"], keep="first")
    return m.reset_index(drop=True)


# ------------------------------------------------------------------ OLS 工具
def _ols(y: np.ndarray, terms: list[np.ndarray], names: list[str],
         cov_type: str = "HC1") -> dict:
    import statsmodels.api as sm
    X = sm.add_constant(np.column_stack(terms), has_constant="add")
    r = sm.OLS(y, X).fit(cov_type=cov_type)
    out = {}
    for i, nm in enumerate(names, start=1):
        ci = r.conf_int()[i]
        out[nm] = {"beta": float(r.params[i]), "se": float(r.bse[i]),
                   "p": float(r.pvalues[i]), "lo": float(ci[0]), "hi": float(ci[1])}
    return out


def fit_one(d: pd.DataFrame, outcome: str, covs: list[str],
            exposure: str = "edent_base") -> dict | None:
    """单队列 OLS：outcome ~ exposure + covs。连续量中心化。"""
    if exposure not in d.columns or outcome not in d.columns:
        return None
    # need 只含**必须非缺失**的暴露与结局；协变量是否可用稍后按本子集判定
    need = [exposure, outcome]
    dd = d.dropna(subset=need).copy()
    # ⚠️ 只保留在**本子集内确实有变异**的协变量（ELSA 无 rural）——
    #    绝不能因某个协变量全缺而 dropna 清空整队（与 step12 `_usable_covs` 同源）
    covs = [c for c in covs if c in dd.columns
            and pd.to_numeric(dd[c], errors="coerce").notna().any()
            and pd.to_numeric(dd[c], errors="coerce").std(skipna=True) > 0]
    # 再按**实际保留的协变量**剔缺失（而非按用户传入的全集）
    if covs:
        dd = dd.dropna(subset=covs)
    if len(dd) < MIN_N or dd[exposure].nunique() < 2:
        return None
    y = pd.to_numeric(dd[outcome], errors="coerce").values.astype(float)
    terms, names = [], []
    for x in [exposure] + covs:
        if x not in dd.columns:
            continue
        v = pd.to_numeric(dd[x], errors="coerce").values.astype(float)
        terms.append(v - np.nanmean(v))
        names.append(x)
    keep = np.isfinite(y) & np.all(np.isfinite(np.column_stack(terms)), axis=1)
    y, terms = y[keep], [t[keep] for t in terms]
    if len(y) < MIN_N:
        return None
    r = _ols(y, terms, names)
    if exposure not in r:
        return None
    rec = dict(r[exposure])
    # ⚠️ 必须回写**实际进入模型**的协变量集（而非调用方传入的请求集）：
    #    上游 fit_one 会剔除本子集内无变异的协变量（典型：ELSA 无 rural），
    #    若仍按请求集记录，Table S1 的 `n_cov/covs` 会与正文矛盾。
    rec.update(n=len(y), n_events=int(dd.loc[keep, exposure].sum()),
               sd_outcome=float(np.std(y, ddof=1)),
               covs_fitted="+".join(covs) if covs else "—",
               n_cov_fitted=len(covs))
    return rec


# ------------------------------------------------------------------ ① 协变量阶梯
COV_LADDER = [
    ("粗模型（未调整）",              []),
    ("+ 实龄",                        ["age_c"]),
    ("+ 实龄 性别 教育",              ["age_c", "female", "edu_years"]),
    ("+ 婚姻 城乡 吸烟",              ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]),
]


def run_covariate_ladder(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, covs in COV_LADDER:
        for coh in ["HRS", "ELSA", "CHARLS"]:
            s = m[m.cohort == coh]
            r = fit_one(s, PRIMARY_METRIC, covs)
            if r is None:
                continue
            # ⚠️ 记录**实际拟合**的协变量集（ELSA 实调 5 项，非请求的 6 项）
            fitted = r.get("covs_fitted", "+".join(covs) if covs else "—")
            rows.append(dict(step=label, cohort=coh, beta=r["beta"], se=r["se"],
                             p=r["p"], lo=r["lo"], hi=r["hi"], n=r["n"],
                             n_cov=r.get("n_cov_fitted", len(covs)),
                             covs=fitted,
                             covs_requested="+".join(covs) if covs else "—"))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ ② 暴露/时序口径
def run_exposure_variants(pf: pd.DataFrame, bm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    variants = [
        ("A 主口径 delta 1–12",       dict(window=POST_EXPOSURE_WINDOW, strict_min_delta=1)),
        ("B 排除前 2 年 delta 3–12",  dict(window=POST_EXPOSURE_WINDOW, strict_min_delta=3)),
        ("C 最长滞后 delta 6–12",     dict(window=POST_EXPOSURE_WINDOW, strict_min_delta=6)),
    ]
    for label, kw in variants:
        mm = build_analysis_frame(pf, bm, **kw)
        if mm.empty:
            continue
        for coh in ["HRS", "ELSA", "CHARLS"]:
            r = fit_one(mm[mm.cohort == coh], PRIMARY_METRIC,
                        ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"])
            if r is None:
                continue
            rows.append(dict(variant=label, cohort=coh, beta=r["beta"], se=r["se"],
                             p=r["p"], lo=r["lo"], hi=r["hi"], n=r["n"],
                             med_delta=float(mm[mm.cohort == coh]["blood_delta"].median())))
    return pd.DataFrame(rows)


def run_leaves_variants(pf: pd.DataFrame, bm: pd.DataFrame) -> pd.DataFrame:
    """暴露定义敏感性：基线暴露 vs 每波实时暴露（leaf=当年测得）。"""
    rows = []
    # —— 基线暴露（主口径）——
    m = build_analysis_frame(pf, bm)
    for coh in ["HRS", "ELSA", "CHARLS"]:
        r = fit_one(m[m.cohort == coh], PRIMARY_METRIC,
                    ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"])
        if r:
            rows.append(dict(definition="基线暴露（最早波）", cohort=coh,
                             beta=r["beta"], se=r["se"], p=r["p"], n=r["n"]))
    # —— 实时暴露：血样所在波/紧邻波的实测缺牙 ——
    base_cols = ["edent", "age", "age_c", "female", "edu_years", "married",
                 "rural", "ever_smoke", "year"]
    exp = pf[[c for c in ["cohort", "id"] + base_cols if c in pf.columns]].copy()
    exp = exp.dropna(subset=["edent"]).rename(columns={"year": "exposure_year"})
    b = bm[["cohort", "id", "year", PRIMARY_METRIC]].copy()
    mm = b.merge(exp, on=["cohort", "id"], how="inner")
    if not mm.empty:
        mm["d"] = (mm["year"] - mm["exposure_year"]).abs()
        mm = mm.sort_values(["cohort", "id", "d"]).drop_duplicates(["cohort", "id"], keep="first")
        for coh in ["HRS", "ELSA", "CHARLS"]:
            r = fit_one(mm[mm.cohort == coh].rename(columns={"edent": "edent_base"}),
                        PRIMARY_METRIC,
                        ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"])
            if r:
                rows.append(dict(definition="同期实测暴露（±最近）", cohort=coh,
                                 beta=r["beta"], se=r["se"], p=r["p"], n=r["n"]))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ ③ 亚组
def run_subgroups(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    covs = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
    specs = [
        ("年龄 50–64",         lambda d: d.age.between(50, 63.999)),
        ("年龄 65–74",         lambda d: d.age.between(64, 73.999)),
        ("年龄 ≥75",           lambda d: d.age >= 74),
        ("男性",               lambda d: d.female == 0),
        ("女性",               lambda d: d.female == 1),
        ("教育 ≤6 年",         lambda d: d.edu_years <= 6),
        ("教育 >6 年",         lambda d: d.edu_years > 6),
        ("农村",               lambda d: d.rural == 1),
        ("城市",               lambda d: d.rural == 0),
        ("从不吸烟",           lambda d: d.ever_smoke == 0),
        ("曾吸烟",             lambda d: d.ever_smoke == 1),
        ("随访 ≥中位",         lambda d: d.blood_delta >= d.blood_delta.median()),
        ("随访 <中位",         lambda d: d.blood_delta < d.blood_delta.median()),
    ]
    for coh in ["HRS", "ELSA", "CHARLS"]:
        s = m[m.cohort == coh]
        for label, fn in specs:
            try:
                sub = s[fn(s)]
            except Exception:
                continue
            if len(sub) < MIN_SUBGROUP or sub.edent_base.nunique() < 2:
                continue
            r = fit_one(sub, PRIMARY_METRIC, covs)
            if r is None:
                continue
            rows.append(dict(cohort=coh, subgroup=label, beta=r["beta"],
                             se=r["se"], p=r["p"], n=r["n"],
                             n_events=r["n_events"]))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ ④ 交互检验
# ⚠️ 交互模型的协变量集**不含 `rural`**：ELSA 无城乡变量（rural 全缺失），
#    若纳入则 complete-case dropna 会把 ELSA 整队 4,390 人删除，
#    使「西方（HRS+ELSA）vs 中国」退化为「美国 vs 中国」（第十轮严格审稿发现）。
#    与主模型协变量集的不对称已在 Methods 声明。
INTERACTION_COVS = ["age_c", "female", "edu_years", "married", "ever_smoke"]


def _fit_interaction(d: pd.DataFrame, covs: list[str], label: str) -> pd.DataFrame:
    """在给定子集上拟合 `outcome ~ edent_base * west + covs`，返回交互项表。

    统一输出：模型层（三队 / 仅 HRS+CHARLS）、term、β/se/p/CI、n 与队列构成。
    """
    import statsmodels.formula.api as smf
    if d.empty or d["cohort"].nunique() < 2:
        return pd.DataFrame()
    dd = d.dropna(subset=[PRIMARY_METRIC, "edent_base"]).copy()
    dd["west"] = dd["cohort"].isin(["HRS", "ELSA"]).astype(int)
    if dd["west"].nunique() < 2 or dd["edent_base"].nunique() < 2:
        return pd.DataFrame()
    # 仅保留本子集内确实有变异的协变量（与 fit_one 同源口径）
    cv = [c for c in covs if c in dd.columns
          and pd.to_numeric(dd[c], errors="coerce").notna().any()
          and pd.to_numeric(dd[c], errors="coerce").std(skipna=True) > 0]
    for c in cv:
        dd[c] = pd.to_numeric(dd[c], errors="coerce")
        dd[c] = dd[c] - np.nanmean(dd[c])
    dd = dd.dropna(subset=cv + [PRIMARY_METRIC, "edent_base"])
    if len(dd) < MIN_N:
        return pd.DataFrame()
    fml = "%s ~ edent_base * west + %s" % (PRIMARY_METRIC, " + ".join(cv)) if cv \
        else "%s ~ edent_base * west" % PRIMARY_METRIC
    r = smf.ols(fml, data=dd).fit(cov_type="HC1")
    ci = r.conf_int()
    cohorts = "+".join(sorted(dd["cohort"].unique()))
    nc = dd["cohort"].value_counts().to_dict()
    n_by_cohort = " | ".join("%s %d" % (k, v) for k, v in sorted(nc.items()))
    rows = []
    for k in ["edent_base", "west", "edent_base:west"]:
        if k in r.params.index:
            rows.append(dict(model=label, term=k, beta=float(r.params[k]),
                             se=float(r.bse[k]), p=float(r.pvalues[k]),
                             lo=float(ci.loc[k, 0]), hi=float(ci.loc[k, 1]),
                             n=len(dd), cohorts=cohorts,
                             n_by_cohort=n_by_cohort,
                             covs="+".join(cv) if cv else "—"))
    return pd.DataFrame(rows)


def run_interactions(m: pd.DataFrame) -> pd.DataFrame:
    """西方（HRS+ELSA）vs 中国（CHARLS）的效应修饰检验。

    ⚠️ 不能同时放 `west` 与 `C(cohort)`：两者完全共线 → `west` 系数会爆到 1e12。
    改用「中国为参照」的单层因子：`west` 即队列固定效应本身，无需重复放。

    输出**两个模型层**：
      - `三队（HRS+ELSA vs CHARLS）`：主口径，协变量集不含 rural（见 INTERACTION_COVS）
      - `仅 HRS vs CHARLS`：次级口径，与主模型同协变量集（含 rural 亦可用），
        用于说明三队口径的差异并非由「剔除 rural」引入。
    """
    d = m[m.cohort.isin(["HRS", "ELSA", "CHARLS"])].copy()
    out = [_fit_interaction(d, INTERACTION_COVS, "三队（HRS+ELSA vs CHARLS）")]
    d2 = m[m.cohort.isin(["HRS", "CHARLS"])].copy()
    out.append(_fit_interaction(d2, INTERACTION_COVS + ["rural"], "仅 HRS vs CHARLS"))
    out = [t for t in out if not t.empty]
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ------------------------------------------------------------------ ⑤ Meta
def run_meta(tbl: pd.DataFrame, col_beta="beta", col_se="se", label=""):
    """对一张含 beta/se/cohort 的表做 DL 随机效应 Meta。"""
    from step4_meta import dl_meta
    if tbl.empty:
        return None
    est = tbl[col_beta].values.astype(float)
    se = tbl[col_se].values.astype(float)
    labels = tbl["cohort"].tolist()
    out = dl_meta(est, se, labels)
    out = dict(out) if isinstance(out, dict) else {"pooled": out}
    out["label"] = label
    return out


# ------------------------------------------------------------------ 主入口
def main() -> None:
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("step13 敏感性分析（缺牙 → 生物衰老加速）")
    print("=" * 70)

    pf, bm = load_frames()
    m = build_analysis_frame(pf, bm)
    print("分析框：n=%d，队列 %s" % (len(m), sorted(m.cohort.unique())))
    print("  同波（delta）分布：")
    print(m.groupby("cohort")["blood_delta"].describe()[["count", "mean", "50%", "max"]].round(2))

    # ① 协变量阶梯
    print("\n[1/5] 协变量阶梯 ……")
    t1 = run_covariate_ladder(m)
    t1.to_csv(OUT_TABLES / "bioage_sensitivity_covariates.csv", index=False, encoding="utf-8-sig")

    # ② 时序口径
    print("[2/5] 时序/滞后口径 ……")
    t2 = run_exposure_variants(pf, bm)
    t2.to_csv(OUT_TABLES / "bioage_sensitivity_exposure.csv", index=False, encoding="utf-8-sig")

    print("[3/5] 暴露定义（基线 vs 实时）……")
    t3 = run_leaves_variants(pf, bm)

    # ③ 亚组
    print("[4/5] 亚组分析 ……")
    t4 = run_subgroups(m)
    t4.to_csv(OUT_TABLES / "bioage_sensitivity_subgroup.csv", index=False, encoding="utf-8-sig")

    # ④ 交互
    print("[5/5] 中西方交互检验 ……")
    t5 = run_interactions(m)
    if not t5.empty:
        t5.to_csv(OUT_TABLES / "bioage_sensitivity_interaction.csv",
                  index=False, encoding="utf-8-sig")

    # ⑤ Meta：三队 vs 西方双队（叙事核心）
    print("[6/5] Meta 汇总（三队 vs 西方双队）……")
    COV_FULL = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
    meta_rows = []
    for coh in ["HRS", "ELSA", "CHARLS"]:
        r = fit_one(m[m.cohort == coh], PRIMARY_METRIC, COV_FULL)
        if r:
            meta_rows.append(dict(cohort=coh, beta=r["beta"], se=r["se"], n=r["n"]))
    tmeta = pd.DataFrame(meta_rows)
    meta_outs = []
    if not tmeta.empty:
        meta_outs.append(run_meta(tmeta, label="三队（HRS+ELSA+CHARLS）"))
        west = tmeta[tmeta.cohort.isin(["HRS", "ELSA"])]
        if len(west) >= 2:
            meta_outs.append(run_meta(west, label="西方双队（HRS+ELSA）"))

    # ---- 汇总 md ----
    L = []
    W = L.append
    W("# 敏感性分析汇总：缺牙 → 生物衰老加速（第二篇）")
    W("")
    W("> 生成：`step13_sensitivity.py`｜主口径 `%s`｜分析框 n=%d" % (PRIMARY_METRIC, len(m)))
    W("> ⚠️ 全部为真实数据结果；协变量与敏感性本轮定稿。")
    W("")

    W("## 一、协变量阶梯（检验效应是否被调整'吃掉'）")
    W("")
    W("| 模型 | 队列 | β（年） | 95%CI | p | n |")
    W("|---|---|---|---|---|---|")
    for _, r in t1.iterrows():
        W("| %s | %s | %+.3f | %.2f–%.2f | %.2e | %d |"
          % (r["step"], r["cohort"], r["beta"], r["lo"], r["hi"], r["p"], r["n"]))
    W("")

    W("## 二、时序/滞后口径敏感性")
    W("")
    W("| 口径 | 队列 | β（年） | 95%CI | p | n | 中位滞后 |")
    W("|---|---|---|---|---|---|---|")
    for _, r in t2.iterrows():
        W("| %s | %s | %+.3f | %.2f–%.2f | %.2e | %d | %.1f |"
          % (r["variant"], r["cohort"], r["beta"], r["lo"], r["hi"], r["p"], r["n"], r["med_delta"]))
    W("")

    if not t3.empty:
        W("## 三、暴露定义敏感性（基线 vs 同期实测）")
        W("")
        W("| 暴露定义 | 队列 | β（年） | p | n |")
        W("|---|---|---|---|---|")
        for _, r in t3.iterrows():
            W("| %s | %s | %+.3f | %.2e | %d |" % (r["definition"], r["cohort"], r["beta"], r["p"], r["n"]))
        W("")

    if not t4.empty:
        W("## 四、亚组分析")
        W("")
        W("| 队列 | 亚组 | β（年） | SE | p | n |")
        W("|---|---|---|---|---|---|")
        for _, r in t4.iterrows():
            W("| %s | %s | %+.3f | %.3f | %.3f | %d |"
              % (r["cohort"], r["subgroup"], r["beta"], r["se"], r["p"], r["n"]))
        W("")

    if not t5.empty:
        W("## 五、中西方交互检验（核心：异质性是否显著）")
        W("")
        W("| 模型层 | 项 | β | 95%CI | p | n | 队列构成 | 协变量 |")
        W("|---|---|---|---|---|---|---|---|")
        for _, r in t5.iterrows():
            W("| %s | %s | %+.3f | %.3f–%.3f | %.3f | %d | %s | %s |"
              % (r["model"], r["term"], r["beta"], r["lo"], r["hi"], r["p"],
                 r["n"], r.get("n_by_cohort", ""), r.get("covs", "")))
        W("")
        W("> `edent_base` = 中国（CHARLS）组内效应；`edent_base:west` = 西方相对中国的**额外**效应。")
        W("> ⚠️ 主口径为「三队（HRS+ELSA vs CHARLS）」，其协变量集**不含 rural**"
          "（ELSA 无城乡变量，纳入会整队删除）。次级口径「仅 HRS vs CHARLS」含 rural，"
          "用于核验两者差异非由剔除 rural 引入。")
        W("")

    if meta_outs:
        W("## 六、Meta 汇总（充分调整集）")
        W("")
        W("| 口径 | pooled（年） | 95%CI | p | k | I² |")
        W("|---|---|---|---|---|---|")
        for o in meta_outs:
            if o is None:
                continue
            W("| %s | %+.3f | %.3f–%.3f | %.4f | %d | %.1f%% |"
              % (o.get("label", ""), o.get("pooled", np.nan),
                 o.get("ci_lo", np.nan), o.get("ci_hi", np.nan),
                 o.get("p", np.nan), o.get("k", 0), o.get("I2", np.nan)))
        W("")

    md = "\n".join(L)
    out = OUT_TABLES / "bioage_sensitivity_summary.md"
    out.write_text(md, encoding="utf-8")
    print("\n[写入] " + str(out))
    print(md[-3000:])


if __name__ == "__main__":
    main()
