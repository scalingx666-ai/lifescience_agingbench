# -*- coding: utf-8 -*-
"""step15_table1.py —— 第二篇（缺牙 → 生物衰老加速）的三队列基线特征表。

与 `table1_baseline.md`（全样本长表版，五队列）不同，本表对应**第二篇的分析框**：
  - 仅 HRS / ELSA / CHARLS
  - 已施加时序筛选（血样滞后 1–12 年，取最早合格波）
  - 按基线无牙颌分组（有牙 vs 无牙颌）
  - 额外报告炎症标志物与生物年龄加速

输出：output/tables/table1_bioage_analysis.md
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
warnings.filterwarnings("ignore")

from config import OUT_TAB  # noqa: E402
from step13_sensitivity import load_frames  # noqa: E402
from step14_figures_cn_west import _mechanism_frame  # noqa: E402

PRIMARY_METRIC = "bioage_accel_clean"


def _fmt_cont(s: pd.Series) -> str:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return "—"
    return "%.1f (%.1f)" % (s.mean(), s.std())


def _fmt_cat(s: pd.Series) -> str:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return "—"
    return "%d (%.1f%%)" % (int(s.sum()), s.mean() * 100)


def _pval_cont(a: pd.Series, b: pd.Series) -> str:
    from scipy import stats
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 3 or len(b) < 3:
        return ""
    try:
        _, p = stats.ttest_ind(a, b, equal_var=False, nan_policy="omit")
    except Exception:
        return ""
    return _star(p)


def _pval_cat(a: pd.Series, b: pd.Series) -> str:
    from scipy import stats
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 3 or len(b) < 3:
        return ""
    tab = np.array([[a.sum(), len(a) - a.sum()], [b.sum(), len(b) - b.sum()]])
    if tab.min() < 0 or (tab.sum(axis=0) == 0).any():
        return ""
    try:
        _, p, _, _ = stats.chi2_contingency(tab)
    except Exception:
        return ""
    return _star(p)


def _star(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


CONT_VARS = [
    ("Age, years",              "age"),
    ("Education, years",        "edu_years"),
    ("Follow-up, years",        "blood_delta"),
    ("CRP, mg/L (median)",      "crp_med"),
    ("WBC, 10^9/L",             "wbc"),
    ("Biological age accel, yrs", PRIMARY_METRIC),
]
CAT_VARS = [
    ("Female",       "female"),
    ("Married",      "married"),
    ("Rural",        "rural"),
    ("Ever smoker",  "ever_smoke"),
]


def build_table1(m: pd.DataFrame) -> str:
    L = []
    W = L.append
    W("# Table 1. Baseline characteristics by edentulism status (third-cohort analysis sample)")
    W("")
    W("*Continuous variables: mean (SD), except CRP given as median due to skewness. "
      "Categorical: n (%). Comparisons use Welch t-test (continuous) and chi-square (categorical).*")
    W("*Asterisks: \\* p<0.05, \\*\\* p<0.01, \\*\\*\\* p<0.001.*")
    W("*Rural residence is available in HRS and CHARLS but not collected in ELSA; "
      "the ELSA column therefore reports no rural comparison.*")
    W("")

    hdr_cells = ["Characteristic"]
    for c in ["HRS", "ELSA", "CHARLS"]:
        hdr_cells += ["%s<br>dentate" % c, "%s<br>edentulous" % c, "p"]
    W("| " + " | ".join(hdr_cells) + " |")
    W("|" + "---|" * len(hdr_cells))
    W("")

    for label, var in CONT_VARS:
        cells = []
        for coh in ["HRS", "ELSA", "CHARLS"]:
            s = m[m.cohort == coh]
            if var == "crp_med":
                a = s[s.edent_base == 0]["crp"].dropna()
                b = s[s.edent_base == 1]["crp"].dropna()
                aa = "%.2f" % a.median() if len(a) else "—"
                bb = "%.2f" % b.median() if len(b) else "—"
                # 中位数用 Mann-Whitney U
                from scipy import stats
                try:
                    _, pu = stats.mannwhitneyu(a, b, alternative="two-sided")
                    pv = _star(pu)
                except Exception:
                    pv = ""
                cells += [aa, bb, pv]
            elif var not in s.columns:
                cells += ["—", "—", ""]
            else:
                a = s[s.edent_base == 0][var]
                b = s[s.edent_base == 1][var]
                cells += [_fmt_cont(a), _fmt_cont(b), _pval_cont(a, b)]
        W("| %s | %s" % (label, " | ".join(cells) + " |"))

    for label, var in CAT_VARS:
        cells = []
        for coh in ["HRS", "ELSA", "CHARLS"]:
            s = m[m.cohort == coh]
            if var not in s.columns or s[var].notna().sum() == 0:
                cells += ["—", "—", ""]
                continue
            a = s[s.edent_base == 0][var]
            b = s[s.edent_base == 1][var]
            cells += [_fmt_cat(a), _fmt_cat(b), _pval_cat(a, b)]
        W("| %s, n (%%)\u00a0 | %s" % (label, " | ".join(cells) + " |"))

    W("| **Total, n** | " + " | ".join(
        "%d | %d | —" % (int(((m.cohort == c) & (m.edent_base == 0)).sum()),
                         int(((m.cohort == c) & (m.edent_base == 1)).sum()))
        for c in ["HRS", "ELSA", "CHARLS"]) + " |")
    W("")
    W("> **Note on biological age acceleration.** Edentulous participants show "
      "significantly higher biological age acceleration in HRS (+3.9 vs −0.5 years) "
      "and ELSA (+3.6 vs −0.5 years), but not in CHARLS (−2.2 vs −2.1 years). "
      "This unadjusted contrast anticipates the formal interaction test reported "
      "in the main text (edentulism × Western cohort = +3.85 years, p<0.001).")
    W("")
    W("## Cohort-level context")
    W("")
    W("| Cohort | Country | Baseline exposure wave | Blood sample wave | Median interval |")
    W("|---|---|---|---|---|")
    ctx = {"HRS": ("United States", "2006", "2016", "10 y"),
           "ELSA": ("England", "2006", "2008/9", "3 y"),
           "CHARLS": ("China", "2011/2013", "2011/2015", "4 y")}
    for c in ["HRS", "ELSA", "CHARLS"]:
        s = m[m.cohort == c]
        country, base, blood, _ = ctx[c]
        W("| %s | %s | %s | %s | %.1f y |" % (c, country, base, blood, s.blood_delta.median()))
    W("")
    return "\n".join(L)


def _model_frame(pf, bm):
    """与 step13 主模型**完全一致**的分析样本：时序筛选 + 充分调整集完整观测。

    早期版本用 `_mechanism_frame`（n=29,016，未剔协变量缺失），
    导致 Table 1 合计与主模型 n 不一致（HRS 11,166 vs 9,526）。
    审稿人会拿这两处对账，必须对齐。
    """
    import step13_sensitivity as s13
    m = s13.build_analysis_frame(pf, bm)
    cov = s13.COV_LADDER[-1][1]
    out = []
    for co in ["HRS", "ELSA", "CHARLS"]:
        d = m[m.cohort == co].dropna(subset=[s13.PRIMARY_METRIC, "edent_base"]).copy()
        use = [c for c in cov if c in d.columns
               and pd.to_numeric(d[c], errors="coerce").notna().any()
               and pd.to_numeric(d[c], errors="coerce").std(skipna=True) > 0]
        if use:
            d = d.dropna(subset=use)
        # 把炎症列并回来（Table 1 要报 CRP/WBC）
        bcols = [c for c in ["crp", "wbc", "il6", "fibrinogen"] if c in bm.columns]
        if "id" in d.columns and "id" in bm.columns:
            keys = [k for k in ["cohort", "id", "blood_year"] if k in d.columns and k in bm.columns]
            d = d.merge(bm[keys + bcols].drop_duplicates(keys), on=keys, how="left")
        out.append(d)
    return pd.concat(out, ignore_index=True)


def main() -> None:
    print("=" * 60)
    print("step15 三队列版 Table 1")
    print("=" * 60)
    pf, bm = load_frames()
    m = _model_frame(pf, bm)
    print("分析框 n=%d（与 step13 主模型一致）" % len(m))
    for c in ["HRS", "ELSA", "CHARLS"]:
        s = m[m.cohort == c]
        print("  %-8s n=%6d  无牙颌=%4d (%.1f%%)" % (c, len(s), int(s.edent_base.sum()),
                                                     s.edent_base.mean() * 100))
    md = build_table1(m)
    p = OUT_TAB / "table1_bioage_analysis.md"
    p.write_text(md, encoding="utf-8")
    print("\n[写入]", p)
    print(md)


if __name__ == "__main__":
    main()
