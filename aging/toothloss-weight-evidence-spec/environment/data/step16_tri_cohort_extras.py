# -*- coding: utf-8 -*-
"""step16_tri_cohort_extras.py —— 第二篇投稿前必补的三件事
================================================================================
用户指令（2026-10-10）：
  ① Figure 1 要**三队列版**样本流程图（现有 fig1 是五队列旧版）
  ② 剂量-反应（牙数）分支要**完善**
  ③ **抽样权重**要纳入
  ④ 作者信息写入稿件（已在 manuscript_v1.md 完成）

本脚本一次产出三块：
  A. 三队列**样本流**（每步排除人数）→ 供 Figure 1 绘制 + 稿件 §3.1
  B. **加权**敏感性分析（设计权重）→ 检验估计是否受抽样设计影响
  C. 剂量-反应**可得性诊断** → 报告哪些队列有真牙数、哪些只有二分无牙颌

⚠️ 纪律
--------
- 所有数字来自真实 harmonized 长表；**无演示模式回退**（若数据缺失即报告缺失）。
- 权重变量逐个从 **Harmonized 官方文件**核实（HRS `rXnwtresp`、ELSA `rXcwtresp`、
  CHARLS `Biomarker_weight`），不做单位/量纲假设。
- 牙数：只有 SHARE 有真「剩余牙数」。HRS/ELSA/CHARLS 官方**均无**连续牙数
  （只有二分「是否全口失牙」）→ 剂量-反应**不可能**在这三队列做真实估计，
  本脚本给出可核查的证据链，而不是编造。

输出
----
  output/tables/sample_flow_tri_cohort.csv       每队列每步 n
  output/tables/sample_flow_tri_cohort.md        可读版（含排除原因）
  output/tables/tooth_count_availability.md      剂量-反应可得性证据链
  output/tables/bioage_weighted_sensitivity.csv  加权 vs 未加权对照
  output/tables/weights_coverage.md              权重覆盖率诊断
运行
----
    python step16_tri_cohort_extras.py
"""
from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
warnings.filterwarnings("ignore")

from config import DATA_HARM, OUT_TAB, DATA_RAW          # noqa: E402
import step13_sensitivity as s13                        # noqa: E402
from config_biomarker import POST_EXPOSURE_WINDOW       # noqa: E402

COHORTS = ["HRS", "ELSA", "CHARLS"]
BIOMARKER = DATA_HARM / "harmonized_biomarkers.csv"


# ============================================================ A. 三队列样本流
def build_sample_flow(pf: pd.DataFrame, bm: pd.DataFrame) -> pd.DataFrame:
    """逐队列、逐步统计样本量（每一步的剩余 n 与排除 n）。

    步骤链（与 step13.build_analysis_frame 完全对齐）：
      S1 队列基线访谈记录（有多少人/多少行）
      S2 有基线口腔暴露（edent_base 非缺失）
      S3 与血样表能按 id 匹配上（inner join）
      S4 血样严格晚于暴露（delta ∈ [1, window]）
      S5 同一人多条合格血样 → 取最早一条（去重后的人）
      S6 结局（bioage_accel_clean）非缺失
      S7 充分调整协变量完整（与主模型同框）→ **主分析样本**
    """
    rows = []
    base_cols = ["edent_base", "age", "age_c", "female", "edu_years",
                 "married", "rural", "ever_smoke", "year"]
    bio_cols = ["cohort", "id", "wave", "year", "bioage_accel_clean"]

    for coh in COHORTS:
        p = pf[pf.cohort == coh].copy()
        b = bm[bm.cohort == coh].copy()

        s1_rows, s1_ids = len(p), p["id"].nunique()

        # S2 有基线暴露
        e = p.dropna(subset=["edent_base"]).sort_values(["cohort", "id", "year"])
        e = e.drop_duplicates(["cohort", "id"], keep="first")
        e = e[["cohort", "id"] + [c for c in base_cols if c in e.columns]]
        e = e.rename(columns={"year": "year_base"})
        s2_ids = e["id"].nunique()

        # S3 匹配血样
        bb = b[[c for c in bio_cols if c in b.columns]].copy()
        m = bb.merge(e, on=["cohort", "id"], how="inner")
        s3_ids = m["id"].nunique()

        # S4 时序
        m["blood_delta"] = m["year_x"] if "year_x" in m.columns else np.nan
        # 列名冲突处理：merge 后 year 来自 bm 与 e 各一
        ycols = [c for c in m.columns if c.startswith("year")]
        if len(ycols) >= 2:
            m["blood_delta"] = m[ycols[0]] - m["year_base"]
        ok = m["blood_delta"].between(1, POST_EXPOSURE_WINDOW)
        m4 = m[ok].copy()
        s4_ids = m4["id"].nunique()

        # S5 去重（取最早血样 = 最小 delta）
        m5 = m4.sort_values(["cohort", "id", "blood_delta"]).drop_duplicates(["cohort", "id"], keep="first")
        s5_ids = m5["id"].nunique()

        # S6 结局非缺失
        m6 = m5.dropna(subset=["bioage_accel_clean"])
        s6_ids = m6["id"].nunique()

        # S7 协变量完整（与主模型同框）
        covs = [c for c in ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
                if c in m6.columns]
        use = [c for c in covs
               if pd.to_numeric(m6[c], errors="coerce").notna().any()
               and pd.to_numeric(m6[c], errors="coerce").std(skipna=True) > 0]
        m7 = m6.dropna(subset=use) if use else m6
        s7_ids = m7["id"].nunique()

        n_edent = int(pd.to_numeric(m7["edent_base"], errors="coerce").fillna(0).sum())

        rows.append(dict(
            cohort=coh,
            S1_baseline_rows=s1_rows, S1_baseline_ids=s1_ids,
            S2_with_exposure=s2_ids, S2_dropped=s1_ids - s2_ids,
            S3_matched_blood=s3_ids, S3_dropped=s2_ids - s3_ids,
            S4_timing_ok=s4_ids, S4_dropped=s3_ids - s4_ids,
            S5_unique_person=s5_ids, S5_dropped=s4_ids - s5_ids,
            S6_outcome_ok=s6_ids, S6_dropped=s5_ids - s6_ids,
            S7_covariates_ok=s7_ids, S7_dropped=s6_ids - s7_ids,
            n_analytic=s7_ids, n_edentulous=n_edent,
            n_covariates=len(use),
            median_delta=float(m7["blood_delta"].median()) if len(m7) else np.nan,
        ))
    return pd.DataFrame(rows)


def flow_markdown(flow: pd.DataFrame) -> str:
    L, W = [], None
    W = L.append
    W("# 三队列样本流（Figure 1 数据源）")
    W("")
    W("> 生成：`step16_tri_cohort_extras.py`｜与 `step13.build_analysis_frame()` 逐步对齐")
    W("")
    W("| 步骤 | HRS | ELSA | CHARLS |")
    W("|---|---:|---:|---:|")
    label_map = [
        ("S1 队列基线访谈（人）", "S1_baseline_ids"),
        ("S2 有基线口腔暴露", "S2_with_exposure"),
        ("S2 排除（无暴露）", "S2_dropped"),
        ("S3 匹配到血样", "S3_matched_blood"),
        ("S3 排除（无血样）", "S3_dropped"),
        ("S4 时序合格（1≤Δ≤12）", "S4_timing_ok"),
        ("S4 排除（同期/超窗）", "S4_dropped"),
        ("S5 每人取最早血样", "S5_unique_person"),
        ("S5 排除（重复波）", "S5_dropped"),
        ("S6 结局非缺失", "S6_outcome_ok"),
        ("S6 排除（缺 accel）", "S6_dropped"),
        ("**S7 协变量完整＝主分析样本**", "S7_covariates_ok"),
        ("S7 排除（协变量缺失）", "S7_dropped"),
        ("其中无牙颌 n", "n_edentulous"),
        ("调整协变量个数", "n_covariates"),
        ("血样滞后中位（年）", "median_delta"),
    ]
    for lab, key in label_map:
        vals = []
        for c in COHORTS:
            v = flow.loc[flow.cohort == c, key]
            v = v.iloc[0] if len(v) else np.nan
            if pd.isna(v):
                vals.append("—")
            elif key in ("median_delta",):
                vals.append(f"{v:.0f}")
            elif key == "n_covariates":
                vals.append(f"{int(v)}")
            else:
                vals.append(f"{int(v):,}")
        W(f"| {lab} | " + " | ".join(vals) + " |")
    W("")
    W("**各步排除原因**")
    W("")
    W("- **S2**：基线访谈未测口腔变量（ELSA 仅 W3/W5 测过，故排除最多）。")
    W("- **S3**：无可用血样（HRS VBS 子样本、ELSA W4 护士访视、CHARLS W1/W3 血样）。")
    W("- **S4**：血样与暴露同期（Δ=0，无法排除反向因果）或超出 12 年窗口。")
    W("- **S5**：同一人多波合格血样，保留最早一波（keep='first'）。")
    W("- **S6**：KDM 去污染版需要 ≥4 项非炎症标志物，不足者无法算 accel。")
    W("- **S7**：充分调整集（age_c/female/edu_years/married/[rural]/ever_smoke）完整。")
    W("  ⚠️ ELSA 无 `rural` → 实调 %d 项，其余两队列 6 项。" %
      int(flow.loc[flow.cohort == "ELSA", "n_covariates"].iloc[0]) if len(flow) else "")
    return "\n".join(L)


# ============================================================ B. 抽样权重
# 权重变量来源（逐条从 Harmonized 官方文件核实，2026-10-10）
WEIGHT_SPEC = {
    # HRS：Harmonized HRS `rXnwtresp` = 物理测量样本权重（VBS 体检子样本口径）
    #      W13 = 2016 年（VBS 年）。同时保留 r13scwtresp（留卷样本）做对照。
    "HRS":    dict(file="hrs", var="r13nwtresp", alt="r13scwtresp",
                   label="w13 物理测量样本权重（2016）",
                   src="Gateway Harmonized HRS `H_HRS_d.dta`"),
    # ELSA：Harmonized ELSA `rXcwtresp` = 核心样本横断面权重。W4 = 2008/9（血样年）。
    "ELSA":   dict(file="elsa", var="r4cwtresp", alt="s4cwtresp",
                   label="w4 核心样本横截面权重（2008/9）",
                   src="Harmonized ELSA `h_elsa_g3.dta`"),
    # CHARLS：官方 Weights.dta 的 `Biomarker_weight`（血样权重，含无应答调整）
    #         —— 与本研究「用血样结局」的抽样设计最匹配。
    "CHARLS": dict(file="charls", var="Biomarker_weight", alt="INDV_weight_ad2",
                   label="血样权重（含家户+个体无应答调整，2015）",
                   src="CHARLS 2015 `Weights.dta`"),
}


def _find(path_root: Path, *patterns) -> Path | None:
    for pat in patterns:
        hits = list(path_root.rglob(pat))
        if hits:
            return hits[0]
    return None


def load_weights() -> tuple[pd.DataFrame, dict]:
    """返回 (cohort,id,weight 的后缀/口径长表, 诊断字典)。

    ⚠️ id 口径必须与 harmonized 表一致：
       HRS = HHID+PN（PN 3 位）；ELSA = str(idauniq)；CHARLS = 去前导零后的 ID。
       若口径不符 → 命中率会异常低，脚本会在诊断里显式报警。
    """
    frames, diag = [], {}
    root23 = DATA_RAW / "23. 七大老年健康数据" / "七大老年健康数据库合集 CHARLS" / "七大老年健康数据库数据 离线"

    # ---- HRS ----
    try:
        p = _find(root23, "H_HRS_d.dta")
        d = pd.read_stata(p, columns=["hhidpn", WEIGHT_SPEC["HRS"]["var"],
                                      WEIGHT_SPEC["HRS"]["alt"]])
        d = d.rename(columns={WEIGHT_SPEC["HRS"]["var"]: "weight",
                              WEIGHT_SPEC["HRS"]["alt"]: "weight_alt"})
        d["id"] = d["hhidpn"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        # Harmonized HRS 的 hhidpn 已是 HHID+PN 拼好的字符串（PN 3 位）→ 直接与长表对齐
        d["cohort"] = "HRS"
        d = d[["cohort", "id", "weight", "weight_alt"]]
        frames.append(d)
        diag["HRS"] = dict(n=len(d), n_w=pd.to_numeric(d["weight"], errors="coerce").gt(0).sum(),
                           file=str(p.name))
    except Exception as e:
        diag["HRS"] = dict(error=str(e))

    # ---- ELSA ----
    try:
        p = _find(root23, "h_elsa_g3.dta")
        it = pd.read_stata(p, iterator=True)
        vl = it.variable_labels()
        idcol = next((c for c in ["idauniq", "idauniq90", "idauniq00"] if c in vl), None)
        keep = [idcol, WEIGHT_SPEC["ELSA"]["var"], WEIGHT_SPEC["ELSA"]["alt"]]
        d = pd.read_stata(p, columns=keep)
        d = d.rename(columns={WEIGHT_SPEC["ELSA"]["var"]: "weight",
                              WEIGHT_SPEC["ELSA"]["alt"]: "weight_alt"})
        d["id"] = d[idcol].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        d["cohort"] = "ELSA"
        d = d[["cohort", "id", "weight", "weight_alt"]]
        frames.append(d)
        diag["ELSA"] = dict(n=len(d), n_w=pd.to_numeric(d["weight"], errors="coerce").gt(0).sum(),
                            file=str(p.name), idcol=idcol)
    except Exception as e:
        diag["ELSA"] = dict(error=str(e))

    # ---- CHARLS ----
    try:
        p = _find(root23 / "1. CHARLS  中国", "Weights.dta")
        if p is None:
            p = _find(DATA_RAW, "Weights.dta")
        d = pd.read_stata(p, columns=["ID", WEIGHT_SPEC["CHARLS"]["var"],
                                      WEIGHT_SPEC["CHARLS"]["alt"]])
        d = d.rename(columns={WEIGHT_SPEC["CHARLS"]["var"]: "weight",
                              WEIGHT_SPEC["CHARLS"]["alt"]: "weight_alt"})
        raw = d["ID"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        # CHARLS 2015 口径：去前导零
        d["id"] = raw.str.lstrip("0")
        d["cohort"] = "CHARLS"
        d = d[["cohort", "id", "weight", "weight_alt"]]
        d = d.drop_duplicates(["cohort", "id"], keep="first")
        frames.append(d)
        diag["CHARLS"] = dict(n=len(d), n_w=pd.to_numeric(d["weight"], errors="coerce").gt(0).sum(),
                              file=str(p.name))
    except Exception as e:
        diag["CHARLS"] = dict(error=str(e))

    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), diag


def weighted_sensitivity(m: pd.DataFrame, wts: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """对每个队列做 WLS（aweight=1/w² 的等价实现：statsmodels WLS）对照 OLS。"""
    import statsmodels.api as sm
    covs_full = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
    rows, log = [], []
    for coh in COHORTS:
        d = m[m.cohort == coh].copy()
        d = d.merge(wts[wts.cohort == coh][["id", "weight"]], on="id", how="left")
        d = d.dropna(subset=["bioage_accel_clean", "edent_base"])
        covs = [c for c in covs_full if c in d.columns
                and pd.to_numeric(d[c], errors="coerce").notna().any()
                and pd.to_numeric(d[c], errors="coerce").std(skipna=True) > 0]
        d = d.dropna(subset=covs)
        y = pd.to_numeric(d["bioage_accel_clean"], errors="coerce").values.astype(float)
        A = pd.to_numeric(d["edent_base"], errors="coerce").values.astype(float)
        Xc = []
        for c in covs:
            v = pd.to_numeric(d[c], errors="coerce").values.astype(float)
            Xc.append(v - np.nanmean(v))
        X = sm.add_constant(np.column_stack([A] + Xc), has_constant="add")

        # 未加权（基准）
        r0 = sm.OLS(y, X).fit(cov_type="HC1")
        rows.append(dict(cohort=coh, model="未加权 OLS", beta=float(r0.params[1]),
                         se=float(r0.bse[1]), p=float(r0.pvalues[1]),
                         lo=float(r0.conf_int()[1][0]), hi=float(r0.conf_int()[1][1]),
                         n=int(len(y)), w_cov=float(pd.to_numeric(d["weight"], errors="coerce")
                                                    .notna().mean())))

        # 加权（WLS，权重 = 设计权重）
        w = pd.to_numeric(d["weight"], errors="coerce").values.astype(float)
        okw = np.isfinite(w) & (w > 0) & np.isfinite(y) & np.all(np.isfinite(X), axis=1)
        if okw.sum() >= 200:
            rw = sm.WLS(y[okw], X[okw], weights=w[okw]).fit(cov_type="HC1")
            rows.append(dict(cohort=coh, model="设计权重 WLS", beta=float(rw.params[1]),
                             se=float(rw.bse[1]), p=float(rw.pvalues[1]),
                             lo=float(rw.conf_int()[1][0]), hi=float(rw.conf_int()[1][1]),
                             n=int(okw.sum()), w_cov=float(pd.to_numeric(d["weight"],
                                                                          errors="coerce").notna().mean())))
            log.append(f"{coh}: 权重可用 {int(okw.sum()):,} / {len(y):,}")
        else:
            log.append(f"{coh}: ⚠️ 权重命中共 {int(okw.sum())} 人，不足以加权（口径可能不匹配）")
    return pd.DataFrame(rows), "\n".join(log)


# ============================================================ C. 剂量-反应可得性
def tooth_count_availability() -> str:
    """逐队列核实「是否有真·剩余牙数」。给出可复现的证据链。"""
    L, W = [], None
    W = L.append
    W("# 剂量-反应（剩余牙数）可得性诊断")
    W("")
    W("> 生成：`step16_tri_cohort_extras.py`｜**逐队列回原始码本核实**，不做假设")
    W("")
    W("## 结论")
    W("")
    W("**三队列（HRS/ELSA/CHARLS）的官方文件中均无连续「剩余牙数」变量**，")
    W("只有二分「是否全口失牙（edentulism）」。因此**剂量-反应无法在这三队列做真实估计**。")
    W("")
    W("## 证据链")
    W("")
    W("| 队列 | 文件 | 相关变量 | 性质 | 结论 |")
    W("|---|---|---|---|---|")
    W("| HRS | Harmonized HRS `H_HRS_d.dta` | `r8–r15noteeth` | 二分（0=no/1=yes，'lost all their teeth'） | ✗ 仅无牙颌 |")
    W("| HRS | 2016 core `H16C_R.dta` | `PC237` LOST PERMANENT TEETH | **分类档位**（1 / 5 / 8 / 9），5='5 or more'，非计数 | ✗ 非连续 |")
    W("| ELSA | Harmonized ELSA `h_elsa_g3.dta` | `r3/r5noteeth`；`r3/r5/r7dentalh` | 二分 + 自评口腔健康（有序） | ✗ 仅无牙颌/自评 |")
    W("| CHARLS | 2011/2013 Health_Status | `da040` Lost all of Teeth | 二分 | ✗ 仅无牙颌 |")
    W("| SHARE | harmonized 长表 | `remaining_teeth` | **连续 0–28**（实测 n=48,750） | ✓ 唯一可用 |")
    W("")
    W("## 对稿件的处置建议")
    W("")
    W("1. **Methods §2.2** 明确写：exposure 为二分 edentulism，因为三队列官方均无连续牙数；")
    W("   Limitations 已据此说明「无法描述剂量-反应」。")
    W("2. **若审稿人坚持要剂量-反应**，有两条可行路径：")
    W("   - 路径 A（推荐）：把 SHARE 纳入为**第四个队列**。SHARE 已有 `remaining_teeth`，")
    W("     可与已跑通的欧洲队列（ELSA）做「同一大陆内剂量-反应」补充分析，")
    W("     并作为 Supplementary Figure，不改动主结论。")
    W("   - 路径 B：改用**替代暴露**（如「缺牙年数」或「自报咀嚼困难」），")
    W("     但这两个变量跨队列构念不同构（config.py 已注明），可比性差，不推荐。")
    W("3. 现有 `sens_dose_response.csv` 里的 B1–B4 是 **SHARE 的认知轨迹**模型")
    W("   （随机斜率、n=46,575），**不是**本稿的缺牙×生物衰老剂量-反应，")
    W("   不可直接引用。")
    W("")
    W("## SHARE `remaining_teeth` 分布（唯一可用队列）")
    try:
        pf = pd.read_csv(DATA_HARM / "harmonized_long_anchored.csv", low_memory=False)
        s = pd.to_numeric(pf.loc[pf.cohort == "SHARE", "remaining_teeth"], errors="coerce").dropna()
        W("")
        W(f"- n = {len(s):,}")
        W(f"- 中位 {s.median():.0f}｜均值 {s.mean():.1f}｜SD {s.std():.1f}｜范围 {s.min():.0f}–{s.max():.0f}")
        bins = pd.cut(s, [-1, 0, 9, 19, 28], labels=["0（无牙颌）", "1–9", "10–19", "≥20（参照）"])
        vc = bins.value_counts().reindex(["0（无牙颌）", "1–9", "10–19", "≥20（参照）"])
        W("")
        W("| WHO 功能牙列分层 | n | % |")
        W("|---|---:|---:|")
        for k, v in vc.items():
            W(f"| {k} | {int(v):,} | {100*v/len(s):.1f}% |")
    except Exception as e:
        W(f"- ⚠️ 读取 SHARE 牙数失败：{e}")
    return "\n".join(L)


# ============================================================ 主入口
def main() -> None:
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    print("=" * 72)
    print("step16 —— 三队列样本流 / 抽样权重 / 剂量-反应可得性")
    print("=" * 72)

    pf, bm = s13.load_frames()
    m = s13.build_analysis_frame(pf, bm)
    print(f"分析框 n={len(m):,}｜队列 {sorted(m.cohort.unique())}")

    # ---- A 样本流 ----
    print("\n[A] 三队列样本流 ……")
    flow = build_sample_flow(pf, bm)
    flow.to_csv(OUT_TAB / "sample_flow_tri_cohort.csv", index=False, encoding="utf-8-sig")
    (OUT_TAB / "sample_flow_tri_cohort.md").write_text(flow_markdown(flow), encoding="utf-8")
    print(flow[["cohort", "S1_baseline_ids", "S3_matched_blood", "S4_timing_ok",
                "S7_covariates_ok", "n_edentulous"]].to_string(index=False))

    # ---- B 权重 ----
    print("\n[B] 抽样权重 ……")
    wts, wdiag = load_weights()
    print("  载入诊断:")
    for k, v in wdiag.items():
        print(f"    {k}: {v}")
    wtab, wlog = weighted_sensitivity(m, wts)
    wtab.to_csv(OUT_TAB / "bioage_weighted_sensitivity.csv", index=False, encoding="utf-8-sig")
    print("  " + wlog.replace("\n", "\n  "))
    # 覆盖率诊断 md
    L = ["# 抽样权重覆盖率与来源", "",
         "> 生成：`step16_tri_cohort_extras.py`｜逐个从 Harmonized 官方文件核实", "",
         "| 队列 | 权重变量 | 口径 | 来源文件 | 权重>0 人数 |", "|---|---|---|---|---:|"]
    for coh, spec in WEIGHT_SPEC.items():
        d = wdiag.get(coh, {})
        nw = d.get("n_w", "—")
        nw = f"{nw:,}" if isinstance(nw, (int, np.integer)) else nw
        L.append(f"| {coh} | `{spec['var']}` | {spec['label']} | {spec['src']} | {nw} |")
    L += ["", "**命中共线性检查**：加权与未加权估计若差异 <0.3 年，说明抽样设计不改变结论。", ""]
    (OUT_TAB / "weights_coverage.md").write_text("\n".join(L), encoding="utf-8")

    # ---- C 剂量-反应 ----
    print("\n[C] 剂量-反应可得性 ……")
    (OUT_TAB / "tooth_count_availability.md").write_text(tooth_count_availability(), encoding="utf-8")
    print("  → tooth_count_availability.md")

    print("\n✅ 三道产出完成")
    print("   output/tables/sample_flow_tri_cohort.{csv,md}")
    print("   output/tables/weights_coverage.md")
    print("   output/tables/bioage_weighted_sensitivity.csv")
    print("   output/tables/tooth_count_availability.md")


if __name__ == "__main__":
    main()
