# -*- coding: utf-8 -*-
"""Generate Aging Cell Supporting Information (Tables S1-S6) as Markdown.

Sources: output/tables/*.csv + bioage_sensitivity_summary.md (all real-data results).
"""
import pandas as pd, os, re, json

T = "output/tables"
OUT = "output/manuscript/submission_agingcell/supporting_information.md"
os.makedirs(os.path.dirname(OUT), exist_ok=True)


def ci(df):
    """Render 'beta (lo to hi)'. Falls back to beta +/- 1.96*se when lo/hi absent."""
    if "lo" in df.columns and "hi" in df.columns:
        return df.apply(lambda r: f"{r['beta']:.2f} ({r['lo']:.2f} to {r['hi']:.2f})", axis=1)
    return df.apply(
        lambda r: f"{r['beta']:.2f} ({r['beta'] - 1.96 * r['se']:.2f} to {r['beta'] + 1.96 * r['se']:.2f})",
        axis=1,
    )


def pfmt(p):
    if pd.isna(p):
        return "—"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def signed(x, d=2):
    return f"{x:+.{d}f}"


COVS = {
    "age_c": "Age",
    "female": "Sex",
    "edu_years": "Education",
    "married": "Marital status",
    "rural": "Residence",
    "ever_smoke": "Smoking",
}


def covs_en(cs):
    cs = str(cs)
    if cs in ("nan", "", "—"):
        return "None"
    return ", ".join(COVS.get(x, x) for x in cs.split("+"))


# Chinese subgroup labels -> English (journal is English-language)
SG = {
    "年龄 50–64": "Age 50–64",
    "年龄 65–74": "Age 65–74",
    "年龄 ≥75": "Age ≥75",
    "男性": "Men",
    "女性": "Women",
    "教育 ≤6 年": "Education ≤6 years",
    "教育 >6 年": "Education >6 years",
    "农村": "Rural residence",
    "城市": "Urban residence",
    "从不吸烟": "Never smoker",
    "曾吸烟": "Ever smoker",
    "随访 ≥中位": "Follow-up ≥ median",
    "随访 <中位": "Follow-up < median",
}

L = []
L.append("# Supporting Information\n")
L.append("**Tooth loss and accelerated biological ageing in later life: "
         "a cross-national comparison of three ageing cohorts**\n")
L.append("*Churen Zhang, Yangping Han, Zijian Liu, Wenxia Huang*\n")
L.append("---\n")
L.append("Biological age acceleration is expressed as the residual from a regression of "
         "Klemera–Doubal biological age on chronological age, in years. Positive values "
         "indicate faster biological ageing than expected for a given chronological age. "
         "All models use heteroskedasticity-robust (HC1) standard errors. Unless stated "
         "otherwise, the analytic sample is restricted to blood samples drawn 1–12 years "
         "after the exposure wave.\n")

# ---------------------------------------------------------------- Table S1
L.append("## Table S1. Covariate adjustment ladder\n")
L.append("*Biological age acceleration (years) associated with edentulism across four nested "
         "adjustment sets, fitted separately within each cohort. Area of residence was not "
         "recorded in ELSA; that cohort accordingly adjusted for five covariates in the fully "
         "adjusted set rather than six.*\n")
L.append("| Adjustment set | Cohort | β (95% CI), years | p | n | Covariates |")
L.append("|---|---|---|---|---:|---|")
d = pd.read_csv(f"{T}/bioage_sensitivity_covariates.csv")
print("S1 steps:", sorted(d["step"].unique()))
STEP_ORDER = ["粗模型（未调整）", "+ 实龄", "+ 实龄 性别 教育", "+ 婚姻 城乡 吸烟"]
for st in STEP_ORDER:
    sub = d[d["step"] == st]
    if not len(sub):
        continue
    if st == "粗模型（未调整）":
        lab = "Unadjusted"
    elif st == "+ 实龄":
        lab = "Adjusted for age"
    elif st == "+ 实龄 性别 教育":
        lab = "Adjusted for age, sex and education"
    else:
        lab = "Fully adjusted"
    for _, r in sub.iterrows():
        # fit_one() now writes back the ACTUAL fitted covariate set (`covs`),
        # which already excludes residence for ELSA. Use it directly; the requested
        # set is retained in `covs_requested` for audit only.
        cs = str(r["covs"])
        fitted = [] if cs in ("nan", "", "—") else cs.split("+")
        L.append(f"| {lab} | {r['cohort']} | {signed(r['beta'])} ({r['lo']:.2f} to {r['hi']:.2f}) | "
                 f"{pfmt(r['p'])} | {int(r['n']):,} | {covs_en('+'.join(fitted))} |")
L.append("")

# ---------------------------------------------------------------- Table S2
L.append("## Table S2. Sensitivity to the exposure–blood sample interval\n")
L.append("*A: primary window (blood drawn 1–12 years after the exposure wave). B: excluding the "
         "first two years (3–12). C: long-lag window (6–12). D: exposure measured in the same "
         "wave as the blood sample. Med. Δ is the median interval between the exposure wave and "
         "the blood sample, in years.*\n")
L.append("| Specification | Cohort | β (95% CI), years | p | n | Med. Δ (years) |")
L.append("|---|---|---|---|---:|---:|")
d = pd.read_csv(f"{T}/bioage_sensitivity_exposure.csv")
print("S2 variants:", sorted(d["variant"].unique()))
V = {}
for v in d["variant"].unique():
    vs = str(v)
    if "A" in vs:
        V[vs] = "A. Primary (1–12)"
    elif "B" in vs:
        V[vs] = "B. Excluding first 2 years (3–12)"
    elif "C" in vs:
        V[vs] = "C. Long lag (6–12)"
    else:
        V[vs] = "D. Concurrent exposure"
for _, r in d.iterrows():
    v = V.get(str(r["variant"]), str(r["variant"]))
    L.append(f"| {v} | {r['cohort']} | {signed(r['beta'])} ({r['lo']:.2f} to {r['hi']:.2f}) | "
             f"{pfmt(r['p'])} | {int(r['n']):,} | {r['med_delta']:.1f} |")
L.append("")

# ---------------------------------------------------------------- Table S3
L.append("## Table S3. Subgroup analyses\n")
L.append("*Biological age acceleration (years) associated with edentulism within each subgroup. "
         "Subgroups were defined a priori and are reported without correction for multiple "
         "comparisons; they are exploratory. n edentulous is the number of edentulous "
         "participants contributing to each estimate.*\n")
L.append("| Cohort | Subgroup | β (95% CI), years | p | n | n edentulous |")
L.append("|---|---|---|---|---:|---:|")
d = pd.read_csv(f"{T}/bioage_sensitivity_subgroup.csv")
civ = ci(d)
for _, r in d.iterrows():
    sg = SG.get(str(r["subgroup"]), str(r["subgroup"]))
    L.append(f"| {r['cohort']} | {sg} | {signed(r['beta'])} ({r['beta'] - 1.96 * r['se']:.2f} to "
             f"{r['beta'] + 1.96 * r['se']:.2f}) | {pfmt(r['p'])} | {int(r['n']):,} | "
             f"{int(r['n_events']):,} |")
L.append("")

# ---------------------------------------------------------------- Table S4
L.append("## Table S4. Cross-national effect modification\n")
L.append("*Pooled model with a cohort-group indicator (West: HRS and ELSA; China: CHARLS). "
         "`Edentulism` is the within-China effect of edentulism; `West` is the shift in the "
         "intercept for Western cohorts; `Edentulism x West` is the additional effect of "
         "edentulism in Western relative to Chinese cohorts. Two model layers are shown: the "
         "primary model includes all three cohorts and omits area of residence, which is not "
         "recorded in ELSA; the secondary model contrasts HRS with CHARLS and additionally "
         "adjusts for residence. The near-identical interaction estimates indicate that the "
         "primary result does not arise from omitting residence.*\n")
L.append("| Model | Term | β (95% CI), years | p | n | Cohort composition |")
L.append("|---|---|---|---:|---:|---|")
d = pd.read_csv(f"{T}/bioage_sensitivity_interaction.csv")
LAB_M = {
    "三队（HRS+ELSA vs CHARLS）": "Primary: HRS + ELSA vs CHARLS",
    "仅 HRS vs CHARLS": "Secondary: HRS vs CHARLS",
}
LAB_T = {
    "edent_base": "Edentulism (China, CHARLS)",
    "west": "West (HRS, ELSA)",
    "edent_base:west": "Edentulism x West",
}
for _, r in d.iterrows():
    model = LAB_M.get(str(r["model"]), str(r["model"]))
    term = LAB_T.get(str(r["term"]), str(r["term"]))
    comp = str(r.get("n_by_cohort", "")).replace(" | ", "; ")
    L.append(f"| {model} | {term} | {signed(r['beta'])} ({r['lo']:.2f} to {r['hi']:.2f}) | "
             f"{pfmt(r['p'])} | {int(r['n']):,} | {comp} |")
L.append("")

L.append("## Table S5. Random-effects meta-analysis of cohort-specific estimates\n")
L.append("*Cohort-specific fully adjusted estimates pooled by DerSimonian–Laird random effects. "
         "The Western-only pool excludes CHARLS.*\n")
L.append("| Pool | Pooled β (95% CI), years | p | k | I² |")
L.append("|---|---|---:|---:|---:|")
meta = [
    ("All three cohorts", 2.104, -0.399, 4.606, 0.0995, 3, "91.3%"),
    ("Western cohorts only", 3.366, 2.391, 4.340, 0.0000, 2, "0.0%"),
]
for name, b, lo, hi, p, k, i2 in meta:
    L.append(f"| {name} | {signed(b)} ({lo:.2f} to {hi:.2f}) | {pfmt(p)} | {k} | {i2} |")
L.append("")

# ---------------------------------------------------------------- Table S6
L.append("## Table S6. Sampling-weight sensitivity analysis\n")
L.append("*Weighted least squares using each survey's design weights, compared with the unweighted "
         "ordinary least squares estimates used in the main analysis. Both use HC1 standard errors. "
         "n is the number of participants with a non-missing, positive design weight: HRS physical "
         "measurement weight (2016), ELSA core cross-sectional weight (wave 4), and the CHARLS "
         "blood-sample weight (2015).*\n")
L.append("| Cohort | Weighting | β (95% CI), years | p | n | Weight variable |")
L.append("|---|---|---|---|---:|---|")
d = pd.read_csv(f"{T}/bioage_weighted_sensitivity.csv")
print("S6 models:", sorted(d["model"].unique()))
WV = {"HRS": "r13nwtresp", "ELSA": "r4cwtresp", "CHARLS": "Biomarker_weight"}
for _, r in d.iterrows():
    ms = str(r["model"])
    m = "Weighted (WLS)" if ("加权" in ms or "wls" in ms.lower() or "weighted" in ms.lower()) else "Unweighted (OLS)"
    if "未" in ms:
        m = "Unweighted (OLS)"
    L.append(f"| {r['cohort']} | {m} | {signed(r['beta'])} ({r['lo']:.2f} to {r['hi']:.2f}) | "
             f"{pfmt(r['p'])} | {int(r['n']):,} | {WV.get(r['cohort'], '—')} |")
L.append("")

# ---------------------------------------------------------------- Table S7
L.append("## Table S7. Sample selection flow by cohort\n")
L.append("*Sequential, cohort-specific exclusions from the baseline interview wave to the analytic "
         "sample. The final analytic sample matches that used in the main models.*\n")
sf = pd.read_csv(f"{T}/sample_flow_tri_cohort.csv").set_index("cohort")
LAB = {
    "S1_baseline_rows": "Baseline records available",
    "S1_baseline_ids": "Unique baseline participants",
    "S2_with_exposure": "With tooth-loss exposure",
    "S2_dropped": "Excluded: exposure missing",
    "S3_matched_blood": "With matched blood sample",
    "S3_dropped": "Excluded: no matched blood sample",
    "S4_timing_ok": "Blood drawn 1–12 years after exposure",
    "S4_dropped": "Excluded: interval outside 1–12 years",
    "S5_unique_person": "One record per participant",
    "S5_dropped": "Excluded: duplicate records",
    "S6_outcome_ok": "With complete biological age outcome",
    "S6_dropped": "Excluded: outcome incomplete",
    "S7_covariates_ok": "With complete covariates",
    "S7_dropped": "Excluded: covariates missing",
    "n_analytic": "**Analytic sample**",
    "n_edentulous": "**Edentulous in analytic sample**",
    "n_covariates": "Covariates included",
    "median_delta": "Median exposure–blood interval (years)",
}
L.append("| Step | HRS | ELSA | CHARLS |")
L.append("|---|---:|---:|---:|")
for col in sf.columns:
    label = LAB.get(col, col.replace("_", " "))
    vals = []
    for coh in ["HRS", "ELSA", "CHARLS"]:
        v = sf.loc[coh, col] if coh in sf.index else float("nan")
        if pd.isna(v):
            vals.append("—")
        elif col in ("median_delta",):
            vals.append(f"{float(v):.1f}")
        elif col in ("n_covariates",):
            vals.append(f"{int(v)}")
        else:
            vals.append(f"{int(v):,}")
    L.append(f"| {label} | " + " | ".join(vals) + " |")
L.append("")
# ---------------------------------------------------------------- Table S8
L.append("## Table S8. NHANES extension: main models for periodontal measures and remaining teeth\n")
L.append("*Cross-sectional ordinary least squares with HC1 robust standard errors, adjusted for age, "
         "sex, education, marital status, race and ethnicity (three indicator terms), and survey "
         "cycle. NHANES 2011-2014. Periodontal models use mean probing depth (mPD) or mean clinical "
         "attachment loss (mLA) across examined sites, or a binary indicator for any site with "
         "probing depth >= 4 mm. Dentition models use the number of remaining teeth, expressed per "
         "ten teeth, or a binary edentulism indicator. Outcomes: WBC = white blood cell count "
         "(10^9/L); NLR = neutrophil-to-lymphocyte ratio; ALB = serum albumin (g/L).*\n")
L.append("| Exposure | Outcome | β (95% CI) | p | n |")
L.append("|---|---|---|---|---:|")
_nh = pd.read_csv(f"{T}/nhanes_main_models.csv")
_NH_LAB = {
    "Perio (mPD)": "Mean probing depth (per mm)",
    "Perio (mLA)": "Mean attachment loss (per mm)",
    "Perio any >=4mm": "Any site with PD >= 4 mm (yes/no)",
    "Teeth lost (per tooth)": "Remaining teeth (per tooth)",
    "Teeth lost (per tooth) (per 10 teeth)": "Remaining teeth (per 10 teeth)",
    "Edentulism": "Edentulism (yes/no)",
}
_NH_ORD = ["Perio (mPD)", "Perio (mLA)", "Perio any >=4mm",
           "Teeth lost (per tooth) (per 10 teeth)", "Edentulism"]
for _m in _NH_ORD:
    for _o in ["WBC", "NLR", "ALB"]:
        _r = _nh[(_nh["model"] == _m) & (_nh["outcome"] == _o)]
        if len(_r):
            _rr = _r.iloc[0]
            L.append(f"| {_NH_LAB.get(_m, _m)} | {_o} | "
                     f"{signed(_rr['beta'])} ({_rr['ci_low']:.3f} to {_rr['ci_high']:.3f}) | "
                     f"{pfmt(_rr['p'])} | {int(_rr['n']):,} |")
L.append("")
L.append("*NHANES 2011-2014 releases no C-reactive protein, so the inflammatory outcomes are "
         "white cell count, the neutrophil-to-lymphocyte ratio, and albumin. Exposure and outcomes "
         "are measured at the same examination, so these estimates are cross-sectional.*\n")

# ---------------------------------------------------------------- Table S9
L.append("## Table S9. NHANES extension: dose-response and sensitivity analyses\n")
L.append("**Panel A. Quintiles of remaining teeth versus white cell count (reference: Q1, most teeth)**\n")
L.append("| Contrast | β (95% CI), 10^9/L | p | n |")
L.append("|---|---|---|---:|")
_dr = pd.read_csv(f"{T}/nhanes_dose_response.csv")
for _t in ["d", "q_num"]:
    for _r in _dr[(_dr["outcome"] == "WBC") & (_dr["term"] == _t)].itertuples():
        _lbl = _r.model.replace("Teeth quintile ", "").replace(" vs Q1", " vs Q1")
        if _t == "q_num":
            _lbl = "Linear trend (per quintile)"
        L.append(f"| {_lbl} | {signed(_r.beta, 3)} ({_r.ci_low:.3f} to {_r.ci_high:.3f}) | "
                 f"{pfmt(_r.p)} | {int(_r.n):,} |")
L.append("")
L.append("**Panel B. Sensitivity analyses**\n")
L.append("| Specification | Exposure | Outcome | β (95% CI) | p | n |")
L.append("|---|---|---|---|---|---:|")
_sn = pd.read_csv(f"{T}/nhanes_sensitivity.csv")
for _r in _sn.itertuples():
    L.append(f"| {_r.model} | {_r.term} | {_r.outcome} | "
             f"{signed(_r.beta, 3)} ({_r.ci_low:.3f} to {_r.ci_high:.3f}) | "
             f"{pfmt(_r.p)} | {int(_r.n):,} |")
L.append("")
L.append("**Panel C. Sampling-weighted models (two-cycle examination weight, 2011-2014)**\n")
L.append("| Exposure | Outcome | β (95% CI) | p | n |")
L.append("|---|---|---|---|---:|")
_wt = pd.read_csv(f"{T}/nhanes_weighted.csv")
for _r in _wt.itertuples():
    L.append(f"| {_NH_LAB.get(str(_r.model).replace(' [weighted]', ''), _r.model)} | {_r.outcome} | "
             f"{signed(_r.beta, 3)} ({_r.ci_low:.3f} to {_r.ci_high:.3f}) | "
             f"{pfmt(_r.p)} | {int(_r.n):,} |")
L.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("written:", OUT)
print("lines:", len(L))
