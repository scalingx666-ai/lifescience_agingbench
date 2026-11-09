# -*- coding: utf-8 -*-
"""
build_hrs_biomarkers.py   HRS 原始文件 → 管道标准血样长表
=========================================================
把本地 HRS 原始数据整理成 `data/harmonized/harmonized_biomarkers.csv`，
使 step11（生物年龄）/ step10（中介）/ step12（衰老当结局）从**演示模式切到真实 HRS**。

输入（全部为本地已有原始文件，无需联网、无需注册）
----------------------------------------------------
基目录（可用环境变量 `HRS_RAW_DIR` 覆盖；默认见 DEFAULT_RAW）：
  · 2016 静脉血研究VBS/HRS2016VBS/hrs2016vbs.sav        主文件（22 项血标志物 + 权重）
  · 2016 静脉血研究VBS/HRS2016VBSsupp_0/vbs16aa.sav     补充（细胞因子 / 维D / IGF-1）
  · 2016 静脉血研究VBS/HRS2016VBSsubs/vbs16ss.sav       子样本（BDNF / Clusterin / HCV / MTDNAcn）
  · 2016 静脉血研究VBS/FlowCyto2016/built/sas/flocyt2016.sas7bdat  流式（CD4/CD8/T/NK/B）
  · 2016 HRS/BIOMK16BL/BIOMK16BL_R.sav                  2016 DBS 血斑（HbA1c 来源）
  · 2016 HRS/H16I_R.dta                                 2016 核心体测 Section I（SBP/峰流速/握力/步速/体格）
  · Cross-Wave Tracker File/trk2020tr_r.dta             管理变量（VBS16VALID / 实龄 PAGE / 权重）

主键
----
`id = norm_id(HHID + PN)`（去前导零），**与 step1_master.py 的 `_norm_id` 完全一致** ——
实测 99.56% 的 VBS 记录能对上主长表（`harmonized_long_anchored.csv`）的 HRS id。
wave = 13（HRS 2016），year = 2016。

输出单位 = 内部标准口径（build 时即换算完毕）
---------------------------------------------
  albumin g/dL→g/L（×10）｜creatinine mg/dL→μmol/L（×88.42）｜glucose mg/dL→mmol/L（×0.05551）
  crp 保持 mg/L｜身高 in→cm｜体重 lb→kg｜腰围 in→cm
  ⚠️ step11.normalise_units() 的自动探测（median<10 / <20 / >30）**对本口径幂等**，
     不会二次换算（albumin 中位≈39、creatinine≈85、glucose≈5.5，均不触发）。

演示模式纪律
------------
本脚本**只产出真实数据**；`harmonized_biomarkers.csv` 一旦存在，step11/10/12 自动切真实。
若某原始文件缺失，脚本会明确报错退出（不静默降级、不合成）。

用法
----
  python build_hrs_biomarkers.py            # 构建 + 附生物年龄列 + QC
  python build_hrs_biomarkers.py --no-bioage  # 只出标志物（不调 step11）
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_HARM, DATA_RAW                           # noqa: E402
from config_biomarker import (                                   # noqa: E402
    BIOMARKER_FILE, HRS_PHYSICAL_MEASURES, OUT_TAB,
)

# ---------------------------------------------------------------- 原始数据基目录
# 目录结构约定：<DATA_RAW>/<cohort_raw_dir>，其中 DATA_RAW 由 config.py 定义。
# 若原始文件放在别处，请设置环境变量 HRS_RAW_DIR 指向该目录。
DEFAULT_RAW = str(DATA_RAW / "HRS")
HRS_RAW = Path(os.environ.get("HRS_RAW_DIR", DEFAULT_RAW))

F_VBS_MAIN = HRS_RAW / "2016 静脉血研究VBS/HRS2016VBS/hrs2016vbs.sav"
F_VBS_SUPP = HRS_RAW / "2016 静脉血研究VBS/HRS2016VBSsupp_0/vbs16aa.sav"
F_VBS_SUBS = HRS_RAW / "2016 静脉血研究VBS/HRS2016VBSsubs/vbs16ss.sav"
F_FLOW     = HRS_RAW / "2016 静脉血研究VBS/FlowCyto2016/built/sas/flocyt2016.sas7bdat"
F_DBS      = HRS_RAW / "2016 HRS/BIOMK16BL/BIOMK16BL_R.sav"
F_CORE_I   = HRS_RAW / "2016 HRS/H16I_R.dta"
F_TRACKER  = HRS_RAW / "Cross-Wave Tracker File/trk2020tr_r.dta"

HRS_WAVE_2016 = 13
HRS_YEAR = 2016

# 静脉血缺失时是否用 DBS（血斑）**校准值**回填 crp / cystatin_c / chol / hdl。
# 默认关闭：DBS 与静脉血是两套测定，混测须在 Methods 明确声明并做敏感性分析。
# 开启：HRS_DBS_FALLBACK=1 python build_hrs_biomarkers.py
DBS_FALLBACK = os.environ.get("HRS_DBS_FALLBACK", "0") == "1"

# ---------------------------------------------------------------- 变量映射（一手核实）
# 来源：《HRS_2016_VBS_码本与变量映射_v1.md》《HRS_2016_核心体测_码本与变量映射_v1.md》
VBS_MAIN_MAP = {
    # —— 标准标志物（进 config_biomarker 体系）——
    "albumin": "PALB", "alp": "PALKP2", "bun": "PBUN", "crp": "PCRP",
    "creatinine": "PCR", "cystatin_c": "PCYSC", "glucose": "PGLUFF",
    "hgb": "PHGB", "lymph_pct": "PLYMP", "mcv": "PMCV", "rdw": "PRDW",
    "wbc": "PWBC", "bnp": "PNTBNPE", "ferritin": "PFERTN",
    # —— 扩展列（未进标准体系；供探索性分析 / NLR）——
    "neut_pct": "PNEUT", "mono_pct": "PMONO", "eos_pct": "PEOS", "baso_pct": "PBASO",
    "neut_abs": "PANEU", "lymph_abs": "PALYM", "plt": "PPLT", "hct": "PHCT",
    "chol": "PCHOL", "hdl": "PHDLD", "ldl": "PLDLC", "trig": "PTGF",
    "cmv_igg": "PCMVGE",
}
VBS_SUPP_MAP = {
    "il6": "PIL6", "tnfr1": "PTNFR1", "igf1": "PIGF1",
    "il10": "PIL10", "il1ra": "PIL1RA", "tgf_beta": "PTGF_BETA",
    "vd2": "PVD2", "vd3": "PVD3",
}
VBS_SUBS_MAP = {
    "bdnf": "PBDNF", "clusterin": "PCLUSTERIN", "hcy": "PHCY", "mtdnacn": "PMTDNACN",
}
DBS_MAP = {"hba1c": "PA1C_ADJ"}
# ⚠️ DBS（血斑）与静脉血是**两套测定**，不合并同名：DBS 版一律加 `_dbs` 后缀，
#    以免静默混测（静脉血优先；hba1c 仅 DBS 有，故直接用）。
DBS_EXTRA = {"crp_dbs": "PCRP_ADJ", "cystatin_c_dbs": "PCYSC_ADJ",
             "hdl_dbs": "PHDL_ADJ", "chol_dbs": "PTC_ADJ"}
FLOW_MAP = {
    "cd4_pct": "PCD4T_PCT", "cd8_pct": "PCD8T_PCT",
    "cd4_abs": "PCD4T_COUNT", "cd8_abs": "PCD8T_COUNT",
}

# 合理性区间（**原始单位**）；超出者视为特殊码/录入错误 → 置 NaN 并计数
PLAUSIBLE = {
    "albumin": (1.0, 7.0), "alp": (5, 1000), "bun": (1, 150), "crp": (0, 300),
    "creatinine": (0.1, 20), "cystatin_c": (0.2, 10), "glucose": (20, 600),
    "hgb": (3, 25), "lymph_pct": (0, 100), "mcv": (40, 150), "rdw": (5, 40),
    "wbc": (0.5, 30), "bnp": (0, 50000), "ferritin": (0, 2000),
    "il6": (0, 500), "tnfr1": (0, 20000), "igf1": (0, 1000),
    "hba1c": (3, 20), "neut_pct": (0, 100), "plt": (5, 1200), "hct": (10, 70),
    "chol": (50, 600), "hdl": (5, 150), "ldl": (10, 500), "trig": (10, 1500),
    "bdnf": (0, 100), "clusterin": (0, 1000), "hcy": (0, 200),
    "cd4_pct": (0, 1), "cd8_pct": (0, 1), "cd4_abs": (0, 5), "cd8_abs": (0, 5),
    "crp_dbs": (0, 300), "cystatin_c_dbs": (0.2, 10),
    "hdl_dbs": (5, 150), "chol_dbs": (50, 600),
}

# 原始→内部标准单位的乘数（build 时即应用）
UNIT_MULT = {
    "albumin": 10.0,        # g/dL → g/L
    "creatinine": 88.42,    # mg/dL → μmol/L
    "glucose": 0.05551,     # mg/dL → mmol/L
}


# ================================================================ 工具
def norm_id(hhid, pn) -> pd.Series:
    """id = norm_id(HHID + PN)。PN 统一补齐到 3 位（原始文件本即 str3；数值型兜底）。"""
    h = pd.Series(hhid).astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    p = pd.Series(pn).astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    # 数值型读入时 '10' → 补成 '010'（与官方 str3 对齐）
    med_len = p.str.len().median()
    if pd.notna(med_len) and med_len <= 2:
        p = p.str.zfill(3)
    return (h + p).str.lstrip("0")


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"缺少原始文件：{path}")
    ext = path.suffix.lower()
    if ext == ".sav":
        df, _ = pyreadstat.read_sav(str(path))
    elif ext == ".dta":
        df, _ = pyreadstat.read_dta(str(path))
    elif ext == ".sas7bdat":
        df, _ = pyreadstat.read_sas7bdat(str(path))
    else:
        raise ValueError(f"不支持：{ext}")
    return df


def _keyed(df: pd.DataFrame) -> pd.DataFrame:
    """加 id 列（并保留 HHID/PN 便于诊断）。"""
    out = df.copy()
    out["id"] = norm_id(out["HHID"], out["PN"])
    return out


def _block(df: pd.DataFrame, mapping: dict, tag: str, log: list) -> pd.DataFrame:
    """按映射取列 → 重命名为标准名 → 合理性筛 → 返回 [id + 标准列]。"""
    got = {}
    for std, raw in mapping.items():
        if raw not in df.columns:
            log.append(f"  [{tag}] ⚠️ 缺列 {raw}（标准名 {std}）→ 跳过")
            continue
        v = pd.to_numeric(df[raw], errors="coerce")
        if std in PLAUSIBLE:
            lo, hi = PLAUSIBLE[std]
            bad = int((v.notna() & ~v.between(lo, hi)).sum())
            if bad:
                log.append(f"  [{tag}] {std}<-{raw}: 剔除超范围 {bad} 个（区间 {lo}–{hi}）")
            v = v.where(v.between(lo, hi))
        got[std] = v
    out = pd.DataFrame(got)
    out.insert(0, "id", df["id"].values)
    log.append(f"  [{tag}] n={len(out):,}  产出列 {len(got)}：{', '.join(got) or '—'}")
    return out


def _drop_special(df: pd.DataFrame, cols: list[str], codes: list, tag: str, log: list) -> pd.DataFrame:
    """把特殊码（DK/RF/超刻度）置 NaN —— **绝不能当 0**。"""
    n_drop = 0
    for c in cols:
        if c not in df.columns:
            continue
        v = pd.to_numeric(df[c], errors="coerce")
        m = v.isin(codes)
        n_drop += int(m.sum())
        df[c] = v.where(~m)
    if n_drop:
        log.append(f"  [{tag}] 特殊码 {codes} 剔除 {n_drop} 个取值")
    return df


# ================================================================ 各数据块
def build_physical(log: list) -> pd.DataFrame:
    """2016 核心体测（Section I）：三次均值 / 最大值 + 特殊码剔除 + 单位换算。"""
    df = _keyed(_read(F_CORE_I))
    spec = HRS_PHYSICAL_MEASURES
    out = pd.DataFrame({"id": df["id"].values})
    for std, cfg in spec.items():
        if std.startswith("_"):
            continue
        if cfg["how"] == "derived":
            continue
        cols = [c for c in cfg["vars"] if c in df.columns]
        if not cols:
            log.append(f"  [体测] ⚠️ {std} 缺列 {cfg['vars']}")
            continue
        sub = df[cols].apply(pd.to_numeric, errors="coerce")
        sub = _drop_special(sub, cols, cfg.get("drop_codes", []), f"体测·{std}", log)
        if cfg["how"] == "mean":
            v = sub.mean(axis=1, skipna=True)
        elif cfg["how"] == "max":
            v = sub.max(axis=1, skipna=True)
        else:                                   # first
            v = sub[cols[0]]
        if cfg.get("conv"):                     # 身高 in→cm / 体重 lb→kg
            v = v * cfg["conv"]
        if std in ("sbp", "dbp", "pulse"):
            v = v.where(v.between(50, 300) if std == "sbp"
                        else v.between(20, 200) if std == "dbp" else v.between(20, 200))
        out[std] = v
    # 派生
    if "height_cm" in out.columns and "weight_kg" in out.columns:
        h = out["height_cm"].where(out["height_cm"].between(100, 220))
        w = out["weight_kg"].where(out["weight_kg"].between(25, 200))
        out["bmi"] = w / (h / 100) ** 2
    log.append(f"  [体测] n={len(out):,}  列：{', '.join(c for c in out.columns if c != 'id')}")
    return out


def build_tracker(log: list) -> pd.DataFrame:
    """Tracker：有效标志、体重、2016 实龄（PAGE）、VBS 权重。"""
    df = _keyed(_read(F_TRACKER))
    keep = {}
    for std, raw in (("valid_vbs", "VBS16VALID"), ("age_interview", "PAGE"),
                     ("gender", "GENDER"), ("edu_years", "SCHLYRS"),
                     ("w_vbs_1618", "VBS1618WGTR"), ("birth_yr", "BIRTHYR")):
        if raw in df.columns:
            keep[std] = pd.to_numeric(df[raw], errors="coerce")
        else:
            log.append(f"  [Tracker] ⚠️ 缺列 {raw}（{std}）")
    out = pd.DataFrame(keep)
    out.insert(0, "id", df["id"].values)
    log.append(f"  [Tracker] n={len(out):,}  列：{', '.join(keep)}")
    return out


# ================================================================ 组装
def assemble(log: list) -> pd.DataFrame:
    log.append("— 读取各数据块 —")
    vb_raw = _keyed(_read(F_VBS_MAIN))
    main = _block(vb_raw, VBS_MAIN_MAP, "VBS主", log)
    supp = _block(_keyed(_read(F_VBS_SUPP)), VBS_SUPP_MAP, "VBS补充", log)
    subs = _block(_keyed(_read(F_VBS_SUBS)), VBS_SUBS_MAP, "VBS子样本", log)
    dbs_raw = _keyed(_read(F_DBS))
    dbs = _block(dbs_raw, DBS_MAP, "DBS", log).merge(
        _block(dbs_raw, DBS_EXTRA, "DBS扩展", log), on="id", how="outer")
    flow = _block(_keyed(_read(F_FLOW)), FLOW_MAP, "流式", log)
    phys = build_physical(log)
    trk = build_tracker(log)

    # 管理变量（直接从 VBS 主文件取）
    mgmt = pd.DataFrame({"id": vb_raw["id"].values})
    for std, raw in (("w_vbs", "PVBSWGTR"), ("vbs_days", "PVBS_N_DAYS"),
                     ("fasting", "PFASTYN")):
        if raw in vb_raw.columns:
            mgmt[std] = pd.to_numeric(vb_raw[raw], errors="coerce")

    # 基准 = **血样并集**（静脉血 ∪ DBS）——只有真正有血样测定的人才进表
    base_ids = pd.Index(pd.unique(pd.concat([main["id"], dbs["id"]], ignore_index=True)),
                        name="id")
    out = pd.DataFrame({"id": base_ids})
    log.append(f"— 基准（血样并集：VBS主 ∪ DBS）= {len(out):,} 人 "
               f"（VBS主 {main['id'].nunique():,} + DBS独有 {dbs['id'].nunique() - len(set(dbs['id']) & set(main['id'])):,}）")

    for label, blk in (("VBS主", main), ("VBS补充", supp), ("VBS子样本", subs),
                       ("DBS", dbs), ("流式", flow), ("核心体测", phys),
                       ("Tracker", trk), ("VBS管理", mgmt)):
        before = out.shape[1]
        out = out.merge(blk, on="id", how="left")
        log.append(f"  + {label:8s}（{blk['id'].nunique():,} 人） → n={len(out):,}  列 {before}→{out.shape[1]}")

    # 血样来源标记（静脉血优先；hba1c 仅 DBS）
    ven = set(main["id"]); dset = set(dbs["id"])
    out["blood_src"] = np.where(out["id"].isin(ven) & out["id"].isin(dset), "venous+dbs",
                        np.where(out["id"].isin(ven), "venous", "dbs"))

    # 单位换算（原始 → 内部标准）
    for m, mult in UNIT_MULT.items():
        if m in out.columns:
            out[m] = out[m] * mult

    # 可选的 DBS 回填（默认关闭；见文件头 DBS_FALLBACK 说明）
    if DBS_FALLBACK:
        filled = []
        for std, src in (("crp", "crp_dbs"), ("cystatin_c", "cystatin_c_dbs"),
                         ("chol", "chol_dbs"), ("hdl", "hdl_dbs")):
            if std in out.columns and src in out.columns:
                n0 = int(out[std].isna().sum())
                out[std] = out[std].fillna(out[src])
                filled.append(f"{std}←{src} +{n0 - int(out[std].isna().sum())}")
        log.append("— DBS 回填（HRS_DBS_FALLBACK=1）：" + ("；".join(filled) or "无可回填"))

    # 派生量
    if "neut_pct" in out.columns and "lymph_pct" in out.columns:
        den = out["lymph_pct"].where(out["lymph_pct"] > 0)
        out["nlr"] = out["neut_pct"] / den
    if "cd4_abs" in out.columns and "cd8_abs" in out.columns:
        den = out["cd8_abs"].where(out["cd8_abs"] > 0)
        out["cd4_cd8"] = out["cd4_abs"] / den
    if "age_interview" in out.columns:
        # 实龄 = 2016 访问年龄 + 采血距访问天数 / 365.25（HRS VBS 的 PVBS_N_DAYS）
        # ⚠️ DBS 独有人群没有 vbs_days（非 VBS 样本）→ 以访问年龄为准（fillna(0)），
        #    否则整列变 NaN 会把这批人从 KDM/PhenoAge 里静默剔除。
        adj = (out["vbs_days"].fillna(0.0) / 365.25) if "vbs_days" in out.columns else 0.0
        out["age"] = out["age_interview"] + adj

    out.insert(0, "cohort", "HRS")
    out.insert(2, "wave", HRS_WAVE_2016)
    out.insert(3, "year", HRS_YEAR)
    return out


# ================================================================ 质控
def _md_table(df: pd.DataFrame) -> str:
    """极简 markdown 表（不依赖 tabulate）。"""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            cells.append("" if pd.isna(v) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def qc_report(bm: pd.DataFrame, log: list) -> pd.DataFrame:
    std_cols = ["albumin", "alp", "bun", "crp", "creatinine", "cystatin_c", "glucose",
                "hgb", "lymph_pct", "mcv", "rdw", "wbc", "bnp", "ferritin", "il6",
                "tnfr1", "igf1", "hba1c", "sbp", "peakflow", "grip", "walk_time",
                "height_cm", "weight_kg", "waist_cm", "bmi", "nlr", "cd4_cd8"]
    if "blood_src" in bm.columns:
        log.append("— 血样来源分布：" + str(bm["blood_src"].value_counts().to_dict()))
    rows = []
    for c in std_cols:
        if c not in bm.columns:
            rows.append({"列": c, "n": 0, "缺失率": "—", "中位": np.nan, "说明": "未产出"})
            continue
        s = pd.to_numeric(bm[c], errors="coerce")
        rows.append({"列": c, "n": int(s.notna().sum()),
                     "缺失率": f"{s.isna().mean()*100:.1f}%",
                     "中位": round(float(s.median()), 3) if s.notna().any() else np.nan,
                     "说明": ""})
    qc = pd.DataFrame(rows)

    # 与主长表的 id 对齐率
    try:
        from config import HARM_LONG
        use = ["cohort", "id", "wave"]
        lg = pd.read_csv(HARM_LONG, usecols=use, low_memory=False)
        hids = set(lg.loc[lg.cohort == "HRS", "id"].astype(str))
        hit = bm["id"].astype(str).isin(hids)
        log.append(f"— 与主长表 id 对齐：命中 {hit.sum():,}/{len(bm):,} = {hit.mean()*100:.2f}%")
        if "valid_vbs" in bm.columns:
            v = pd.to_numeric(bm["valid_vbs"], errors="coerce")
            log.append(f"  VBS16VALID=1 的 n={int((v == 1).sum()):,}")
        log.append(f"  与长表交集且 VBS 有效 n={int((hit & (pd.to_numeric(bm.get('valid_vbs'), errors='coerce') == 1)).sum()):,}")
    except Exception as e:                                        # noqa: BLE001
        log.append(f"— ⚠️ 无法读取主长表做对齐诊断：{e}")
    return qc


# ================================================================ main
def main(with_bioage: bool = True) -> pd.DataFrame:
    DATA_HARM.mkdir(parents=True, exist_ok=True)
    log: list[str] = ["=" * 74,
                      "build_hrs_biomarkers —— HRS 原始数据 → harmonized_biomarkers.csv",
                      "=" * 74,
                      f"原始基目录：{HRS_RAW}"]
    bm = assemble(log)

    # 列顺序：主键 → 标准标志物 → 扩展 → 体测 → 管理 → age 已在前面
    head = ["cohort", "id", "wave", "year", "age"]
    rest = [c for c in bm.columns if c not in head]
    std_order = ["albumin", "alp", "bun", "crp", "creatinine", "cystatin_c", "glucose",
                 "hgb", "lymph_pct", "mcv", "rdw", "wbc", "bnp", "ferritin",
                 "il6", "tnfr1", "igf1", "hba1c"]
    ordered = head + [c for c in std_order if c in rest] + \
        [c for c in rest if c not in std_order]
    bm = bm[ordered]

    log.append(f"— 组装完成：n={len(bm):,}  列数={bm.shape[1]}")

    # —— 附生物年龄列（供 step10 真实模式直接取 bioage_accel_clean）——
    if with_bioage:
        try:
            from step11_biologicage import compute_bioage_table
            people, qc = compute_bioage_table(bm, allow_flagged=False)
            add = people[["cohort", "id", "kdm_accel", "kdm_clean_accel",
                          "phenoage_accel", "n_markers", "n_markers_clean"]].copy()
            add = add.rename(columns={"kdm_clean_accel": "bioage_accel_clean"})
            bm = bm.merge(add, on=["cohort", "id"], how="left")
            log.append(f"— 已附生物年龄列（{qc['metric'].unique().tolist()}）")
            log.append(qc.to_string(index=False))
        except Exception as e:                                    # noqa: BLE001
            log.append(f"— ⚠️ 生物年龄列计算失败（{e}）→ 仅输出标志物")

    bm.to_csv(BIOMARKER_FILE, index=False, encoding="utf-8-sig")
    log.append(f"— 已写出：{BIOMARKER_FILE}  （n={len(bm):,}，{bm.shape[1]} 列）")

    qc = qc_report(bm, log)
    (DATA_HARM / "hrs_biomarker_build_log.txt").write_text("\n".join(log), encoding="utf-8")

    OUT_TAB.mkdir(parents=True, exist_ok=True)
    md = ["# HRS 血样长表构建质控", "",
          "**数据来源**：HRS 2016 VBS 主/补充/子样本 + 流式 + 2016 DBS + 2016 核心体测 + Tracker（本地原始文件）", "",
          "## 逐列覆盖", "", _md_table(qc), "", "## 构建日志", "", "```",
          "\n".join(log), "```"]
    (OUT_TAB / "hrs_biomarker_build_qc.md").write_text("\n".join(md), encoding="utf-8")

    print("\n".join(log))
    print("\n—— 逐列覆盖 ——")
    print(qc.to_string(index=False))
    return bm


if __name__ == "__main__":
    main(with_bioage="--no-bioage" not in sys.argv)
