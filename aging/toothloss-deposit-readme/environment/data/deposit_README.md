# Tooth loss and accelerated biological ageing in later life: analysis code and summary results

**Release date:** 2026-10-10
**Version:** 1.0.0

This archive contains the analysis code and summary output tables for a cross-national
study of tooth loss (edentulism) and biological age acceleration in three ageing cohorts
(HRS, ELSA, CHARLS), together with an independent cross-sectional extension in NHANES.

The archive contains **code and derived summary results only**. It does **not** contain
the underlying cohort microdata, which remain governed by the data-access terms of each
original study.

---

## 1. What is included

| Folder | Contents |
|---|---|
| `code/` | Python analysis pipeline (see section 3) |
| `data/` | Derived variable dictionary, NHANES analysis extract, and data-availability notes |
| `results/` | Summary result tables (main models, sensitivity analyses, mechanism layer) |

## 2. What is NOT included

- Original cohort microdata (HRS, ELSA, CHARLS, NHANES raw files). These are obtained
  from each study's own access portal and must not be redistributed.
- The `harmonized_biomarkers.csv` long table derived from those microdata. It can be
  regenerated locally from the original files using the `build_*_biomarkers.py` scripts.

## 3. Pipeline overview

The pipeline runs in the following order. All scripts use a single interpreter with
`pandas`, `numpy`, `scipy`, `statsmodels` and `matplotlib`; no R is required.

### 3.1 Shared configuration

| Script | Role |
|---|---|
| `config.py` | Paths, cohort profiles, variable dictionaries, model formulas |
| `config_biomarker.py` | Blood-marker mappings, unit conversions, KDM and PhenoAge definitions |
| `model_utils.py` | Shared model helpers |

### 3.2 Blood-marker harmonisation (one script per cohort)

| Script | Input | Output |
|---|---|---|
| `build_hrs_biomarkers.py` | Local HRS 2016 VBS files | Appends HRS rows to `harmonized_biomarkers.csv` |
| `build_elsa_biomarkers.py` | ELSA wave 4 nurse data | Appends ELSA rows |
| `build_charls_biomarkers.py` | CHARLS 2011 and 2015 blood files | Appends CHARLS rows |

Each builder is idempotent: it removes and rebuilds only its own cohort's rows.

### 3.3 Biological age and the main analysis

| Script | Role |
|---|---|
| `step11_biologicage.py` | Computes Klemera-Doubal and PhenoAge biological age; derives acceleration |
| `step12_bioage_outcome.py` | Main analysis: edentulism as exposure, acceleration as outcome (OLS with HC3 standard errors, meta-analysis, E-value, mediation) |
| `step4_meta.py` | DerSimonian-Laird random-effects pooling, imported by the analysis scripts |
| `step10_mediation.py` | Mediation helpers shared with the above |

### 3.4 Sensitivity, tables and figures

| Script | Role |
|---|---|
| `step13_sensitivity.py` | Covariate ladder, timing windows, exposure definitions, subgroups, region interaction |
| `step14_figures_cn_west.py` | Covariate-ladder figure and the China-versus-West mechanism figure |
| `step15_table1.py` | Table 1 for the analysis sample |
| `step16_tri_cohort_extras.py` | Sample flow, sampling weights, dose-response availability |
| `step17_figure1_tri_cohort.py` | Three-column sample-flow figure (Figure 1) |

### 3.5 Independent extension in NHANES

| Script | Role |
|---|---|
| `step20_nhanes_extract.py` | Downloads and harmonises NHANES 2011-2014 oral examination, periodontal and inflammation files |
| `step21_nhanes_analysis.py` | Cross-sectional association of periodontal severity and tooth count with inflammation markers |
| `step22_nhanes_figure.py` | Supplementary figure for the NHANES extension |

### 3.6 Manuscript support

| Script | Role |
|---|---|
| `build_agingcell_si.py` | Builds supporting-information tables from the result files |
| `build_figure2_agingcell.py` | Rebuilds the meta-analysis forest plot with the final estimates |
| `check_manuscript_numbers.py` | Recomputes every number quoted in the manuscript and compares against the text |
| `selftest_biomarker.py` | Self-test of the biological-age and mediation estimators against simulated ground truth |

## 4. How to reproduce

1. Obtain the original cohort files under their own access agreements and place them in
   a local `data/raw/<cohort>/` directory.
2. Run the biomarker builders in sequence:
   `build_hrs_biomarkers.py`, `build_elsa_biomarkers.py`, `build_charls_biomarkers.py`.
3. Run `step11_biologicage.py`, then `step12_bioage_outcome.py`.
4. Run the sensitivity and figure scripts (`step13` through `step17`).
5. For the NHANES extension, run `step20`, `step21` and `step22`.
6. Verify internal consistency with `check_manuscript_numbers.py`.

## 5. Key data-availability notes

- **Continuous remaining-tooth count** is not available in HRS, ELSA or CHARLS, which
  record tooth loss as a binary indicator. Only a binary edentulism exposure enters the
  main analysis. See `data/tooth_count_availability.md`.
- **Sampling weights** are available with incomplete coverage in all three cohorts.
  See `data/weights_coverage.md` for the exact variables, waves and coverage rates.
- **NHANES 2011-2014** has no publicly released C-reactive protein file, so the NHANES
  extension uses white cell count, neutrophil-to-lymphocyte ratio and albumin.
- **Biological age** is estimated with the Klemera-Doubal method, which does not require
  external coefficients and is invariant to linear rescaling of each marker.

## 6. Software

Python 3.13 with numpy, pandas, scipy, statsmodels and matplotlib. The analysis was run
on a single CPU. No R dependency.

## 7. Citation

If you use this code or these results, please cite the associated article (citation to be
added on publication).

## 8. License

Code is released under the MIT License (see `LICENSE`). Summary result tables and derived
documentation are released under CC BY 4.0.
