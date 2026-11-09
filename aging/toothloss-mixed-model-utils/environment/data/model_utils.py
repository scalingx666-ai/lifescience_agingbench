# -*- coding: utf-8 -*-
"""
model_utils.py  混合效应模型拟合的共享工具
==========================================
把「随机斜率 -> 随机截距」的稳健回退、公式拼装、结果抽取集中在此，
供 step3（主模型）/ step5（敏感性·亚组·剂量反应）复用，避免多处复制。

设计要点
--------
1. **暴露默认用 `edent_base`（基线时不变暴露）**，而非时变的 `edent`：
   口腔状况会随随访变化，用当期测量做暴露会引入「反向因果 / 结局-暴露同时性」偏倚。
   基线暴露是流行病学的标准主口径；时变暴露 `edent` 作为敏感性分析。
2. 模型公式 `cog_z ~ <exposure> * time_c + <协变量> + (1+time_c | id)`；
   主系数 = `<exposure>:time_c` —— 暴露组相对参照组，**每年认知 z 分的额外变化**。
3. 随机斜率不收敛时自动降为随机截距，并在结果里记录 `re` 字段。
"""
from __future__ import annotations

import re
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from config import FORMULA, RANDOM_EFFECT, COHORTS

warnings.filterwarnings("ignore")

# 从 config.FORMULA 里把协变量部分抽出来（`... * time_c + age_c + female + ...`）
def _covariates(formula: str = FORMULA) -> str:
    rhs = formula.split("~", 1)[1]
    parts = [p.strip() for p in rhs.split("+")]
    keep = [p for p in parts if "time_c" not in p]
    # 去掉可能残留的星号交互（如 "edent * time_c" 已被上一步过滤）
    return " + ".join(keep)


COVARIATES = _covariates()


def build_formula(exposure: str, covariates: str | None = None,
                  extra: str = "") -> str:
    """拼装模型公式：暴露 × 时间 + 协变量 (+ 额外项)。"""
    cov = COVARIATES if covariates is None else covariates
    f = f"cog_z ~ {exposure} * time_c"
    if cov:
        f += f" + {cov}"
    if extra:
        f += f" + {extra}"
    return f


# 允许「按队列缺席」的协变量 —— 缺则该队列公式里剔除该项，而不是整队列报废。
OPTIONAL_COVS = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]


def build_cohort_formula(base_formula: str, d: pd.DataFrame) -> str:
    """把在**该队列中 100% 缺失**的可选协变量从句子里剔掉。

    典型情形：ELSA 没有城乡变量（rural 全缺）→ 若保留该项，patsy 会把
    **整个队列**的行全部剔除，导致该队列从 Meta 里消失。剔除该项后
    ELSA 仍可正常贡献（方法学上记「ELSA 未校正城乡」即可）。
    """
    fml = base_formula
    for c in OPTIONAL_COVS:
        if c in d.columns and d[c].notna().sum() == 0:
            fml = re.sub(rf"\s*\+\s*{re.escape(c)}\b", "", fml)
    return fml


def fit_mixed(df: pd.DataFrame, exposure: str = "edent_base",
              formula: str | None = None, term: str | None = None,
              covariates: str | None = None, extra: str = "",
              label: str = "") -> dict:
    """拟合单个混合效应模型并返回系数摘要。

    参数
    ----
    df        : 长表子集（须含 cog_z / time_c / id / cohort 及协变量）
    exposure  : 暴露变量名（默认 edent_base）
    formula   : 直接给定公式（给定时忽略 exposure/covariates/extra）
    term      : 要抽取的系数（默认 f"{exposure}:time_c"）
    label     : 结果里记录的模型标签

    返回 dict：cohort, label, n_ind, n_obs, beta, se, p, ci_lo, ci_hi, re, err
    """
    d = df.copy()
    fml = formula or build_formula(exposure, covariates, extra)

    # ⚠️ patsy 遇到缺失值会直接抛 "factor contains missing values"（不自动剔除），
    #    故必须显式按公式里出现的列剔除缺失行 —— 真实数据必然有缺失。
    fml = build_cohort_formula(fml, d)
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", fml))
    drop = [c for c in d.columns if c in toks]
    if drop:
        d = d.dropna(subset=drop)

    if "edu_years" in d.columns:
        d["edu_years"] = d["edu_years"] - d["edu_years"].mean()   # 中心化，改善数值稳定性
    d["_gid"] = d["cohort"].astype(str) + "_" + d["id"].astype(str)

    trm = term or f"{exposure}:time_c"
    coh = str(d["cohort"].iloc[0]) if len(d) else "?"

    base = dict(cohort=coh, label=label, n_ind=int(d["_gid"].nunique()),
                n_obs=int(len(d)), beta=np.nan, se=np.nan, p=np.nan,
                ci_lo=np.nan, ci_hi=np.nan, re="", err="")

    for attempt in ("random_slope", "random_intercept"):
        try:
            if attempt == "random_slope":
                md = smf.mixedlm(fml, data=d, groups=d["_gid"], re_formula=RANDOM_EFFECT)
            else:
                md = smf.mixedlm(fml, data=d, groups=d["_gid"])
            res = md.fit(reml=True, method="lbfgs", maxiter=400)
            if not res.converged:
                raise RuntimeError("not converged")
            ci = res.conf_int().loc[trm]
            base.update(beta=float(res.params[trm]), se=float(res.bse[trm]),
                        p=float(res.pvalues[trm]), ci_lo=float(ci[0]), ci_hi=float(ci[1]),
                        re=attempt, err="")
            return base
        except Exception as e:                                   # noqa: BLE001
            if attempt == "random_intercept":
                base["re"] = "FAILED"
                base["err"] = str(e)[:70]
    return base


def fit_mixed_multi(df: pd.DataFrame, formula: str, terms: list[str],
                    label: str = "") -> list[dict]:
    """**一次拟合**抽取多个系数（用于「多分类 × time」等需要同时报告多个对比的模型）。

    与 `fit_mixed` 的区别：只拟合一次，返回每个 term 一行 —— 避免为 k 个类别
    重复拟合 k 次（SHARE 单次 ≈450 s）。随机斜率不收敛时同样回退随机截距。
    """
    d = df.copy()
    fml = build_cohort_formula(formula, d)
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", fml))
    drop = [c for c in d.columns if c in toks]
    if drop:
        d = d.dropna(subset=drop)
    if "edu_years" in d.columns:
        d["edu_years"] = d["edu_years"] - d["edu_years"].mean()
    d["_gid"] = d["cohort"].astype(str) + "_" + d["id"].astype(str)
    coh = str(d["cohort"].iloc[0]) if len(d) else "?"

    def _blank(err=""):
        return [dict(cohort=coh, label=label, n_ind=int(d["_gid"].nunique()),
                     n_obs=int(len(d)), term=t, beta=np.nan, se=np.nan, p=np.nan,
                     ci_lo=np.nan, ci_hi=np.nan, re="FAILED" if err else "", err=err)
                for t in terms]

    for attempt in ("random_slope", "random_intercept"):
        try:
            if attempt == "random_slope":
                md = smf.mixedlm(fml, data=d, groups=d["_gid"], re_formula=RANDOM_EFFECT)
            else:
                md = smf.mixedlm(fml, data=d, groups=d["_gid"])
            res = md.fit(reml=True, method="lbfgs", maxiter=400)
            if not res.converged:
                raise RuntimeError("not converged")
            out = []
            for t in terms:
                ci = res.conf_int().loc[t]
                out.append(dict(cohort=coh, label=label, n_ind=int(d["_gid"].nunique()),
                                n_obs=int(len(d)), term=t, beta=float(res.params[t]),
                                se=float(res.bse[t]), p=float(res.pvalues[t]),
                                ci_lo=float(ci[0]), ci_hi=float(ci[1]),
                                re=attempt, err=""))
            return out
        except Exception as e:                                   # noqa: BLE001
            if attempt == "random_intercept":
                return _blank(str(e)[:70])
    return _blank("unknown")


def fit_all_cohorts(df: pd.DataFrame, cohorts, exposure: str = "edent_base",
                    label: str = "", **kw) -> pd.DataFrame:
    """对多个队列逐一拟合同一规格，返回结果表。"""
    rows = []
    for c in cohorts:
        sub = df[df["cohort"] == c]
        if len(sub) == 0:
            continue
        rows.append(fit_mixed(sub, exposure=exposure, label=label, **kw))
    return pd.DataFrame(rows)


def anchor_dose_frame(df: pd.DataFrame, cohorts=None,
                      min_people: int = 200, min_levels: int = 3) -> pd.DataFrame | None:
    """把「单波口腔模块」重锚为可用于**剂量-反应随访**的分析框。

    ⚠️ 为什么需要它（2026-10-07 实测教训）
    --------------------------------------
    连续牙数 `remaining_teeth` 在长表里**每人只有 1 行**（口腔模块只在个别波测得；
    本批 = SHARE W5/2013，48,750 人 × 1 行）。此时直接写 `cog_z ~ teeth * time_c`
    是**退化**的：同一个人没有跨时间的重复测量，`time_c` 不过是该行距**个人基线**的
    偏移，估出来的「斜率交互」并非衰退速度（实测 β≈0、p≈0.5 —— 是假象）。
    判别红旗：`n_obs ≈ n_ind`。

    做法：以**口腔模块所在波为锚点**，把 `time_c` 重定义为「距锚点的年数」（锚点波 = 0），
    锚点测得的牙数作为**时不变剂量** `teeth_base`，再向后随访其认知 —— 与主分析
    `edent_base` 口径同构。

    返回
    ----
    合并长表（含 `teeth_base` / 重锚 `time_c` / `_teeth_c` 中心化 / `_tcat_n` 五分类）；
    若无任何队列满足条件则返回 ``None``。
    """
    cohorts = list(cohorts) if cohorts is not None else list(COHORTS)
    if "remaining_teeth" not in df.columns:
        return None
    src = df[df["remaining_teeth"].notna()]
    if len(src) == 0:
        return None
    pieces = []
    for c in cohorts:
        s = src[src["cohort"] == c]
        if len(s) == 0:
            continue
        anchor = int(s["year"].mode().iloc[0])
        tb = s[s["year"] == anchor].groupby("id")["remaining_teeth"].first()
        full = df[(df["cohort"] == c) & (df["year"] >= anchor)].copy()
        full = full.merge(tb.rename("teeth_base"), left_on="id",
                          right_index=True, how="inner")
        # ⚠️ 牙齿数不可能为负：SHARE `ph092`（缺失牙数）上限可到 30（有人计入智齿），
        #    28 − ph092 会得到 −1/−2（实测 679 人，1.4%）→ 一律 clip 到 [0, 28]。
        full["teeth_base"] = full["teeth_base"].clip(lower=0, upper=28)
        if full["teeth_base"].nunique() < min_levels or len(full) < min_people:
            continue
        full["time_c"] = full["year"] - anchor          # 重锚：锚点波 t = 0
        full["_teeth_c"] = full["teeth_base"] - tb.mean()
        full["_tcat_n"] = np.select(
            [full["teeth_base"] <= 0, full["teeth_base"] <= 9,
             full["teeth_base"] <= 19, full["teeth_base"] <= 27],
            [0, 1, 2, 3], default=4)
        pieces.append(full)
    if not pieces:
        return None
    return pd.concat(pieces, ignore_index=True)


def fmt_beta(r) -> str:
    """β (95% CI) 的格式化输出。"""
    if not np.isfinite(r.get("beta", np.nan)):
        return "—"
    return f"{r['beta']:+.4f} ({r['ci_lo']:+.4f}, {r['ci_hi']:+.4f})"


def fmt_p(p) -> str:
    if p is None or not np.isfinite(p):
        return "—"
    if p < 1e-16:
        return "<1e-16"
    return f"{p:.3g}"
