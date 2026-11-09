# -*- coding: utf-8 -*-
"""
build_charls_biomarkers.py   CHARLS 血样（2011 基线 + 2015）→ 追加进管道标准血样长表
========================================================================================
把本地 CHARLS 原始血样整理成标准行，**追加**到 `data/harmonized/harmonized_biomarkers.csv`
（保留已有 HRS / ELSA 行），使 **第三队（中国）** 进入主分析与炎症中介层。

输入（本地已有原始文件，无需联网、无需注册）
--------------------------------------------
基目录（`CHARLS_RAW_DIR` 可覆盖；默认见 DEFAULT_CHARLS_RAW）：
  · 2011charls/Blood_20140429.dta    2011 基线血样（官方 2014-04-29 版）
  · 2015charls/Blood.dta             2015 血样

主键（**两波规则不同，务必注意**）
----------------------------------
  · **2015**：`ID` 已是官方 12 位（`省2 县2 村2 家户3 个人3`）→ `id = ID.lstrip("0")`，**100% 命中**长表。
  · **2011**：`ID` 仅 **11 位**（个人序号段只有 **2 位**）→ **在倒数第 2 位前插入一个 `0`**（补足到 3 位）
    再 `lstrip("0")`。实测 **99.93%（11,839/11,847）** 命中长表。
    例：`01010410101` → `010104101001` → `10104101001`。
  · 两波都用 `lstrip("0")` 与 `step1_master._norm_id` 对齐。

时序（决定谁能进主分析）
------------------------
  · 2011 血样 = 2011 暴露**同年** → 若暴露取自 2011 则**时序不成立**（脚本仍产出，交 step12 过滤）。
  · **2015 血样 + 2011 暴露 = 滞后 4 年**（n≈9,866）✅；+2013 暴露 = 滞后 2 年（n≈10,970）✅。
  · 两波都写入 `wave`/`year`，step12 的 `POST_EXPOSURE_WINDOW` 会自动做时序筛选。

单位（**原始单位即为内部标准口径，无需换算**）
----------------------------------------------
  · newglu/bl_glu 是 **mg/dL** → ×0.05551 转 mmol/L；newcrea/bl_crea 是 **mg/dL** → ×88.42 转 μmol/L；
    newbun/bl_bun 是 mg/dL（内部口径保持 mg/dL，与 HRS 一致）。
  · 其余（CRP mg/L、HbA1c %、血脂 mg/dL、WBC ×10⁹/L、Hgb g/dL、CystatinC mg/L、MCV fL、PLT ×10⁹/L）直接用。
  · ⚠️ 血脂 HRS/CHARLS 用 mg/dL、ELSA 用 mmol/L —— **KDM 对线性缩放不变**，不影响 BA。

缺失组分
--------
CHARLS **无** 白蛋白 / ALP / RDW / 淋巴细胞% → PhenoAge 不可算；KDM 可算（≥4 项）。
`available_markers("CHARLS")` 在 config 里已登记 9 项，本脚本可再多给脂质/PLT/HCT 等扩展列。

用法
----
  python build_charls_biomarkers.py             # 构建 + 合并 + 重算生物年龄 + QC
  python build_charls_biomarkers.py --no-bioage # 只合并标志物（不调 step11）
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
from config_biomarker import BIOMARKER_FILE, OUT_TAB             # noqa: E402

# ---------------------------------------------------------------- 原始数据基目录
# 目录结构约定：<DATA_RAW>/CHARLS。若原始文件放在别处，设置环境变量 CHARLS_RAW_DIR。
DEFAULT_CHARLS_RAW = str(DATA_RAW / "CHARLS")
CHARLS_RAW = Path(os.environ.get("CHARLS_RAW_DIR", DEFAULT_CHARLS_RAW))
F_2011 = CHARLS_RAW / "2011charls/Blood_20140429.dta"
F_2015 = CHARLS_RAW / "2015charls/Blood.dta"

# ---------------------------------------------------------------- 各波映射
# 标准名 → 2011 变量名。⚠️ 2011 的 WBC/MCV/PLT 用 qc1_*，其余用 new*
MAP_2011 = {
    "wbc":        "qc1_vb002",   # ×10⁹/L（"in Thousands"）
    "mcv":        "qc1_vb006",   # fL
    "plt":        "qc1_vb009",   # ×10⁹/L
    "bun":        "newbun",      # mg/dL
    "glucose":    "newglu",      # mg/dL → 需 ×0.05551
    "creatinine": "newcrea",     # mg/dL → 需 ×88.42
    "chol":       "newcho",      # mg/dL
    "trig":       "newtg",       # mg/dL
    "hdl":        "newhdl",      # mg/dL
    "ldl":        "newldl",      # mg/dL
    "crp":        "newcrp",      # mg/L
    "hba1c":      "newhba1c",    # %
    "hct":        "qc1_vb005",   # %
    "hgb":        "qc1_vb004",   # g/dL
    "cystatin_c": "cystatinc",   # mg/L
}
# 标准名 → 2015 变量名（统一 bl_* 前缀）
MAP_2015 = {
    "wbc":        "bl_wbc",      # ×10⁹/L
    "hgb":        "bl_hgb",      # g/dL
    "hct":        "bl_hct",      # %
    "mcv":        "bl_mcv",      # fL
    "plt":        "bl_plt",      # ×10⁹/L
    "trig":       "bl_tg",       # mg/dL
    "creatinine": "bl_crea",     # mg/dL → ×88.42
    "bun":        "bl_bun",      # mg/dL
    "hdl":        "bl_hdl",      # mg/dL
    "ldl":        "bl_ldl",      # mg/dL
    "chol":       "bl_cho",      # mg/dL
    "glucose":    "bl_glu",      # mg/dL → ×0.05551
    "cystatin_c": "bl_cysc",     # mg/L
    "crp":        "bl_crp",      # mg/L
    "hba1c":      "bl_hbalc",    # %
}

# 原始→内部标准单位的乘数（build 时即应用）
UNIT_MULT = {
    "glucose":    0.05551,       # mg/dL → mmol/L
    "creatinine": 88.42,         # mg/dL → μmol/L
}

# 合理性区间（**换算后**的内部口径）→ 一并剔除特殊码/录入错误
PLAUSIBLE = {
    "wbc":        (0.5,  30.0),
    "hgb":        (3.0,  25.0),
    "hct":        (10.0, 70.0),
    "mcv":        (40.0, 150.0),
    "plt":        (5.0,  1200.0),
    "trig":       (10.0, 1500.0),
    "creatinine": (20.0, 2000.0),     # μmol/L
    "bun":        (1.0,  150.0),
    "hdl":        (5.0,  150.0),
    "ldl":        (10.0, 500.0),
    "chol":       (50.0, 600.0),
    "glucose":    (2.0,  33.0),       # mmol/L（mg/dL 20–600）
    "cystatin_c": (0.2,  10.0),
    "crp":        (0.01, 300.0),
    "hba1c":      (3.0,  20.0),
}

# 特殊码（CHARLS 常见缺失码）—— 绝不作为 0 使用
SPECIAL_CODES = [999, 9999, 99999, -1, -9, -99, -999]

BIOAGE_COLS = ["kdm_accel", "kdm_clean_accel", "bioage_accel_clean",
               "phenoage_accel", "kdm", "kdm_clean", "phenoage",
               "n_markers", "n_markers_clean"]


# ================================================================ 工具
def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"缺少 CHARLS 原始文件：{path}\n"
            f"（可设环境变量 CHARLS_RAW_DIR 指向 CHARLS 的 Raw_data 目录）")
    df, _ = pyreadstat.read_dta(str(path))
    return df


def norm_id_2011(raw: pd.Series) -> pd.Series:
    """2011 血样 ID（11 位）→ 官方 12 位：**在倒数第 2 位前插入一个 `0`**，再去前导零。

    例：`01010410101` → `010104101001` → `10104101001`。实测命中长表 99.93%。
    """
    s = raw.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    fixed = s.str.slice(0, -2) + "0" + s.str.slice(-2)
    return fixed.str.lstrip("0")


def norm_id_2015(raw: pd.Series) -> pd.Series:
    """2015 血样 ID 已是官方 12 位 → 仅去前导零（100% 命中长表）。"""
    s = raw.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return s.str.lstrip("0")


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(r[c]) else str(r[c])
                                       for c in df.columns) + " |")
    return "\n".join(lines)


def attach_age(bm: pd.DataFrame, log: list) -> pd.DataFrame:
    """从主长表按 (cohort,id,wave) 取实龄。

    ⚠️ CHARLS 血样文件**本身不含年龄** → 必须回长表取；
    血样波次与长表波次一致（2011=wave1、2015=wave3），故按 (id, wave) 精确对齐。
    长表命中者用其 `age`；未命中者退回「出生年→年龄」的粗口径（若有 dobyear）。
    """
    from config import HARM_LONG
    lg = pd.read_csv(HARM_LONG, usecols=["cohort", "id", "wave", "age"],
                     low_memory=False)
    lg = lg[lg.cohort == "CHARLS"].copy()
    lg["id"] = lg["id"].astype(str)
    lg = lg.dropna(subset=["age"]).drop_duplicates(["id", "wave"])
    bm = bm.merge(lg[["id", "wave", "age"]], on=["id", "wave"], how="left",
                  suffixes=("_raw", ""))
    if "age_raw" in bm.columns:
        bm = bm.drop(columns=["age_raw"])
    hit = bm["age"].notna()
    log.append(f"  [age] 由长表按 (id,wave) 取龄：命中 {hit.sum():,}/{len(bm):,} = "
               f"{hit.mean()*100:.2f}%")
    return bm


# ================================================================ 单波构建
def _build_wave(df: pd.DataFrame, mapping: dict, ids: pd.Series,
                wave: int, year: int, log: list) -> pd.DataFrame:
    out = pd.DataFrame({"cohort": "CHARLS", "id": ids.values})
    out["wave"] = wave
    out["year"] = year

    got = {}
    for std, raw in mapping.items():
        if raw not in df.columns:
            log.append(f"  [{wave}] ⚠️ 缺列 {raw}（标准名 {std}）→ 跳过")
            continue
        v = pd.to_numeric(df[raw], errors="coerce")
        # 特殊码 → NaN
        v = v.where(~v.isin(SPECIAL_CODES))
        # 单位换算
        if std in UNIT_MULT:
            v = v * UNIT_MULT[std]
        # 合理性区间
        lo, hi = PLAUSIBLE[std]
        bad = int((v.notna() & ~v.between(lo, hi)).sum())
        if bad:
            log.append(f"  [{wave}] {std}<-{raw}: 剔除超范围 {bad} 个（区间 {lo}–{hi}）")
        got[std] = v.where(v.between(lo, hi))

    for std, v in got.items():
        out[std] = v.values
    log.append(f"  [{wave}] n={len(out):,}  产出标志物 {len(got)}：{', '.join(got)}")

    # 来源标记（与其它队列对齐）
    out["blood_src"] = "venous"
    out["valid_vbs"] = 1.0
    fast = df.get("bl_fasting", df.get("qc1_va003"))
    if fast is not None:
        out["fasting"] = pd.to_numeric(fast, errors="coerce").where(
            lambda x: x.isin([1, 2, 0]), np.nan).values
    return out


# ================================================================ 合并到总表
def merge_into(bm_new: pd.DataFrame, log: list) -> pd.DataFrame:
    if BIOMARKER_FILE.exists():
        bm_old = pd.read_csv(BIOMARKER_FILE, dtype={"id": str}, low_memory=False)
        log.append(f"— 读入现有总表：n={len(bm_old):,}  列={bm_old.shape[1]}")
        n0 = len(bm_old)
        bm_old = bm_old[bm_old["cohort"].astype(str) != "CHARLS"].copy()
        if n0 != len(bm_old):
            log.append(f"  剔除旧 CHARLS 行 {n0 - len(bm_old):,}（幂等重建）")
        bm_old = bm_old.drop(columns=[c for c in BIOAGE_COLS if c in bm_old.columns])
    else:
        bm_old = pd.DataFrame()
        log.append("— ⚠️ 现有总表不存在 → 将只写 CHARLS")

    if len(bm_old):
        bm_old["id"] = bm_old["id"].astype(str)
    # 补齐列：任一侧缺的列用 NaN
    for c in bm_new.columns:
        if c not in bm_old.columns:
            bm_old[c] = np.nan
    for c in bm_old.columns:
        if c not in bm_new.columns:
            bm_new[c] = np.nan

    bm = pd.concat([bm_old, bm_new], ignore_index=True, sort=False)
    head = ["cohort", "id", "wave", "year", "age"]
    bm = bm[head + [c for c in bm.columns if c not in head]]
    log.append(f"— 合并后 n={len(bm):,}（{bm['cohort'].value_counts().to_dict()}）")
    return bm


# ================================================================ QC
def qc_report(bm: pd.DataFrame, log: list) -> pd.DataFrame:
    std_cols = ["albumin", "alp", "bun", "crp", "creatinine", "cystatin_c", "glucose",
                "hgb", "lymph_pct", "mcv", "rdw", "wbc", "ferritin", "hba1c",
                "chol", "hdl", "ldl", "trig", "plt", "hct", "fibrinogen", "igf1"]
    rows = []
    sub = bm[bm.cohort == "CHARLS"]
    for c in std_cols:
        if c not in bm.columns:
            rows.append({"列": c, "CHARLS_n": 0, "说明": "未产出"})
            continue
        s = pd.to_numeric(sub[c], errors="coerce")
        rows.append({"列": c, "CHARLS_n": int(s.notna().sum()),
                     "说明": f"中位 {s.median():.3g}" if s.notna().any() else ""})
    qc = pd.DataFrame(rows)

    try:
        from config import HARM_LONG
        lg = pd.read_csv(HARM_LONG, usecols=["cohort", "id"], low_memory=False)
        cids = set(lg.loc[lg.cohort == "CHARLS", "id"].astype(str))
        hit = sub["id"].astype(str).isin(cids)
        log.append(f"— CHARLS 行与主长表 id 对齐：命中 {hit.sum():,}/{len(sub):,} = "
                   f"{hit.mean()*100:.2f}%")
    except Exception as e:                                        # noqa: BLE001
        log.append(f"— ⚠️ 无法读取主长表做对齐诊断：{e}")
    return qc


# ================================================================ main
def main(with_bioage: bool = True) -> pd.DataFrame:
    DATA_HARM.mkdir(parents=True, exist_ok=True)
    log: list[str] = ["=" * 74,
                      "build_charls_biomarkers —— CHARLS 血样 → harmonized_biomarkers.csv",
                      "=" * 74,
                      f"原始基目录：{CHARLS_RAW}"]

    # —— 2011 ——
    d11 = _read(F_2011)
    ids11 = norm_id_2011(d11["ID"])
    log.append(f"— 读入 2011 血样：{F_2011.name}  n={len(d11):,}")
    log.append(f"  id 规则：倒数第 2 位前插 0 后 lstrip('0')"
               f"（示例 {d11['ID'].iloc[0]} → {ids11.iloc[0]}）")
    w11 = _build_wave(d11, MAP_2011, ids11, wave=1, year=2011, log=log)

    # —— 2015 ——
    d15 = _read(F_2015)
    ids15 = norm_id_2015(d15["ID"])
    log.append(f"— 读入 2015 血样：{F_2015.name}  n={len(d15):,}")
    log.append(f"  id 规则：原样 lstrip('0')（已是官方 12 位）")
    w15 = _build_wave(d15, MAP_2015, ids15, wave=3, year=2015, log=log)

    new = pd.concat([w11, w15], ignore_index=True, sort=False)
    new = attach_age(new, log)
    bm = merge_into(new, log)

    if with_bioage:
        try:
            from step11_biologicage import compute_bioage_table
            people, qc = compute_bioage_table(bm, allow_flagged=False)
            add = people[["cohort", "id", "wave", "kdm_accel", "kdm_clean_accel",
                          "phenoage_accel", "kdm", "kdm_clean", "phenoage",
                          "n_markers", "n_markers_clean"]].copy()
            add = add.rename(columns={"kdm_clean_accel": "bioage_accel_clean"})
            # 生物年龄按 (cohort,id) 唯一 → 只留 wave 最小的一行合并；此处直接按 id 合并
            add = add.sort_values(["cohort", "id", "wave"]).drop_duplicates(
                ["cohort", "id", "wave"])
            bm = bm.drop(columns=[c for c in BIOAGE_COLS if c in bm.columns])
            bm = bm.merge(add, on=["cohort", "id", "wave"], how="left")
            log.append("— 生物年龄列（含 CHARLS）：")
            log.append(qc.to_string(index=False))
        except Exception as e:                                    # noqa: BLE001
            log.append(f"— ⚠️ 生物年龄列计算失败（{e}）→ 仅输出标志物")

    bm.to_csv(BIOMARKER_FILE, index=False, encoding="utf-8-sig")
    log.append(f"— 已写出：{BIOMARKER_FILE}  （n={len(bm):,}，{bm.shape[1]} 列）")

    qc = qc_report(bm, log)
    (DATA_HARM / "charls_biomarker_build_log.txt").write_text("\n".join(log), encoding="utf-8")
    OUT_TAB.mkdir(parents=True, exist_ok=True)
    md = ["# CHARLS 血样并入质控（2011 基线 + 2015）", "",
          "**数据来源**：CHARLS 官方 Blood 数据集（本地 `.dta`）", "",
          "## 逐列覆盖（CHARLS）", "", _md_table(qc), "",
          "## 构建日志", "", "```", "\n".join(log), "```"]
    (OUT_TAB / "charls_biomarker_build_qc.md").write_text("\n".join(md), encoding="utf-8")

    print("\n".join(log))
    print("\n—— 逐列覆盖 ——")
    print(qc.to_string(index=False))
    return bm


if __name__ == "__main__":
    main(with_bioage="--no-bioage" not in sys.argv)
