# -*- coding: utf-8 -*-
"""
config_biomarker.py  机制层（系统性炎症 × 生物学衰老）配置
==========================================================
配套《生物标志物变量字典_v1.md》（同一分析工程内，用于记录各标志物的核实状态）。

只做三件事：
  1. 逐队列血样标志物的**标准化变量名 → 原始变量名**映射（附核实状态）；
  2. 单位换算 + PhenoAge / KDM 的组分口径；
  3. 中介分析的规格清单（L1/L2/L3 分层）。

⚠️ 设计原则（很重要）
---------------------
· `status="verified"`  = 已读官方文件或真实数据文件逐字确认（写进预注册/论文可用）；
· `status="flagged"`   = 成分已确认存在，但**精确变量名待官方码本**（不得写进预注册，
                         脚本默认 **跳过** 该标志物，只有显式设 BIOMARKER_ALLOW_FLAGGED=1 才纳入）；
· 任何非 verified 的标志物一旦被纳入，结果表会打 `flag` 标记，提醒不要直接用于投稿。

为什么不用 Crimmins(2021) 22 标记的"官方系数"？
-----------------------------------------------
因为我们**没有**该文献的公开系数表（那是 HRS 内部拟合的参数）。写死一份臆造系数
是不可接受的。故本工程改用两条**不依赖外部系数**的路线（见 step11_biologicage.py）：
  ① KDM（Klemera-Doubal 2006）：各标志物对实龄回归，用样本内估出的 (q,k,s) 算加权年龄；
  ② Levine PhenoAge (2018)：系数已从原文及 PLoS Med 勘误逐字核对，见 PHENOAGE_COEF。
若日后拿到 Crimmins 官方系数，只需在 step11 的 CRIMMINS_COEF 填表即可启用。
"""
from __future__ import annotations

import os
from pathlib import Path

from config import ROOT, DATA_HARM, OUT_TAB, OUT_FIG        # noqa: F401

# ---------------------------------------------------------------- 路径与开关
# 血样标志物长表（与 harmonized_long_*.csv 同粒度：cohort,id,wave,year + 标志物列）
BIOMARKER_FILE = DATA_HARM / "harmonized_biomarkers.csv"

# 取"暴露后"血样时允许的窗口（年）：血样年 − 暴露年 ∈ [0, POST_EXPOSURE_WINDOW]
POST_EXPOSURE_WINDOW = 12

# 中介分析 bootstrap 次数（真实数据慢，可用环境变量调小做调试）
MEDIATION_BOOT = int(os.environ.get("MEDIATION_BOOT", "1000"))
# 是否允许纳入 flagged 标志物（默认否）
ALLOW_FLAGGED = os.environ.get("BIOMARKER_ALLOW_FLAGGED", "0") == "1"

RANDOM_SEED = 20261009

# ---------------------------------------------------------------- 标准化标志物名
# 内部统一用小写短名；PhenoAge 需要的 9 项见 PHENOAGE_COMPONENTS
MARKER_LABEL = {
    "albumin":    "白蛋白 Albumin (g/L)",
    "creatinine": "肌酐 Creatinine (μmol/L)",
    "glucose":    "空腹血糖 Fasting glucose (mmol/L)",
    "crp":        "C 反应蛋白 CRP (mg/L)",
    "il6":        "白细胞介素-6 IL-6 (pg/mL)",
    "wbc":        "白细胞计数 WBC (10^3/μL)",
    "lymph_pct":  "淋巴细胞百分比 Lymphocyte % (%)",
    "mcv":        "平均红细胞体积 MCV (fL)",
    "rdw":        "红细胞分布宽度 RDW (%)",
    "alp":        "碱性磷酸酶 ALP (U/L)",
    "bun":        "血尿素氮 BUN (mg/dL)",
    "cystatin_c": "胱抑素 C Cystatin C (mg/L)",
    "fibrinogen": "纤维蛋白原 Fibrinogen (g/L)",
    "hba1c":      "糖化血红蛋白 HbA1c (%)",
    "tnfr1":      "TNF 受体 1 (pg/mL)",
    "igf1":       "胰岛素样生长因子-1 IGF-1 (ng/mL)",
    "bnp":        "NT-proBNP (pg/mL)",
    "hgb":        "血红蛋白 Hemoglobin (g/dL)",
    "ferritin":   "铁蛋白 Ferritin (ng/mL)",
    "nfl":        "神经丝轻链 NfL (pg/mL)",
    "gfaP":       "胶质纤维酸性蛋白 GFAP (pg/mL)",
    "ptau217":    "磷酸化 Tau217 (pg/mL)",
    # —— 核心体测（非血样；HRS 2016 Core Section I）——
    "sbp":        "收缩压 SBP (mmHg)",
    "dbp":        "舒张压 DBP (mmHg)",
    "pulse":      "脉搏 Pulse (bpm)",
    "peakflow":   "峰流速 Peak flow (L/min)",
    "grip":       "握力 Grip strength (kg)",
    "walk_time":  "步行时间 Walking time (s)",
    "height_cm":  "身高 Height (cm)",
    "weight_kg":  "体重 Weight (kg)",
    "waist_cm":   "腰围 Waist (cm)",
    "bmi":        "体质指数 BMI (kg/m2)",
}

# PhenoAge 9 组分（Levine 2018）
PHENOAGE_COMPONENTS = ["albumin", "creatinine", "glucose", "crp",
                       "lymph_pct", "mcv", "rdw", "alp", "wbc"]

# 炎症标志物（"去污染"时要从生物年龄里剔除的组分）
INFLAMMATION_MARKERS = ["crp", "il6", "wbc", "lymph_pct", "fibrinogen"]
# 非炎症标志物（可构造"去污染版"生物年龄）
NONINFLAMMATION_MARKERS = ["albumin", "creatinine", "glucose", "mcv", "rdw",
                           "alp", "bun", "cystatin_c", "hba1c", "hgb"]

# ---------------------------------------------------------------- 核心体测（非血样）
# 来源：2026-10-10 一手核实自 HRS 2016 Core Final V2.0 官方码本 **Section I**（见工程内变量字典文档）。
#
# ⚠️ 这些变量在 **2016 HRS Core（Section I）**，**不在 VBS 文件**；按 HHID + PN 合并。
# ⚠️ 它们**不属于** Crimmins(2021) 22 项**血液**生物年龄组分，属**功能/生理**衰老维度。
#    → 主分析（保守）不并入生物年龄；如需"生理-血样混合 BA"，见 PHYSICAL_AGE_MARKERS
#      与 available_markers(include_optional=True)（默认关闭）。
HRS_PHYSICAL_MEASURES = {
    "_source": "HRS 2016 Core Final V2.0 官方码本 Section I（一手核实）",
    "sbp":       {"vars": ["PI859", "PI864", "PI869"], "how": "mean", "unit": "mmHg",
                  "drop_codes": [993, 998, 999], "status": "verified"},
    "dbp":       {"vars": ["PI860", "PI865", "PI870"], "how": "mean", "unit": "mmHg",
                  "drop_codes": [993, 998, 999], "status": "verified"},
    "pulse":     {"vars": ["PI861", "PI866", "PI871"], "how": "mean", "unit": "bpm",
                  "drop_codes": [993, 998, 999], "status": "verified"},
    "peakflow":  {"vars": ["PI807", "PI808", "PI809"], "how": "max", "unit": "L/min",
                  "drop_codes": [890, 993, 998, 999], "status": "verified"},
    "grip":      {"vars": ["PI816", "PI851", "PI852", "PI853"], "how": "max", "unit": "kg",
                  "drop_codes": [993, 998, 999], "status": "verified",
                  "note": "优势手见 PI815"},
    "walk_time": {"vars": ["PI823", "PI824"], "how": "mean", "unit": "s",
                  "drop_codes": [993, 998, 999], "status": "verified",
                  "note": "步速 = 步道长度 ÷ 时间；步道长度待核实（字典 §6）"},
    "balance_semi": {"vars": ["PI880"], "how": "first", "unit": "s", "status": "verified"},
    "balance_full": {"vars": ["PI897"], "how": "first", "unit": "s", "status": "verified"},
    "height_cm": {"vars": ["PI834"], "how": "first", "unit": "cm", "raw_unit": "in",
                  "conv": 2.54, "drop_codes": [98, 99], "status": "verified"},
    "weight_kg": {"vars": ["PI841"], "how": "first", "unit": "kg", "raw_unit": "lb",
                  "conv": 0.45359, "drop_codes": [993, 998, 999], "status": "verified"},
    "waist_cm":  {"vars": ["PI907"], "how": "first", "unit": "cm", "raw_unit": "in",
                  "conv": 2.54, "drop_codes": [993, 998, 999], "status": "verified"},
    "bmi":       {"vars": [], "how": "derived", "unit": "kg/m2",
                  "formula": "weight_kg / (height_cm/100)^2", "status": "derived"},
}
# 可并入 KDM 的体测标志物（默认**不**并入，保持血液口径；开启见 step11 的
# BIOAGE_INCLUDE_PHYSICAL=1 → available_markers(include_optional=True)）
PHYSICAL_AGE_MARKERS = ["sbp", "peakflow", "grip"]

# ---------------------------------------------------------------- 逐队列变量映射
# 来源：《生物标志物变量字典_v1.md》§3；verified = 一手核实
BIOMARKERS = {
    "HRS": {
        # 2016 Venous Blood Study（VBS）主文件 + 补充文件 + 流式 + 2016 DBS
        # 变量名一手核实自官方码本 V3.0（见《HRS_2016_VBS_码本与变量映射_v1.md》）
        "_wave": "2016", "_blood_year": 2016,
        "_source": "HRS 2016 VBS 官方码本 V3.0（2026-10-10 一手核实）",
        "_weight": "PVBSWGTR", "_valid_flag": "VBS16VALID",
        "albumin":    {"var": "PALB",    "unit": "g/L",     "status": "verified",
                       "raw_unit": "g/dL",  "note": "×10 → g/L（PhenoAge 用）"},
        "creatinine": {"var": "PCR",     "unit": "umol/L",  "status": "verified",
                       "raw_unit": "mg/dL", "note": "×88.42 → μmol/L"},
        "glucose":    {"var": "PGLUFF",  "unit": "mmol/L",  "status": "verified",
                       "raw_unit": "mg/dL", "note": "×0.05551 → mmol/L（空腹血糖）"},
        "crp":        {"var": "PCRP",    "unit": "mg/L",    "status": "verified",
                       "note": "hsCRP（VBS 主文件）；PhenoAge 用 ln(×0.1 mg/dL)"},
        "il6":        {"var": "PIL6",    "unit": "pg/mL",   "status": "verified",
                       "note": "VBS 补充文件"},
        "wbc":        {"var": "PWBC",    "unit": "10^3/uL", "status": "verified"},
        "lymph_pct":  {"var": "PLYMP",   "unit": "%",       "status": "verified"},
        "mcv":        {"var": "PMCV",    "unit": "fL",      "status": "verified"},
        "rdw":        {"var": "PRDW",    "unit": "%",       "status": "verified"},
        "alp":        {"var": "PALKP2",  "unit": "U/L",     "status": "verified"},
        "bun":        {"var": "PBUN",    "unit": "mg/dL",   "status": "verified"},
        "cystatin_c": {"var": "PCYSC",   "unit": "mg/L",    "status": "verified"},
        "bnp":        {"var": "PNTBNPE", "unit": "pg/mL",   "status": "verified",
                       "note": "NT-proBNP"},
        "hba1c":      {"var": "PA1C_ADJ","unit": "%",       "status": "verified",
                       "note": "2016 DBS（NHANES 等效值，用 _ADJ 而非 PA1CUW）"},
        "tnfr1":      {"var": "PTNFR1",  "unit": "pg/mL",   "status": "verified",
                       "note": "VBS 补充文件"},
        "igf1":       {"var": "PIGF1",   "unit": "ng/mL",   "status": "verified",
                       "note": "VBS 补充文件"},
        "hgb":        {"var": "PHGB",    "unit": "g/dL",    "status": "verified"},
        "ferritin":   {"var": "PFERTN",  "unit": "ng/mL",   "status": "verified"},
        # —— 血脂（2026-10-10 纳入 KDM：HRS 为 mg/dL，ELSA 为 mmol/L；
        #    ⚠️ KDM 对每个标志物的线性缩放不变 → 跨队列单位差异不影响 BA）——
        "chol":       {"var": "PCHOL",   "unit": "mg/dL",   "status": "verified"},
        "hdl":        {"var": "PHDLD",   "unit": "mg/dL",   "status": "verified"},
        "ldl":        {"var": "PLDLC",   "unit": "mg/dL",   "status": "verified"},
        "trig":       {"var": "PTGF",    "unit": "mg/dL",   "status": "verified"},
        # —— VBS 里还有、但未进标准名体系的（脚本可另取）——
        #   CMV：PCMVGE（连续 COI，KDM 用）/ PCMVGINT（三分类）
        #   免疫：PNEUT 中性粒% → NLR = PNEUT/PLYMP
        #   流式：PCD4T_PCT / PCD8T_PCT → CD4/CD8 比值
        # ⚠️ HRS **无纤维蛋白原（fibrinogen）**。
        # —— 核心体测（**2016 HRS Core Section I**，非 VBS；按 HHID+PN 合并）——
        #    标记 optional=True → **默认不并入生物年龄**（保持血液口径）；
        #    如需生理-血样混合 BA，设 BIOAGE_INCLUDE_PHYSICAL=1。明细见 HRS_PHYSICAL_MEASURES。
        "sbp":      {"var": "PI859/PI864/PI869", "unit": "mmHg",  "status": "verified",
                     "optional": True, "note": "三次均值 → PHYSICAL_MEASURES['sbp']"},
        "peakflow": {"var": "PI807/PI808/PI809", "unit": "L/min", "status": "verified",
                     "optional": True, "note": "三次最大值 → PHYSICAL_MEASURES['peakflow']"},
        "grip":     {"var": "PI816/PI851/PI852/PI853", "unit": "kg", "status": "verified",
                     "optional": True, "note": "四次最大值 → PHYSICAL_MEASURES['grip']"},
    },
    "ELSA": {
        "_wave": "W4(2008/9)", "_blood_year": 2008,
        "_source": "ELSA W4 护士访视文件（wave_4_nurse_data.dta）一手核实；"
                   "变量名在文件中为**小写**，哨兵码为**负值**（-1/-2/-6/-11…）",
        "crp":        {"var": "hscrp", "unit": "mg/L",    "status": "verified", "note": "炎症层主力"},
        "fibrinogen": {"var": "cfib",  "unit": "g/L",     "status": "verified"},
        "wbc":        {"var": "wbc",   "unit": "10^3/uL", "status": "verified"},
        "hba1c":      {"var": "hba1c", "unit": "%",       "status": "verified"},
        "glucose":    {"var": "fglu",  "unit": "mmol/L",  "status": "verified",
                       "note": "仅空腹；非空腹为负哨兵码"},
        "ferritin":   {"var": "rtin",  "unit": "ng/mL",   "status": "verified"},
        "igf1":       {"var": "igf1",  "unit": "nmol/L",  "status": "verified",
                       "note": "ELSA 为 nmol/L（HRS 为 ng/mL）；KDM 队内标准化，量纲不影响"},
        "hgb":        {"var": "hgb",   "unit": "g/dL",    "status": "verified"},
        # —— 血脂（2026-10-10 纳入 KDM；ELSA 为 mmol/L，HRS 为 mg/dL）——
        "chol":       {"var": "chol",  "unit": "mmol/L",  "status": "verified"},
        "hdl":        {"var": "hdl",   "unit": "mmol/L",  "status": "verified"},
        "ldl":        {"var": "ldl",   "unit": "mmol/L",  "status": "verified"},
        "trig":       {"var": "trig",  "unit": "mmol/L",  "status": "verified"},
        "dheas":      {"var": "dheas", "unit": "umol/L",  "status": "verified",
                       "note": "强衰老标志物；HRS VBS 无此项（KDM 队内拟合，允许面板不对称）"},
        "mch":        {"var": "mch",   "unit": "pg/cell", "status": "verified"},
    },
    "CHARLS": {
        "_wave": "2011(W1) / 2015(W3)", "_blood_year": 2011,
        "_source": "官方《2015 Blood Data Release Note》表 1（变量名一手核实）",
        "crp":        {"var": "bl_crp",  "unit": "mg/L",   "status": "verified", "note": "本队列唯一炎症标志物"},
        "wbc":        {"var": "bl_wbc",  "unit": "10^3/uL","status": "verified"},
        "creatinine": {"var": "bl_crea", "unit": "umol/L", "status": "verified"},
        "glucose":    {"var": "bl_glu",  "unit": "mmol/L", "status": "verified"},
        "cystatin_c": {"var": "bl_cysc", "unit": "mg/L",   "status": "verified"},
        "hba1c":      {"var": "bl_hbalc","unit": "%",      "status": "verified"},
        "mcv":        {"var": "bl_mcv",  "unit": "fL",     "status": "verified"},
        "bun":        {"var": "bl_bun",  "unit": "mg/dL",  "status": "verified"},
        "hgb":        {"var": "bl_hgb",  "unit": "g/dL",   "status": "verified"},
        # —— 以下 6 项 build 脚本已写入，2026-10-10 诊断确认两波均有 >200 非缺失 ——
        "chol":       {"var": "bl_cho",  "unit": "mg/dL",  "status": "verified"},
        "hdl":        {"var": "bl_hdl",  "unit": "mg/dL",  "status": "verified"},
        "ldl":        {"var": "bl_ldl",  "unit": "mg/dL",  "status": "verified"},
        "trig":       {"var": "bl_tg",   "unit": "mg/dL",  "status": "verified"},
        "plt":        {"var": "bl_plt",  "unit": "10^3/uL","status": "verified"},
        "hct":        {"var": "bl_hct",  "unit": "%",      "status": "verified"},
        # ⚠️ 缺白蛋白/ALP/RDW/淋巴% → PhenoAge 不可算；无中性粒计数 → NLR 不可算
    },
    "NHANES": {
        "_wave": "2011-14(认知期) / 2015-18(CRP 期)", "_blood_year": 2011,
        "_source": "真实 XPT 文件逐列读取（变量名一手核实）",
        "albumin":    {"var": "LBXSAL",    "unit": "g/L",     "status": "verified"},
        "alp":        {"var": "LBXSAPSI",  "unit": "U/L",     "status": "verified"},
        "creatinine": {"var": "LBXSCR",    "unit": "umol/L",  "status": "verified", "note": "原始 mg/dL 需 ×88.42"},
        "glucose":    {"var": "LBXSGL",    "unit": "mmol/L",  "status": "verified"},
        "wbc":        {"var": "LBXWBCSI",  "unit": "10^3/uL", "status": "verified"},
        "lymph_pct":  {"var": "LBXLYPCT",  "unit": "%",       "status": "verified"},
        "mcv":        {"var": "LBXMCVSI",  "unit": "fL",      "status": "verified"},
        "rdw":        {"var": "LBXRDW",    "unit": "%",       "status": "verified"},
        "crp":        {"var": "LBXHSCRP",  "unit": "mg/L",    "status": "verified", "note": "仅 2009-10 / 2015-18，与认知期不重叠"},
    },
    "SHARE": {
        "_wave": "W6(2015) DBS", "_blood_year": 2015,
        "_source": "SHARE-DBS Release 2.0.0（成分已核实；精确变量名+转换公式待注册下载）",
        "crp":        {"var": "?", "unit": "mg/L",   "status": "flagged", "note": "DBS 值需官方转换公式"},
        "cystatin_c": {"var": "?", "unit": "mg/L",   "status": "flagged"},
        "hba1c":      {"var": "?", "unit": "%",      "status": "flagged"},
        "nfl":        {"var": "?", "unit": "pg/mL",  "status": "flagged", "note": "Set2, 2026-04 新发布"},
        "gfaP":       {"var": "?", "unit": "pg/mL",  "status": "flagged"},
        "ptau217":    {"var": "?", "unit": "pg/mL",  "status": "flagged"},
    },
}

# 无任何血样的队列 —— 显式登记，脚本遇到即跳过并说明
NO_BLOOD_COHORTS = ["KLoSA", "LASI", "MHAS"]

# ---------------------------------------------------------------- 单位换算
# 各队列原始单位 → PhenoAge 口径的单位。字段缺失视为已是目标单位。
# 参考：Levine 2018 / Liu 2018 PLoS Med 勘误（Frontiers 2026 复核）
UNIT_CONVERSIONS = {
    # (目标单位) 需要的换算：原始 → 目标
    "creatinine_mgdl_to_umolL": 88.42,      # mg/dL → μmol/L
    "glucose_mgdl_to_mmolL": 0.05551,       # mg/dL → mmol/L
    "albumin_gdl_to_gL": 10.0,              # g/dL → g/L
    "crp_mgL_to_mgdl": 0.1,                 # mg/L → mg/dL（PhenoAge 用 ln(CRP mg/dL)）
}

# PhenoAge 常数（Levine 2018；勘误见 Liu 2018 PLoS Med, PMC6388911）
PHENOAGE_COEF = {
    "intercept": -19.9067,
    "albumin_gL": -0.0336,
    "creatinine_umolL": 0.0095,
    "glucose_mmolL": 0.1953,
    "ln_crp_mgdl": 0.0954,
    "lymph_pct": -0.0120,
    "mcv_fL": 0.0268,
    "rdw_pct": 0.3306,
    "alp_UL": 0.00188,
    "wbc_1e3uL": 0.0554,
    "age_years": 0.0804,
    "gamma": 0.0076927,          # Gompertz 尺度参数
    "horizon_months": 120,       # 10 年
    "age_intercept": 141.50225,
    "age_slope": 0.090165,
    "age_inner": -0.00553,
    "source": "Levine et al. 2018 Aging; 勘误 Liu et al. 2018 PLoS Med 15(12):e1002718",
}

# ---------------------------------------------------------------- 中介分析规格
# 分层设计（见变量字典 §5）：
#   L2  炎症中介层：HRS + ELSA + CHARLS（暴露后血样可得）
#   L2b 代理炎症：NHANES 2011-14 的 NLR（横断面，脚本里单独构造）
#   L3  衰老中介层：HRS 单队（生物年龄加速）
#   L4  衰老稳健性：7 队衰弱指数（不在本脚本）
#   L5  探索：SHARE W6 的 CRP / pTau217 / NfL / GFAP
MEDIATION_SPECS = [
    # ---- L2 炎症中介（三队平行，主分析） ----
    {"layer": "L2", "cohort": "HRS",   "mediator": "crp",  "label": "HRS · CRP"},
    {"layer": "L2", "cohort": "HRS",   "mediator": "il6",  "label": "HRS · IL-6"},
    {"layer": "L2", "cohort": "ELSA",  "mediator": "crp",  "label": "ELSA · CRP"},
    {"layer": "L2", "cohort": "ELSA",  "mediator": "fibrinogen", "label": "ELSA · 纤维蛋白原"},
    {"layer": "L2", "cohort": "CHARLS","mediator": "crp",  "label": "CHARLS · CRP"},
    # ---- L3 衰老中介（HRS 单队） ----
    {"layer": "L3", "cohort": "HRS",   "mediator": "bioage_accel_clean",
     "label": "HRS · 生物年龄加速(去污染)"},
    # ---- L5 探索 ----
    {"layer": "L5", "cohort": "SHARE", "mediator": "ptau217", "label": "SHARE · pTau217"},
]

# 串联链式中介：暴露 → M1(炎症) → M2(生物衰老) → 结局
SERIAL_SPECS = [
    {"layer": "L3", "cohort": "HRS", "m1": "crp", "m2": "bioage_accel_clean",
     "label": "HRS · 缺牙→CRP→生物年龄加速→认知"},
]


# ---------------------------------------------------------------- 演示/合成数据
# 缺失模式（忠实于官方文档）：某队列**没有**哪些标志物
_MISSING_BY_COHORT = {
    "CHARLS": ("albumin", "alp", "rdw", "lymph_pct", "il6", "fibrinogen"),
    "ELSA":   ("albumin", "alp", "creatinine", "rdw", "lymph_pct", "bun"),
    "SHARE":  ("albumin", "alp", "creatinine", "rdw", "lymph_pct"),
    "HRS":    tuple(),
    "NHANES": tuple(),
    "LASI":   ("albumin", "alp", "creatinine", "rdw", "lymph_pct", "il6",
               "fibrinogen", "cystatin_c", "hba1c", "bun", "hgb", "mcv", "wbc"),
}

_BLOOD_YEAR = {"HRS": 2016, "ELSA": 2008, "CHARLS": 2011, "NHANES": 2011,
               "SHARE": 2015, "LASI": 2017}


def _synth_markers(age: "np.ndarray", cohort: str, rng) -> dict:
    """按「标志物 = 基线 + 实龄效应 + 噪声」生成一组标志物（合成）。"""
    import numpy as np
    n = len(age)
    d = {
        "albumin":    44.0 - 0.10 * (age - 60) + rng.normal(0, 2.2, n),
        "creatinine": 78.0 + 0.55 * (age - 60) + rng.normal(0, 11, n),
        "glucose":    5.1 + 0.020 * (age - 60) + rng.normal(0, 0.55, n),
        "crp":        np.exp(-0.2 + 0.030 * (age - 60) + rng.normal(0, 0.85, n)),
        "il6":        np.exp(0.6 + 0.022 * (age - 60) + rng.normal(0, 0.5, n)),
        "wbc":        6.4 + 0.010 * (age - 60) + rng.normal(0, 1.3, n),
        "lymph_pct":  30.0 - 0.075 * (age - 60) + rng.normal(0, 5.5, n),
        "mcv":        89.0 + 0.08 * (age - 60) + rng.normal(0, 4.0, n),
        "rdw":        13.0 + 0.055 * (age - 60) + rng.normal(0, 0.85, n),
        "alp":        72.0 + 0.55 * (age - 60) + rng.normal(0, 17, n),
        "bun":        14.0 + 0.25 * (age - 60) + rng.normal(0, 3.2, n),
        "cystatin_c": 0.85 + 0.012 * (age - 60) + rng.normal(0, 0.13, n),
        "hba1c":      5.6 + 0.015 * (age - 60) + rng.normal(0, 0.5, n),
        "fibrinogen": 3.1 + 0.028 * (age - 60) + rng.normal(0, 0.6, n),
        "hgb":        14.0 - 0.030 * (age - 60) + rng.normal(0, 1.2, n),
        "ptau217":    np.exp(-3.0 + 0.035 * (age - 60) + rng.normal(0, 0.6, n)),
    }
    for m in _MISSING_BY_COHORT.get(cohort, ()):
        d.pop(m, None)
    return d


def synth_marker_frame(meta, seed: int = RANDOM_SEED) -> "pd.DataFrame":
    """为给定受试者（含真实 ID）合成一组血样标志物。

    meta : DataFrame，须含列 cohort, id, age。
    返回：cohort,id,wave,year,age + 标志物列。
    用途：演示模式下把「模拟标志物」挂到**真实长表的同一批人**上，
          从而能端到端跑通「暴露→中介→结局」而无需真数据。
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    rows = []
    for coh, sub in meta.groupby("cohort"):
        age = pd.to_numeric(sub["age"], errors="coerce").values.astype(float)
        d = {"cohort": coh, "id": sub["id"].values,
             "wave": 1, "year": _BLOOD_YEAR.get(coh, 2012), "age": age}
        d.update(_synth_markers(np.nan_to_num(age, nan=65.0), coh, rng))
        rows.append(pd.DataFrame(d))
    return pd.concat(rows, ignore_index=True)


def demo_biomarkers(n: int = 4000, seed: int = RANDOM_SEED,
                    cohorts=("HRS", "ELSA", "CHARLS", "NHANES")) -> "pd.DataFrame":
    """生成结构逼真的**合成**血样标志物表（独立演示/自检用）。

    ⚠️ 合成数据只用于跑通代码/自检，**任何数字不得写进论文**。
    返回列：cohort, id, wave, year, age, age_c + 标志物列（内部标准名）。
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    rows = []
    for c in cohorts:
        sub_n = max(1, n // len(cohorts))
        age = rng.uniform(50, 88, sub_n)
        d = {"cohort": c, "id": [f"{c}{i:06d}" for i in range(sub_n)],
             "wave": 1, "year": _BLOOD_YEAR.get(c, 2012), "age": age}
        d.update(_synth_markers(age, c, rng))
        rows.append(pd.DataFrame(d))
    out = pd.concat(rows, ignore_index=True)
    out["age_c"] = out["age"] - out["age"].mean()
    return out


def available_markers(cohort: str, include_flagged: bool | None = None,
                      include_optional: bool = False) -> list[str]:
    """返回某队列**可用**的标准标志物名（按 status 过滤）。

    include_optional : 是否纳入 `optional=True` 的**核心体测**标志物（sbp/peakflow/grip）。
        默认 False —— 主分析的生物年龄保持**血液口径**（与 Crimmins 22 项可比）；
        设 True 则得到"生理-血样混合 BA"（须在 Methods 声明为功能维度扩展）。
    """
    allow = ALLOW_FLAGGED if include_flagged is None else include_flagged
    d = BIOMARKERS.get(cohort, {})
    out = []
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if v.get("optional") and not include_optional:
            continue
        if v.get("status") == "verified" or allow:
            out.append(k)
    return out
