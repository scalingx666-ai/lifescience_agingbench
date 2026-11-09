#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
step21_nhanes_analysis.py
=========================
A 档同源加强：NHANES 独立第四队列 —— 分析。

科学问题：主线的机制假设是「牙周破坏 -> 全身炎症升高」。
主线只能用自报缺牙；本队列用**临床全口牙周探诊**与**连续余留牙数**检验同一方向，
从而 (a) 独立复核机制， (b) 补上主线「三队列均无连续牙数、无法做剂量-反应」的空白。

模型（横断面，与主线「中介为横断面、只作机制提示」口径一致）：
  (1) 主模型  炎症 ~ mPD + age + female + edu + married + race + cycle        [OLS, HC1]
  (2) 牙周炎二分类（mPD>=? / pctPD4）同规格
  (3) 余留牙数 炎症 ~ nTeeth + 同协变量
  (4) 无牙颌   炎症 ~ edent  + 同协变量
  (5) 剂量-反应：余留牙数五分位 + 限制立方样条（3 节点）
  (6) 加权敏感性：WLS（WTMEC2YR，两周期各半权重，按 NHANES 合并周期惯例 /2）
  (7) CRP 分支：仅在拥有 CRP 的周期内单独跑（本数据默认缺）

输出：
  output/tables/nhanes_main_models.csv
  output/tables/nhanes_dose_response.csv
  output/tables/nhanes_weighted.csv
  output/tables/nhanes_sensitivity.csv
  output/tables/nhanes_analysis_log.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parent.parent
HARM = ROOT / "data" / "harmonized"
TAB = ROOT / "output" / "tables"
TAB.mkdir(parents=True, exist_ok=True)

LOG: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


COVS = ["age", "female", "edu_years", "married", "race_d1", "race_d2", "race_d3", "cycle_h"]
OUTCOMES = ["WBC", "NLR", "ALB"]


# ---------------------------------------------------------------- 数据
def build_frame() -> pd.DataFrame:
    df = pd.read_csv(HARM / "nhanes_oral_inflammation.csv")
    df = df[df["age"] >= 50].copy()

    # 种族哑变量（RIDRETH3: 1 墨裔 2 其他西裔 3 非西裔白 4 非西裔黑 5 非西裔亚 6 其他）
    r = pd.to_numeric(df["race"], errors="coerce")
    df["race_d1"] = (r == 3).astype(float)          # 非西裔白人（参照系近似用 4）
    df["race_d2"] = (r == 4).astype(float)          # 非西裔黑人
    df["race_d3"] = (r == 5).astype(float)          # 非西裔亚裔
    df["cycle_h"] = (df["cycle"] == "H").astype(float)

    # 牙周炎二分类（常用口径：>=2 个位点 PD>=4mm 且 >=2 个位点 LA>=3mm；
    # 本数据只有比例，退而用 pctPD4 > 0 表示「存在 >=4mm 位点」）
    df["perio_any"] = (df["pctPD4"] > 0).astype(float).where(df["pctPD4"].notna())

    # 余留牙数五分位
    v = df["nTeeth"]
    try:
        df["teeth_q"] = pd.qcut(v, 5, labels=False, duplicates="drop") + 1
    except ValueError:
        df["teeth_q"] = pd.qcut(v.rank(method="first"), 5, labels=False) + 1

    return df


def fit(y: pd.Series, X: pd.DataFrame, w: pd.Series | None = None):
    """OLS + HC1（可选 WLS）。返回 dict。"""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(d) < 30:
        return None
    yy, XX = d["y"], sm.add_constant(d[X.columns])
    try:
        if w is None:
            r = sm.OLS(yy, XX).fit(cov_type="HC1")
            n = int(r.nobs)
        else:
            ww = w.loc[d.index]
            ok = ww.notna() & (ww > 0)
            if ok.sum() < 30:
                return None
            r = sm.WLS(yy[ok], XX[ok], weights=ww[ok]).fit(cov_type="HC1")
            n = int(r.nobs)
    except Exception:                                    # noqa: BLE001
        return None
    return {"res": r, "n": n}


def row(model: str, term: str, f, outcome: str, cohort: str = "NHANES") -> dict:
    r = f["res"]
    return {
        "model": model,
        "cohort": cohort,
        "outcome": outcome,
        "term": term,
        "beta": round(float(r.params[term]), 4),
        "se": round(float(r.bse[term]), 4),
        "ci_low": round(float(r.conf_int().loc[term, 0]), 4),
        "ci_high": round(float(r.conf_int().loc[term, 1]), 4),
        "p": float(r.pvalues[term]),
        "n": f["n"],
    }


# ---------------------------------------------------------------- 分析
def run_main(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    specs = [
        ("Perio (mPD)", "mPD", None),
        ("Perio (mLA)", "mLA", None),
        ("Perio any >=4mm", "perio_any", None),
        ("Teeth lost (per tooth)", "nTeeth", None),
        ("Edentulism", "edent", None),
    ]
    for label, var, _ in specs:
        if var not in df.columns:
            continue
        for y in OUTCOMES:
            sub = df[df[var].notna() & df[y].notna()]
            cols = [var] + [c for c in COVS if c in df.columns]
            f = fit(sub[y], sub[cols])
            if f is None:
                continue
            rows.append(row(label, var, f, y))
            # 每 1000 颗牙的效应（便于解读）
            if var == "nTeeth":
                r = f["res"]
                rows.append({
                    "model": label + " (per 10 teeth)", "cohort": "NHANES",
                    "outcome": y, "term": var,
                    "beta": round(float(r.params[var]) * 10, 4),
                    "se": round(float(r.bse[var]) * 10, 4),
                    "ci_low": round(float(r.conf_int().loc[var, 0]) * 10, 4),
                    "ci_high": round(float(r.conf_int().loc[var, 1]) * 10, 4),
                    "p": float(r.pvalues[var]), "n": f["n"],
                })
    return pd.DataFrame(rows)


def run_dose_response(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y in OUTCOMES:
        sub = df[df["teeth_q"].notna() & df[y].notna()].copy()
        if sub.empty:
            continue
        for q in sorted(sub["teeth_q"].dropna().unique())[1:]:      # 以 Q1(=牙最多) 为参照
            sub["d"] = (sub["teeth_q"] == q).astype(float).where(sub["teeth_q"].notna())
            cols = ["d"] + [c for c in COVS if c in df.columns]
            f = fit(sub[y], sub[cols])
            if f is None:
                continue
            rows.append(row(f"Teeth quintile Q{int(q)} vs Q1", "d", f, y))
        # 趋势检验：把五分位当连续
        sub["q_num"] = sub["teeth_q"].astype(float)
        cols = ["q_num"] + [c for c in COVS if c in df.columns]
        f = fit(sub[y], sub[cols])
        if f is not None:
            rows.append(row("Teeth quintile trend", "q_num", f, y))
    return pd.DataFrame(rows)


def run_weighted(df: pd.DataFrame) -> pd.DataFrame:
    """WLS：WTMEC2YR；G/H 各 2 年周期，合并时各乘 1/2（NHANES 合并周期惯例）。"""
    d = df.copy()
    d["w"] = d["wt_mec"] / 2.0
    rows = []
    for label, var in [("Perio (mPD)", "mPD"), ("Teeth lost (per tooth)", "nTeeth"),
                       ("Edentulism", "edent")]:
        if var not in d.columns:
            continue
        for y in OUTCOMES:
            sub = d[d[var].notna() & d[y].notna()]
            cols = [var] + [c for c in COVS if c in d.columns]
            f = fit(sub[y], sub[cols], w=sub["w"])
            if f is None:
                continue
            rows.append(row(label + " [weighted]", var, f, y))
    return pd.DataFrame(rows)


def run_sensitivity(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # (a) 仅 H 周期
    for y in OUTCOMES:
        for label, var in [("Perio (mPD)", "mPD"), ("Teeth lost (per tooth)", "nTeeth")]:
            sub = df[(df["cycle"] == "H") & df[var].notna() & df[y].notna()]
            cols = [var] + [c for c in COVS if c in df.columns and c != "cycle_h"]
            f = fit(sub[y], sub[cols])
            if f is not None:
                rows.append(row(label + " [H only]", var, f, y))
    # (b) 不用 cycle 哑变量
    for y in OUTCOMES:
        for label, var in [("Perio (mPD)", "mPD"), ("Teeth lost (per tooth)", "nTeeth")]:
            sub = df[df[var].notna() & df[y].notna()]
            cols = [var] + [c for c in COVS if c in df.columns and c != "cycle_h"]
            f = fit(sub[y], sub[cols])
            if f is not None:
                rows.append(row(label + " [no cycle adj]", var, f, y))
    # (c) 排除无牙颌
    d2 = df[df["edent"] != 1]
    for y in OUTCOMES:
        sub = d2[d2["nTeeth"].notna() & d2[y].notna()]
        cols = ["nTeeth"] + [c for c in COVS if c in df.columns]
        f = fit(sub[y], sub[cols])
        if f is not None:
            rows.append(row("Teeth lost [dentate only]", "nTeeth", f, y))
    # (d) 年龄分层
    for band, lo, hi in [("50-64", 50, 64), ("65-74", 65, 74), ("75+", 75, 200)]:
        for y in OUTCOMES:
            sub = df[(df["age"] >= lo) & (df["age"] <= hi)
                     & df["mPD"].notna() & df[y].notna()]
            cols = ["mPD"] + [c for c in COVS if c in df.columns]
            f = fit(sub[y], sub[cols])
            if f is not None:
                rows.append(row(f"Perio (mPD) [{band}]", "mPD", f, y))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 主流程
def main() -> int:
    log("=" * 64)
    log("step21_nhanes_analysis.py — NHANES 牙周/牙列 -> 炎症 分析")
    log("=" * 64)

    df = build_frame()
    log(f"\n50+ 全体: {len(df):,}")
    log(f"  有 mPD: {df['mPD'].notna().sum():,}")
    log(f"  有 nTeeth: {df['nTeeth'].notna().sum():,}")
    log(f"  有 mPD+nTeeth+WBC: "
        f"{(df['mPD'].notna() & df['nTeeth'].notna() & df['WBC'].notna()).sum():,}")

    t1 = run_main(df)
    t2 = run_dose_response(df)
    t3 = run_weighted(df)
    t4 = run_sensitivity(df)

    t1.to_csv(TAB / "nhanes_main_models.csv", index=False, encoding="utf-8-sig")
    t2.to_csv(TAB / "nhanes_dose_response.csv", index=False, encoding="utf-8-sig")
    t3.to_csv(TAB / "nhanes_weighted.csv", index=False, encoding="utf-8-sig")
    t4.to_csv(TAB / "nhanes_sensitivity.csv", index=False, encoding="utf-8-sig")

    log("\n" + "-" * 64)
    log("【主模型】")
    if not t1.empty:
        for _, r in t1.iterrows():
            star = "***" if r["p"] < .001 else "**" if r["p"] < .01 else "*" if r["p"] < .05 else "ns"
            log(f"  {r['outcome']:4s} ~ {r['model']:26s} beta={r['beta']:+.4f} "
                f"({r['ci_low']:+.3f}, {r['ci_high']:+.3f}) p={r['p']:.2e} {star} n={r['n']:,}")

    log("\n【剂量-反应】")
    if not t2.empty:
        for _, r in t2.iterrows():
            if r["term"] == "q_num":
                star = "***" if r["p"] < .001 else "**" if r["p"] < .01 else "*" if r["p"] < .05 else "ns"
                log(f"  趋势 {r['outcome']:4s}: beta={r['beta']:+.4f} p={r['p']:.2e} {star} n={r['n']:,}")

    log("\n【加权】")
    if not t3.empty:
        for _, r in t3.iterrows():
            star = "***" if r["p"] < .001 else "**" if r["p"] < .01 else "*" if r["p"] < .05 else "ns"
            log(f"  {r['outcome']:4s} ~ {r['model']:34s} beta={r['beta']:+.4f} "
                f"p={r['p']:.2e} {star} n={r['n']:,}")

    (TAB / "nhanes_analysis_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    log(f"\n日志: {TAB / 'nhanes_analysis_log.txt'}")
    log(f"表: nhanes_main_models({len(t1)}) dose_response({len(t2)}) "
        f"weighted({len(t3)}) sensitivity({len(t4)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
