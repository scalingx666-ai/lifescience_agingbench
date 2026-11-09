# -*- coding: utf-8 -*-
"""
build_elsa_biomarkers.py   ELSA 护士血样（W4, 2008/9）→ 追加进管道标准血样长表
================================================================================
把本地 ELSA 原始护士文件整理成标准行，**追加**到 `data/harmonized/harmonized_biomarkers.csv`
（保留已有 HRS 行），使 step11/10/12 的**炎症中介层**从 HRS 单队扩到 HRS + ELSA。

输入（本地已有原始文件，无需联网、无需注册）
--------------------------------------------
基目录（`ELSA_RAW_DIR` 可覆盖；默认见 DEFAULT_ELSA_RAW）：
  · wave4/wave_4_nurse_data.dta     ELSA 第 4 波护士访视血样（2008/9）

为什么用 W4
-----------
  · 暴露（无牙颌）在 W3(2006)/W5(2010) 测得；W4 血样(2008/9) 落在 W3 之后 → 满足时序。
  · W2(2004) 早于暴露，**排除**；W6 hba1c 用 IFCC 单位（mmol/mol），W8/9 样本较小、间隔最长。
  · W4 与 config_biomarker.ELSA 声明的 `_blood_year=2008` 一致。

主键
----
`id = str(idauniq)`（ELSA 全波唯一个人编号，6 位）——与主长表 ELSA id 直接对齐
（实测约 3/4 命中；未命中者为锚定长表未纳入者，脚本只报告不补齐）。

单位与哨兵
----------
  · hba1c %｜hscrp mg/L｜cfib g/L｜wbc ×10⁹/L｜hgb g/dL｜rtin ng/mL｜igf1 nmol/L
  · ⚠️ `fglu`（空腹血糖）含**哨兵值 −1 / −11**（非空腹样本）→ 按 <2 mmol/L 剔除，**不得当 0**。
  · ⚠️ ELSA `igf1` 单位为 **nmol/L**（HRS 为 ng/mL）——KDM 在**队列内**标准化，跨队列量纲不影响。

用法
----
  python build_elsa_biomarkers.py             # 构建 + 合并 + 重算生物年龄 + QC
  python build_elsa_biomarkers.py --no-bioage # 只合并标志物（不调 step11）
  python build_elsa_biomarkers.py --rebuild-hrs  # 先跑 build_hrs_biomarkers 再追加（谨慎）
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_HARM, DATA_RAW                           # noqa: E402
from config_biomarker import BIOMARKER_FILE, OUT_TAB             # noqa: E402

# ---------------------------------------------------------------- 原始数据基目录
# 目录结构约定：<DATA_RAW>/ELSA。若原始文件放在别处，设置环境变量 ELSA_RAW_DIR。
DEFAULT_ELSA_RAW = str(DATA_RAW / "ELSA")
ELSA_RAW = Path(os.environ.get("ELSA_RAW_DIR", DEFAULT_ELSA_RAW))
F_NURSE = ELSA_RAW / "wave4/wave_4_nurse_data.dta"

ELSA_WAVE = 4
ELSA_BLOOD_YEAR = 2008          # 兜底；实际按 per-person visyear(2008/9)

# 标准名 → ELSA W4 实际变量名（均已一手核实自 .dta 官方标签）
ELSA_MAP = {
    "crp":        "hscrp",      # mg/L
    "fibrinogen": "cfib",       # g/L
    "wbc":        "wbc",        # ×10⁹/L
    "hba1c":      "hba1c",      # %
    "glucose":    "fglu",       # mmol/L（空腹；含哨兵 −1/−11）
    "ferritin":   "rtin",       # ng/mL
    "igf1":       "igf1",       # nmol/L
    "hgb":        "hgb",        # g/dL
    "chol":       "chol",       # mmol/L（2026-10-10 纳入 KDM）
    "hdl":        "hdl",        # mmol/L
    "ldl":        "ldl",        # mmol/L
    "trig":       "trig",       # mmol/L
    "dheas":      "dheas",      # umol/L（强衰老标志物）
    "mch":        "mch",        # pg/cell
}

# 合理性区间（同时用于剔除 fglu 的 −1/−11 哨兵；ELSA 用**负哨兵码**）
PLAUSIBLE = {
    "crp":        (0.01, 100.0),
    "fibrinogen": (0.50, 12.0),
    "wbc":        (1.0,  30.0),
    "hba1c":      (3.0,  20.0),
    "glucose":    (2.0,  30.0),
    "ferritin":   (1.0,  2000.0),
    "igf1":       (1.0,  300.0),
    "hgb":        (5.0,  22.0),
    "chol":       (1.0,  20.0),
    "hdl":        (0.30, 5.0),
    "ldl":        (0.50, 15.0),
    "trig":       (0.20, 15.0),
    "dheas":      (0.05, 30.0),
    "mch":        (15.0, 45.0),
}

BIOAGE_COLS = ["kdm_accel", "kdm_clean_accel", "bioage_accel_clean",
               "phenoage_accel", "kdm", "kdm_clean", "phenoage",
               "n_markers", "n_markers_clean"]


# ================================================================ 工具
def _read(path: Path) -> pd.DataFrame:
    import pyreadstat
    if not path.exists():
        raise FileNotFoundError(
            f"缺少 ELSA 原始文件：{path}\n"
            f"（可设环境变量 ELSA_RAW_DIR 指向 ELSA Raw_data 目录）")
    df, _ = pyreadstat.read_dta(str(path))
    return df


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(r[c]) else str(r[c])
                                       for c in df.columns) + " |")
    return "\n".join(lines)


# ================================================================ 构建 ELSA 行
def build_elsa(log: list) -> pd.DataFrame:
    df = _read(F_NURSE)
    log.append(f"— 读入 W4 护士文件：{F_NURSE.name}  n={len(df):,}  列={df.shape[1]}")

    # —— 主键 / 时间 / 人口学 ——
    idn = df["idauniq"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out = pd.DataFrame({"cohort": "ELSA", "id": idn})
    out["wave"] = ELSA_WAVE
    vy = pd.to_numeric(df.get("visyear"), errors="coerce")
    out["year"] = vy.fillna(ELSA_BLOOD_YEAR).astype("Int64")
    log.append(f"  visyear 分布：{vy.value_counts(dropna=False).to_dict()}")

    age = pd.to_numeric(df.get("confage"), errors="coerce")
    if age.isna().all():
        age = pd.to_numeric(df.get("hhage"), errors="coerce")
        log.append("  ⚠️ confage 缺失 → 退回 hhage")
    out["age"] = age
    log.append(f"  age(confage)：min={age.min()} 中位={age.median()} max={age.max()}"
               f"（90+ 在源头折叠）")

    sex = pd.to_numeric(df.get("dhsex"), errors="coerce")
    out["gender"] = sex                     # 1=男 2=女（与 HRS 口径一致）
    out["female"] = (sex == 2).astype(float).where(sex.notna())

    # —— 标志物 ——
    got = {}
    for std, raw in ELSA_MAP.items():
        if raw not in df.columns:
            log.append(f"  ⚠️ 缺列 {raw}（标准名 {std}）→ 跳过")
            continue
        v = pd.to_numeric(df[raw], errors="coerce")
        lo, hi = PLAUSIBLE[std]
        bad = int((v.notna() & ~v.between(lo, hi)).sum())
        if bad:
            log.append(f"  {std}<-{raw}: 剔除超范围/哨兵 {bad} 个（区间 {lo}–{hi}）")
        got[std] = v.where(v.between(lo, hi))
    for std, v in got.items():
        out[std] = v.values
    log.append(f"  [ELSA] 产出标志物 {len(got)}：{', '.join(got)}")

    # —— 派生量（与 HRS 对齐）——
    if {"crp", "fibrinogen"} <= set(got):
        pass  # 无 NLR（ELSA W4 无中性粒%）

    # —— 管理/来源标记 ——
    out["blood_src"] = "venous"
    out["valid_vbs"] = 1.0
    out["age_interview"] = age
    out["birth_yr"] = pd.to_numeric(df.get("dobyear"), errors="coerce")
    out["vbs_days"] = 0.0
    out["fasting"] = np.where(got.get("glucose", pd.Series(np.nan, index=df.index)).notna(),
                              1.0, np.nan)

    log.append(f"  [ELSA] 组装完成 n={len(out):,}")
    return out


# ================================================================ 合并到总表
def merge_into(bm_new: pd.DataFrame, log: list, write: bool = False) -> pd.DataFrame:
    """把 ELSA 行并入现有 harmonized_biomarkers.csv（保留 HRS 行）。"""
    if BIOMARKER_FILE.exists():
        bm_old = pd.read_csv(BIOMARKER_FILE, dtype={"id": str}, low_memory=False)
        log.append(f"— 读入现有总表：n={len(bm_old):,}  列={bm_old.shape[1]}")
        n_before = len(bm_old)
        bm_old = bm_old[bm_old["cohort"].astype(str) != "ELSA"].copy()
        if n_before != len(bm_old):
            log.append(f"  剔除旧 ELSA 行 {n_before - len(bm_old):,}（幂等重建）")
        # 丢掉旧生物年龄列，稍后统一重算
        bm_old = bm_old.drop(columns=[c for c in BIOAGE_COLS if c in bm_old.columns])
    else:
        bm_old = pd.DataFrame()
        log.append("— ⚠️ 现有总表不存在 → 将只写 ELSA（建议先跑 build_hrs_biomarkers.py）")

    if len(bm_old):
        bm_old["id"] = bm_old["id"].astype(str)
    extra = [c for c in bm_old.columns if c not in bm_new.columns]
    extra = [c for c in extra if c not in ("cohort", "id")]
    bm_old_x = bm_old.copy()
    for c in bm_new.columns:
        if c not in bm_old_x.columns:
            bm_old_x[c] = np.nan
    for c in extra:
        bm_new[c] = np.nan

    bm = pd.concat([bm_old_x, bm_new], ignore_index=True, sort=False)
    # 列顺序：主键 → age → 其余
    head = ["cohort", "id", "wave", "year", "age"]
    ordered = head + [c for c in bm.columns if c not in head]
    bm = bm[ordered]
    log.append(f"— 合并后 n={len(bm):,}（{bm['cohort'].value_counts().to_dict()}）")
    return bm


# ================================================================ QC
def qc_report(bm: pd.DataFrame, log: list) -> pd.DataFrame:
    std_cols = ["albumin", "creatinine", "glucose", "crp", "wbc", "lymph_pct", "mcv",
                "rdw", "alp", "bun", "cystatin_c", "hba1c", "fibrinogen", "hgb",
                "ferritin", "igf1", "il6", "tnfr1"]
    rows = []
    for c in std_cols:
        if c not in bm.columns:
            rows.append({"列": c, "ELSA_n": 0, "HRS_n": 0, "说明": "未产出"})
            continue
        s = pd.to_numeric(bm.loc[bm.cohort == "ELSA", c], errors="coerce")
        h = pd.to_numeric(bm.loc[bm.cohort == "HRS", c], errors="coerce")
        rows.append({"列": c, "ELSA_n": int(s.notna().sum()), "HRS_n": int(h.notna().sum()),
                     "说明": f"ELSA 中位 {s.median():.3g}" if s.notna().any() else ""})
    qc = pd.DataFrame(rows)

    try:
        from config import HARM_LONG
        lg = pd.read_csv(HARM_LONG, usecols=["cohort", "id"], low_memory=False)
        eids = set(lg.loc[lg.cohort == "ELSA", "id"].astype(str))
        sub = bm[bm.cohort == "ELSA"]
        hit = sub["id"].astype(str).isin(eids)
        log.append(f"— ELSA 行与主长表 id 对齐：命中 {hit.sum():,}/{len(sub):,} = "
                   f"{hit.mean()*100:.2f}%")
    except Exception as e:                                        # noqa: BLE001
        log.append(f"— ⚠️ 无法读取主长表做对齐诊断：{e}")
    return qc


# ================================================================ main
def main(with_bioage: bool = True) -> pd.DataFrame:
    DATA_HARM.mkdir(parents=True, exist_ok=True)
    log: list[str] = ["=" * 74,
                      "build_elsa_biomarkers —— ELSA W4 护士血样 → harmonized_biomarkers.csv",
                      "=" * 74,
                      f"原始基目录：{ELSA_RAW}"]
    elsa = build_elsa(log)
    bm = merge_into(elsa, log)

    if with_bioage:
        try:
            from step11_biologicage import compute_bioage_table
            people, qc = compute_bioage_table(bm, allow_flagged=False)
            add = people[["cohort", "id", "kdm_accel", "kdm_clean_accel",
                          "phenoage_accel", "kdm", "kdm_clean", "phenoage",
                          "n_markers", "n_markers_clean"]].copy()
            add = add.rename(columns={"kdm_clean_accel": "bioage_accel_clean"})
            bm = bm.drop(columns=[c for c in BIOAGE_COLS if c in bm.columns])
            bm = bm.merge(add, on=["cohort", "id"], how="left")
            log.append("— 生物年龄列（含 ELSA）：")
            log.append(qc.to_string(index=False))
        except Exception as e:                                    # noqa: BLE001
            log.append(f"— ⚠️ 生物年龄列计算失败（{e}）→ 仅输出标志物")

    bm.to_csv(BIOMARKER_FILE, index=False, encoding="utf-8-sig")
    log.append(f"— 已写出：{BIOMARKER_FILE}  （n={len(bm):,}，{bm.shape[1]} 列）")

    qc = qc_report(bm, log)
    (DATA_HARM / "elsa_biomarker_build_log.txt").write_text("\n".join(log), encoding="utf-8")
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    md = ["# ELSA 血样并入质控（W4, 2008/9）", "",
          "**数据来源**：ELSA W4 护士访视数据（本地 `wave_4_nurse_data.dta`）", "",
          "## 逐列覆盖（ELSA vs 现有 HRS）", "", _md_table(qc), "",
          "## 构建日志", "", "```", "\n".join(log), "```"]
    (OUT_TAB / "elsa_biomarker_build_qc.md").write_text("\n".join(md), encoding="utf-8")

    print("\n".join(log))
    print("\n—— 逐列覆盖 ——")
    print(qc.to_string(index=False))
    return bm


if __name__ == "__main__":
    main(with_bioage="--no-bioage" not in sys.argv)
