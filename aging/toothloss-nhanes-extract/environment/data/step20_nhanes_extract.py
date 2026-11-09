#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
step20_nhanes_extract.py
========================
A 档同源加强：NHANES 独立第四队列 —— 数据抽取与变量构建。

目标（与主线「缺牙 -> 炎症 -> 生物衰老」同源，但用临床测量暴露）：
  暴露：
    - mPD  平均探诊深度 (mm)      <- OHXPER 每牙 6 位点的 PCD 列
    - mLA  平均附着丧失 (mm)      <- OHXPER 每牙 6 位点的 LAD 列
    - nTeeth 连续余留牙数 (0-28)  <- OHXDEN 的 OHXnnTC（1/2/3 = 有牙）
    - edent 无牙颌 (nTeeth == 0)
  结局（炎症/营养）：
    - WBC  白细胞 (10^9/L)        <- CBC  LBXWBCSI
    - NLR  中性粒/淋巴比值        <- CBC  LBDNENO / LBDLYMNO
    - ALB  血清白蛋白 (g/dL)      <- BIOPRO LBXSAL
    - CRP  C 反应蛋白 (mg/L)      <- CRP_F(LBXCRP, mg/dL) 或 HSCRP_I(LBXHSCRP, mg/L)
  协变量：age, female, edu, married, race, bmi?（BMI 需 BMX，本地暂缺，跳过）

支持周期：
  G = 2011-2012（本地）
  H = 2013-2014（本地）
  I = 2015-2016（CRP 可用；牙周/牙列需另下 OHXPER_I/OHXDEN_I）
  F = 2009-2010（仅 CRP_F 本地，无牙周，故不用于主分析）

⚠️ 已核实的关键限制：
  NHANES 2011-2014 无公开 CRP（CRP_G / CRP_H 均 404）。
  故主分析（G+H）用 WBC/NLR/ALB 作炎症结局；CRP 仅在 I 周期（或 F 周期）单独做。

⚠️ OHXDEN 编码陷阱：
  OHXnnTC: 1=原发牙, 2=已修复, 3=未修复龋, 4=缺失, 5=埋伏牙
  => 有牙 = {1,2,3}；不是「含 1 即有牙」（那样会得到中位 0 的荒谬结果）

输出：
  data/harmonized/nhanes_oral_inflammation.csv   （分析用宽表）
  output/tables/nhanes_build_log.txt             （自检日志）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parent.parent          # .../02_数据分析
RAW = ROOT / "data" / "raw" / "NHANES"
HARM = ROOT / "data" / "harmonized"
TAB = ROOT / "output" / "tables"
HARM.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)

LOG: list[str] = []


def log(msg: str) -> None:
    print(msg)
    LOG.append(msg)


def load(name: str) -> pd.DataFrame | None:
    """读 XPT；不存在或疑似 404 页面时返回 None。"""
    p = RAW / f"{name}.XPT"
    if not p.exists():
        return None
    if p.stat().st_size < 10_000:      # 404 页面恒为 1245 / 20905 字节
        return None
    try:
        return pd.read_sas(p, format="xport")
    except Exception as exc:           # noqa: BLE001
        log(f"  [warn] 读取 {name} 失败: {exc}")
        return None


def num(df: pd.DataFrame, col: str) -> pd.Series:
    """安全转数值；列不存在时返回全 NaN。"""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


# ---------------------------------------------------------------- 牙周
def build_periodontal(per: pd.DataFrame) -> pd.DataFrame:
    """从 OHXPER 提取 mPD / mLA。位点值 0-15 mm 有效，>15 记为缺失。"""
    pdc = [c for c in per.columns if c.endswith("PCD")]
    lac = [c for c in per.columns if c.endswith("LAD")]

    out = pd.DataFrame({"SEQN": per["SEQN"].astype(float)})

    if pdc:
        m = per[pdc].apply(pd.to_numeric, errors="coerce")
        m = m.mask(m > 15)             # 99 = 缺失牙位
        out["mPD"] = m.mean(axis=1)
        out["nPD_sites"] = m.notna().sum(axis=1)
        # 探诊深度 >=4 mm 的位点比例（常用牙周炎负荷指标）
        out["pctPD4"] = (m >= 4).sum(axis=1) / m.notna().sum(axis=1).replace(0, np.nan)
    else:
        out["mPD"] = np.nan
        out["nPD_sites"] = np.nan
        out["pctPD4"] = np.nan

    if lac:
        m = per[lac].apply(pd.to_numeric, errors="coerce")
        m = m.mask(m > 15)
        out["mLA"] = m.mean(axis=1)
        out["nLA_sites"] = m.notna().sum(axis=1)
    else:
        out["mLA"] = np.nan
        out["nLA_sites"] = np.nan

    # 位点太少的个体置缺失（保证 mPD 稳定）
    out.loc[out["nPD_sites"] < 12, ["mPD", "pctPD4"]] = np.nan
    out.loc[out["nLA_sites"] < 12, "mLA"] = np.nan
    return out


# ---------------------------------------------------------------- 牙列
def build_dentition(den: pd.DataFrame) -> pd.DataFrame:
    """从 OHXDEN 计算连续余留牙数（0-28）与无牙颌。"""
    tc = [
        c
        for c in den.columns
        if c.startswith("OHX") and c.endswith("TC") and c[3:5].isdigit()
    ]
    out = pd.DataFrame({"SEQN": den["SEQN"].astype(float)})
    if not tc:
        out["nTeeth"] = np.nan
        out["nExamined"] = np.nan
        out["edent"] = np.nan
        return out

    v = den[tc].apply(pd.to_numeric, errors="coerce")
    n_teeth = v.isin([1, 2, 3]).sum(axis=1)        # ⚠️ 有牙 = 1/2/3
    n_exam = v.isin([1, 2, 3, 4]).sum(axis=1)
    n_teeth = n_teeth.where(n_exam >= 20)          # 检查牙数不足 -> 缺失
    out["nTeeth"] = n_teeth
    out["nExamined"] = n_exam
    out["edent"] = (n_teeth == 0).astype(float).where(n_teeth.notna())
    return out


# ---------------------------------------------------------------- 炎症
def build_inflammation(cbc: pd.DataFrame, bio: pd.DataFrame, cycle: str) -> pd.DataFrame:
    out = pd.DataFrame({"SEQN": cbc["SEQN"].astype(float)})
    out["WBC"] = num(cbc, "LBXWBCSI")
    neu, lym = num(cbc, "LBDNENO"), num(cbc, "LBDLYMNO")
    out["NLR"] = neu / lym.replace(0, np.nan)

    b = pd.DataFrame({"SEQN": bio["SEQN"].astype(float)})
    b["ALB"] = num(bio, "LBXSAL")
    out = out.merge(b, on="SEQN", how="outer")

    # CRP：按周期取不同文件 / 不同单位
    crp = None
    if cycle == "I":
        d = load("HSCRP_I")
        if d is not None and "LBXHSCRP" in d.columns:
            crp = pd.DataFrame(
                {"SEQN": d["SEQN"].astype(float),
                 "CRP": pd.to_numeric(d["LBXHSCRP"], errors="coerce")}
            )
            log("  CRP <- HSCRP_I.LBXHSCRP (mg/L)")
    elif cycle == "F":
        d = load("CRP_F")
        if d is not None and "LBXCRP" in d.columns:
            v = pd.to_numeric(d["LBXCRP"], errors="coerce")
            crp = pd.DataFrame({"SEQN": d["SEQN"].astype(float), "CRP": v * 10.0})
            log("  CRP <- CRP_F.LBXCRP (mg/dL -> mg/L, x10)")
    if crp is not None:
        out = out.merge(crp, on="SEQN", how="outer")
    else:
        out["CRP"] = np.nan
    return out


# ---------------------------------------------------------------- 协变量
def build_covariates(dem: pd.DataFrame, cycle: str) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "SEQN": dem["SEQN"].astype(float),
            "age": num(dem, "RIDAGEYR"),
            "female": (num(dem, "RIAGENDR") == 2).astype(float),
            "race": num(dem, "RIDRETH3").fillna(num(dem, "RIDRETH1")),
        }
    )
    # 教育：DMDEDUC2 成年人 1-5；转受教育年数近似
    edu_map = {1: 8, 2: 10, 3: 12, 4: 14, 5: 16}
    out["edu_years"] = num(dem, "DMDEDUC2").map(edu_map)
    # 婚姻：DMDMARTL 1=已婚
    out["married"] = (num(dem, "DMDMARTL") == 1).astype(float).where(
        num(dem, "DMDMARTL").notna()
    )
    # 权重：2 年 MEC 权重
    w = num(dem, "WTMEC2YR")
    out["wt_mec"] = w.where(w > 0)
    out.loc[out["age"] < 20, "edu_years"] = np.nan     # 20 岁以下教育编码不同
    return out


# ---------------------------------------------------------------- 主流程
CYCLE_FILES = {
    "G": {"year": "2011-2012", "dem": "DEMO_G", "per": "OHXPER_G",
          "den": "OHXDEN_G", "cbc": "CBC_G", "bio": "BIOPRO_G"},
    "H": {"year": "2013-2014", "dem": "DEMO_H", "per": "OHXPER_H",
          "den": "OHXDEN_H", "cbc": "CBC_H", "bio": "BIOPRO_H"},
}


def extract_cycle(cyc: str) -> pd.DataFrame | None:
    spec = CYCLE_FILES[cyc]
    log(f"\n=== 周期 {cyc} ({spec['year']}) ===")
    dem = load(spec["dem"])
    per = load(spec["per"])
    den = load(spec["den"])
    cbc = load(spec["cbc"])
    bio = load(spec["bio"])
    if any(x is None for x in (dem, per, den, cbc, bio)):
        miss = [k for k, x in zip(["dem", "per", "den", "cbc", "bio"],
                                  [dem, per, den, cbc, bio]) if x is None]
        log(f"  [skip] 缺文件: {miss}")
        return None

    df = build_periodontal(per)
    log(f"  牙周: mPD 非空 {df['mPD'].notna().sum():,} | mLA 非空 {df['mLA'].notna().sum():,}")

    dd = build_dentition(den)
    log(f"  牙列: 余留牙数非空 {dd['nTeeth'].notna().sum():,} | "
        f"中位 {dd['nTeeth'].median():.0f} | 无牙颌 {int((dd['edent'] == 1).sum()):,}")

    infl = build_inflammation(cbc, bio, cyc)
    log(f"  炎症: WBC {infl['WBC'].notna().sum():,} | NLR {infl['NLR'].notna().sum():,} | "
        f"ALB {infl['ALB'].notna().sum():,}")

    cov = build_covariates(dem, cyc)
    out = (df.merge(dd, on="SEQN", how="outer")
             .merge(infl, on="SEQN", how="outer")
             .merge(cov, on="SEQN", how="outer"))
    out["cycle"] = cyc
    out["year"] = spec["year"]
    log(f"  合并后: {out.shape[0]:,} 行 x {out.shape[1]} 列")
    return out


def main() -> int:
    log("=" * 64)
    log("step20_nhanes_extract.py — NHANES 牙周/牙列 -> 炎症 变量构建")
    log("=" * 64)

    frames = []
    for cyc in ("G", "H"):
        d = extract_cycle(cyc)
        if d is not None:
            frames.append(d)

    if not frames:
        log("\n[FAIL] 没有任何周期成功。")
        return 1

    all_df = pd.concat(frames, ignore_index=True)
    all_df = all_df.sort_values(["cycle", "SEQN"]).reset_index(drop=True)

    out_csv = HARM / "nhanes_oral_inflammation.csv"
    all_df.to_csv(out_csv, index=False, encoding="utf-8-sig")

    log("\n" + "-" * 64)
    log(f"落盘: {out_csv}")
    log(f"总行数: {len(all_df):,}")

    # 分析样本（50 岁及以上，牙周 + 牙列 + WBC 齐备）
    a = all_df[(all_df["age"] >= 50)
               & all_df["mPD"].notna()
               & all_df["nTeeth"].notna()
               & all_df["WBC"].notna()]
    log(f"分析样本(>=50, 有牙周+牙列+WBC): {len(a):,}")
    for c in ("H", "G"):
        s = a[a["cycle"] == c]
        log(f"  周期 {c}: {len(s):,}")
    log("\n描述(分析样本):")
    for c in ("mPD", "mLA", "nTeeth", "WBC", "NLR", "ALB"):
        v = pd.to_numeric(a[c], errors="coerce")
        if v.notna().sum():
            log(f"  {c:7s} n={v.notna().sum():5,}  中位={v.median():7.3f}  "
                f"IQR=({v.quantile(.25):.2f}, {v.quantile(.75):.2f})")

    (TAB / "nhanes_build_log.txt").write_text("\n".join(LOG), encoding="utf-8")
    log(f"\n日志: {TAB / 'nhanes_build_log.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
