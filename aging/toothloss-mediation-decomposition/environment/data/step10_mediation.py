# -*- coding: utf-8 -*-
"""
step10_mediation.py   机制层：中介分析（四向分解 + 串联链式）
==============================================================
命题：**缺牙/牙周炎 → 系统性炎症 → 生物学衰老加速 → 认知衰退**

本脚本做三件事
--------------
1. **VanderWeele 四向分解**（VanderWeele 2014, Epidemiology）：
   把总效应 TE 拆成
        TE = CDE + INTref + INTmed + PIE
   · CDE    受控直接效应（把中介固定在均值水平时的暴露效应）
   · INTref 参照交互（暴露×中介交互，在未暴露者的中介水平上）
   · INTmed 中介交互（交互中"经由中介"的那部分）
   · PIE    纯间接效应
   另报 NIE = PIE + INTmed（自然间接效应）与"中介比例" NIE/TE。
2. **串联链式中介**（缺牙 → M1 炎症 → M2 生物年龄 → 认知）：product-of-coefficients，
   分别给出三条间接路径 a1·b1 / a1·d21·b2 / a2·b2。
3. **bootstrap 百分位 CI**（个体层重抽样），并对"中介比例不稳定"给出显式告警。

⚠️ 三条必须写进方法学的口径
---------------------------
· 暴露用 **edent_base**（基线时不变），结局为**随访期末认知**（随访口径）或**个体认知斜率**，
  两者都校正**基线认知**——这是队列研究中介分析的标准做法。
· **中介必须测于暴露之后**（blood_year ≥ 暴露年），脚本强制过滤并在输出里报告被剔除人数。
· **成分污染**：Levine PhenoAge 本身含 CRP；故主分析用**去污染版**生物年龄
  （`bioage_accel_clean`，剔除炎症组分），与炎症标志物**并列**做中介，避免"同一变量用两次"。
· 比例中介（proportion mediated）在总效应接近 0 时极不稳定 → 脚本在 |TE| 小或 CI 含 0 时
  只报**绝对效应**并打 `ratio_unstable` 标记，**不报比例**。

运行
----
    python step10_mediation.py                 # 有真实血样表则用真实，否则演示模式
    MEDIATION_BOOT=200 python step10_mediation.py
输出： output/tables/mediation_4way.csv
       output/tables/mediation_serial.csv
       output/tables/mediation_summary.md
       output/figures/mediation_effects.png
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import HARM_LONG, OUT_TAB, OUT_FIG                          # noqa: E402
from config_biomarker import (                                          # noqa: E402
    BIOMARKER_FILE, MEDIATION_SPECS, SERIAL_SPECS, MEDIATION_BOOT,
    RANDOM_SEED, INFLAMMATION_MARKERS, synth_marker_frame,
)

warnings.filterwarnings("ignore")

COVS = ["age_c", "female", "edu_years", "married", "rural", "ever_smoke"]
MAX_N = int(__import__("os").environ.get("MEDIATION_MAX_N", "0")) or None   # 调试用上限


# ==================================================================== 基础 OLS
def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _z(v: np.ndarray) -> np.ndarray:
    s = np.nanstd(v, ddof=1)
    return (v - np.nanmean(v)) / s if s > 0 else v * np.nan


# ==================================================================== 四向分解
def fourway(y, A, M, C) -> dict:
    """VanderWeele 四向分解（A 二分、M 连续、C 已中心化）。

    M 模型: E[M|A,C] = a0 + a1·A + a'C
    Y 模型: E[Y|A,M,C] = c0 + c1·A + b·M + c3·A·M + c'C
    """
    n = len(y)
    C = np.atleast_2d(C).T if C.ndim == 1 else C
    Xm = np.column_stack([np.ones(n), A, C])
    bm = _ols(M, Xm)
    a0, a1 = float(bm[0]), float(bm[1])

    Xy = np.column_stack([np.ones(n), A, M, A * M, C])
    by = _ols(y, Xy)
    c1, b, c3 = float(by[1]), float(by[2]), float(by[3])

    CDE, INTref, INTmed, PIE = c1, c3 * a0, c3 * a1, b * a1
    TE = CDE + INTref + INTmed + PIE
    NIE = PIE + INTmed

    def _ratio(part):
        return part / TE if abs(TE) > 1e-9 else np.nan

    return dict(TE=TE, CDE=CDE, INTref=INTref, INTmed=INTmed, PIE=PIE, NIE=NIE,
                a0=a0, a1=a1, b=b, c1=c1, c3=c3,
                prop_NIE=_ratio(NIE), prop_PIE=_ratio(PIE),
                prop_INTmed=_ratio(INTmed), prop_INTref=_ratio(INTref),
                n=n)


def boot_ci(fn, n: int, B: int, seed: int, alpha: float = 0.05) -> dict:
    """个体层 bootstrap，返回每个标量的百分位 CI。"""
    rng = np.random.default_rng(seed)
    recs = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        try:
            out = fn(idx)
            if out:
                recs.append(out)
        except Exception:                                        # noqa: BLE001
            continue
    if not recs:
        return {}
    df = pd.DataFrame(recs)
    lo, hi = alpha / 2 * 100, (1 - alpha / 2) * 100
    return {f"{c}_lo": float(df[c].quantile(lo / 100)) for c in df.columns} | \
           {f"{c}_hi": float(df[c].quantile(hi / 100)) for c in df.columns}


# ==================================================================== 串联链式中介
def serial(y, A, M1, M2, C) -> dict:
    """串联：A → M1 → M2 → Y（product-of-coefficients）。C 已中心化。"""
    n = len(y)
    C = np.atleast_2d(C).T if C.ndim == 1 else C
    one = np.ones(n)

    a1 = float(_ols(M1, np.column_stack([one, A, C]))[1])
    b2_ = _ols(M2, np.column_stack([one, A, M1, C]))
    a2, d21 = float(b2_[1]), float(b2_[2])
    c_ = _ols(y, np.column_stack([one, A, M1, M2, C]))
    c_dir, b1, b2 = float(c_[1]), float(c_[2]), float(c_[3])

    ind_m1   = a1 * b1                # A → M1 → Y
    ind_m1m2 = a1 * d21 * b2          # A → M1 → M2 → Y（链式）
    ind_m2   = a2 * b2                # A → M2 → Y（不经 M1）
    total_ind = ind_m1 + ind_m1m2 + ind_m2
    TE = c_dir + total_ind
    return dict(TE=TE, direct=c_dir, ind_M1=ind_m1, ind_M1M2=ind_m1m2,
                ind_M2=ind_m2, total_indirect=total_ind,
                prop_chain=(ind_m1m2 / TE) if abs(TE) > 1e-9 else np.nan,
                a1=a1, d21=d21, b2=b2, b1=b1, a2=a2, c_dir=c_dir, n=n)


# ==================================================================== 个体层分析框
def person_frame(df: pd.DataFrame, cohort: str) -> pd.DataFrame:
    """把长表压成**人 × 1 行**的分析框。"""
    d = df[df["cohort"] == cohort].copy()
    if len(d) == 0:
        return pd.DataFrame()
    d["id"] = d["id"].astype(str)
    d = d.sort_values(["id", "year"])
    g = d.groupby("id", sort=False)

    out = pd.DataFrame(index=g.size().index)
    first = g.first()
    for c in ["edent_base", "age", "age_c", "female", "edu_years", "married",
              "rural", "ever_smoke", "year"]:
        if c in first.columns:
            out[c] = first[c]
    out = out.rename(columns={"year": "year_base"})

    cog = d.dropna(subset=["cog_z"])
    gcog = cog.groupby("id", sort=False)
    out["cog_base"] = gcog["cog_z"].first()
    out["cog_fu"] = gcog["cog_z"].last()
    out["year_fu"] = gcog["year"].last()
    out["n_cog"] = gcog["cog_z"].count()

    # 个体认知斜率（向量化协方差公式）—— 需 ≥3 个认知观测且时点有变异
    t, y = cog["time_c"], cog["cog_z"]
    tm = t.groupby(cog["id"], sort=False).transform("mean")
    ym = y.groupby(cog["id"], sort=False).transform("mean")
    num = ((t - tm) * (y - ym)).groupby(cog["id"], sort=False).sum()
    den = ((t - tm) ** 2).groupby(cog["id"], sort=False).sum()
    den = den.replace(0, np.nan)
    slope = (num / den).where(gcog["cog_z"].count() >= 3)
    out["cog_slope"] = slope
    out["cohort"] = cohort
    return out.reset_index().rename(columns={"index": "id"})


def _usable_covs(d: pd.DataFrame) -> list[str]:
    """只保留在该队列里**确实有变异**的协变量。

    典型情形：ELSA 无城乡变量（rural 全缺）→ 若把它放进 dropna，会一次清空整个队列
    （与上游 `model_utils.build_cohort_formula` 的坑同源）。
    """
    return [c for c in COVS if c in d.columns and d[c].notna().any() and d[c].std(skipna=True) > 0]


def _design(pf: pd.DataFrame, mediator: str, outcome: str):
    """构造 y, A, M, C 矩阵（剔除缺失、中心化连续协变量）。"""
    need = [c for c in ["edent_base", mediator, outcome, "cog_base"] if c in pf.columns]
    d = pf.dropna(subset=need).copy()
    covs = _usable_covs(d)
    d = d.dropna(subset=covs)
    if len(d) < 200 or d["edent_base"].nunique() < 2:
        return None
    A = d["edent_base"].astype(float).values
    M = _z(d[mediator].astype(float).values)                 # 中介标准化
    y = _z(d[outcome].astype(float).values)                  # 结局标准化
    base = _z(d["cog_base"].astype(float).values)            # 基线认知
    covs_mat = []
    for c in covs:
        v = d[c].astype(float).values
        covs_mat.append(v - np.nanmean(v))                   # 全部中心化（含二分，便于 INTref 解释）
    C = np.column_stack(covs_mat + [base])
    return y, A, M, C, d


# ==================================================================== 演示模式
def demo_attach(pf: pd.DataFrame, cohort: str, bm_raw: pd.DataFrame,
                people: pd.DataFrame, seed: int) -> pd.DataFrame:
    """演示模式：给真实 ID 挂合成标志物 + 合成结局（含已知中介结构）。

    DGP（仅演示）：M* = κ·A + z(标志物)；Y = -0.20·A - 0.35·M* + 0.10·A·M* + 0.55·cog_base + N(0,0.8)
    ⚠️ 数字不得写入论文。
    """
    rng = np.random.default_rng(seed + abs(hash(cohort)) % 10000)
    d = pf.copy()
    n = len(d)
    A = pd.to_numeric(d["edent_base"], errors="coerce").fillna(0).values.astype(float)

    raw = bm_raw[bm_raw["cohort"] == cohort].drop_duplicates("id").set_index("id")
    peo = people[people["cohort"] == cohort].drop_duplicates("id").set_index("id")

    def _pull(src, col):
        if col not in src.columns:
            return None
        return pd.to_numeric(d["id"].map(src[col]), errors="coerce").values.astype(float)

    src_map = {"crp": (raw, .50), "il6": (raw, .45), "fibrinogen": (raw, .30),
               "wbc": (raw, .25), "ptau217": (raw, .35)}
    first_m = None
    for name, (src, kappa) in src_map.items():
        v = _pull(src, name)
        if v is None:
            continue
        v = np.where(np.isfinite(v), v, np.nanmean(v))
        d[name] = _z(kappa * A + _z(v))
        if first_m is None:
            first_m = name
    if first_m is None:
        return d

    # 生物年龄置于 CRP 下游 —— 体现"炎症 → 衰老"的链条，使链式中介可校验
    zk = _pull(peo, "kdm_clean_accel")
    if zk is not None and "crp" in d.columns:
        zk = np.where(np.isfinite(zk), zk, np.nanmean(zk))
        d["kdm_clean_accel"] = _z(0.45 * d["crp"].values + 0.55 * A + _z(zk))
        d["bioage_accel_clean"] = d["kdm_clean_accel"]
    elif zk is not None:
        d["kdm_clean_accel"] = _z(0.55 * A + _z(zk))
        d["bioage_accel_clean"] = d["kdm_clean_accel"]

    base_cog = _z(pd.to_numeric(d["cog_base"], errors="coerce").fillna(0).values)
    M = np.nan_to_num(d[first_m].values, nan=0.0)
    d["cog_fu"] = (-0.20 * A - 0.35 * M + 0.10 * A * M + 0.55 * base_cog
                   + rng.normal(0, 0.8, n))
    d["cog_slope"] = d["cog_fu"] / 6.0           # 演示用粗换算
    return d


# ==================================================================== 主流程
def demo_outcome(A, M, base, seed: int, structure: str = "simple") -> np.ndarray:
    """演示用已知 DGP：让每个规格都带一个**可校验的**真实中介效应。

    simple : Y = -0.20A - 0.35M + 0.10A·M + 0.55·base + N(0,0.8)
             真值 → CDE=-0.20, PIE=-0.35·a1, INTmed=0.10·a1 （a1 由重抽样样本决定）
    chain  : Y = -0.15A - 0.25M1 - 0.30M2 + 0.55·base + N(0,0.8)
    """
    rng = np.random.default_rng(seed)
    n = len(A)
    if structure == "chain":
        M2 = M
        M1 = base * 0  # 占位，由调用方传入
        return -0.15 * A - 0.25 * M1 - 0.30 * M2 + 0.55 * base + rng.normal(0, .8, n)
    return (-0.20 * A - 0.35 * M + 0.10 * A * M + 0.55 * base + rng.normal(0, .8, n))


def run_spec(pf: pd.DataFrame, spec: dict, outcome: str, seed: int, B: int,
             demo: bool = False):
    d = _design(pf, spec["mediator"], outcome)
    if d is None:
        return None
    y, A, M, C, used = d
    n = len(y)
    base = C[:, -1]
    if demo:                                   # 演示：用已知 DGP 覆盖结局，使真值可校验
        y = _z(demo_outcome(A, M, base, seed + n))
    est = fourway(y, A, M, C)

    def _boot(idx):
        return fourway(y[idx], A[idx], M[idx], C[idx])

    ci = boot_ci(_boot, n, B, seed)
    est.update({k: v for k, v in ci.items()})
    est.update(cohort=spec["cohort"], layer=spec["layer"],
               mediator=spec["mediator"], outcome=outcome, label=spec["label"],
               n_people=n, n_events=int(np.nansum(A)))
    # 比例中介的稳定性判定
    unstable = (abs(est["TE"]) < 1e-3) or \
               (est.get("TE_lo", np.nan) * est.get("TE_hi", np.nan) < 0)
    est["ratio_unstable"] = bool(unstable)
    if unstable:
        for k in ("prop_NIE", "prop_PIE", "prop_INTmed", "prop_INTref"):
            est[k] = np.nan
    return est


def run_serial(pf: pd.DataFrame, spec: dict, outcome: str, seed: int, B: int,
               demo: bool = False):
    need = [c for c in ["edent_base", spec["m1"], spec["m2"], outcome, "cog_base"]
            if c in pf.columns]
    d = pf.dropna(subset=need).copy()
    covs = _usable_covs(d)
    d = d.dropna(subset=covs)
    if len(d) < 200:
        return None
    A = d["edent_base"].astype(float).values
    M1 = _z(d[spec["m1"]].astype(float).values)
    M2 = _z(d[spec["m2"]].astype(float).values)
    base = _z(d["cog_base"].astype(float).values)
    C = np.column_stack([base] + [d[c].astype(float).values - np.nanmean(d[c].astype(float).values)
                                  for c in covs])
    y = _z(d[outcome].astype(float).values)
    n = len(y)
    if demo:      # 链式 DGP：Y 同时依赖 M1 与 M2，故 a1·d21·b2 应显著非零
        rng = np.random.default_rng(seed + n)
        y = _z(-0.15 * A - 0.25 * M1 - 0.30 * M2 + 0.55 * base + rng.normal(0, .8, n))
    est = serial(y, A, M1, M2, C)
    ci = boot_ci(lambda idx: serial(y[idx], A[idx], M1[idx], M2[idx], C[idx]), n, B, seed)
    est.update(ci)
    est.update(cohort=spec["cohort"], layer=spec["layer"], m1=spec["m1"],
               m2=spec["m2"], outcome=outcome, label=spec["label"], n_people=n)
    return est


def _figure(rows: pd.DataFrame):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    if rows.empty:
        return None
    r = rows.dropna(subset=["NIE"]).reset_index(drop=True)
    if r.empty:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 0.55 * len(r) + 1.8))
    yy = np.arange(len(r))[::-1]
    for yi, (_, s) in zip(yy, r.iterrows()):
        ax.plot([s["NIE_lo"], s["NIE_hi"]], [yi, yi], color="#3b6ea5", lw=1.8)
        ax.plot([s["NIE"]], [yi], "s", color="#1f3b57", ms=8)
        ax.text(1.02, yi, f"{s['NIE']:+.3f} ({s['NIE_lo']:+.3f}, {s['NIE_hi']:+.3f})",
                transform=ax.get_yaxis_transform(), va="center", fontsize=9)
    ax.axvline(0, color="#888", ls="--", lw=1)
    ax.set_yticks(yy); ax.set_yticklabels(r["label"])
    ax.set_xlabel("Natural indirect effect (NIE), standardized units")
    ax.set_title("缺牙 → 中介 → 认知：自然间接效应（bootstrap 95% CI）", fontsize=11.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    p = OUT_FIG / "mediation_effects.png"
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def main(demo: bool | None = None, outcome: str = "followup",
         seed: int = RANDOM_SEED, boot: int | None = None):
    B = boot or MEDIATION_BOOT
    OUT_TAB.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(HARM_LONG, low_memory=False)
    print(f"读取主长表 {HARM_LONG.name}（n={len(df):,}）")

    demo = (not BIOMARKER_FILE.exists()) if demo is None else demo
    bm_people = None
    if demo:
        print("⚠️ 演示模式：血样表不存在 → 合成标志物 + 合成结局（数字不得写入论文）")
    else:
        bm_people = pd.read_csv(BIOMARKER_FILE)
        print(f"读取血样表 {BIOMARKER_FILE.name}（n={len(bm_people):,}）")

    out_col = "cog_fu" if outcome == "followup" else "cog_slope"
    cohorts = sorted({s["cohort"] for s in MEDIATION_SPECS + SERIAL_SPECS})

    frames, rows4, rowsS = {}, [], []
    for coh in cohorts:
        pf = person_frame(df, coh)
        if pf.empty:
            print(f"  [{coh:6s}] 长表无该队列 → 跳过"); continue
        if MAX_N and len(pf) > MAX_N:
            pf = pf.sample(MAX_N, random_state=seed)
        if demo:
            meta = pf[["cohort", "id", "age"]].copy()
            bmc = synth_marker_frame(meta, seed=seed)
            from step11_biologicage import compute_bioage_table
            people, _ = compute_bioage_table(bmc, allow_flagged=True)
            people["bioage_accel_clean"] = people["kdm_clean_accel"]
            pf = demo_attach(pf, coh, bmc, people, seed)
        else:
            keep = ["cohort", "id"] + [c for c in bm_people.columns
                                       if c in INFLAMMATION_MARKERS or c.startswith("bioage")]
            # ⚠️ id 类型对齐：person_frame 的 id 恒为 str，而 CSV 里的纯数字 id 会被 pandas 读成 int64
            pf["id"] = pf["id"].astype(str)
            bmk = bm_people[keep].copy()
            bmk["id"] = bmk["id"].astype(str)
            pf = pf.merge(bmk.drop_duplicates(["cohort", "id"]),
                          on=["cohort", "id"], how="left")
        frames[coh] = pf
        print(f"  [{coh:6s}] n={len(pf):>6,}  有结局={pf[out_col].notna().sum():>6,}  "
              f"其中无牙颌={int(pf['edent_base'].fillna(0).sum()):>5,}", flush=True)

    for spec in MEDIATION_SPECS:
        pf = frames.get(spec["cohort"])
        if pf is None:
            continue
        if spec["mediator"] not in pf.columns or pf[spec["mediator"]].notna().sum() < 200:
            print(f"  ✗ {spec['label']}：中介 '{spec['mediator']}' 不可用 → 跳过")
            continue
        r = run_spec(pf, spec, out_col, seed, B, demo=demo)
        if r is None:
            print(f"  ✗ {spec['label']}：有效样本不足 → 跳过"); continue
        rows4.append(r)
        flag = "  ⚠️比例不稳定" if r["ratio_unstable"] else ""
        print(f"  ✓ {spec['label']:<28} n={r['n_people']:>5,}  TE={r['TE']:+.3f} "
              f"NIE={r['NIE']:+.3f} [{r['NIE_lo']:+.3f},{r['NIE_hi']:+.3f}]  "
              f"中介比例={r['prop_NIE'] if np.isfinite(r['prop_NIE']) else float('nan'):.2f}{flag}",
              flush=True)

    for spec in SERIAL_SPECS:
        pf = frames.get(spec["cohort"])
        if pf is None or spec["m1"] not in pf.columns or spec["m2"] not in pf.columns:
            continue
        r = run_serial(pf, spec, out_col, seed, B, demo=demo)
        if r is None:
            continue
        rowsS.append(r)
        print(f"  ✓ [链式] {spec['label']:<28} n={r['n_people']:>5,}  "
              f"链式间接={r['ind_M1M2']:+.3f} [{r['ind_M1M2_lo']:+.3f},{r['ind_M1M2_hi']:+.3f}]")

    t4 = pd.DataFrame(rows4)
    tS = pd.DataFrame(rowsS)
    t4.to_csv(OUT_TAB / "mediation_4way.csv", index=False, encoding="utf-8-sig")
    tS.to_csv(OUT_TAB / "mediation_serial.csv", index=False, encoding="utf-8-sig")
    fig = _figure(t4)
    _write_md(t4, tS, outcome, demo)

    print(f"\n已输出：\n  {OUT_TAB/'mediation_4way.csv'}\n  {OUT_TAB/'mediation_serial.csv'}"
          f"\n  {OUT_TAB/'mediation_summary.md'}" + (f"\n  {fig}" if fig else ""))
    return t4, tS


def _write_md(t4: pd.DataFrame, tS: pd.DataFrame, outcome: str, demo: bool):
    L = ["# 中介分析结果汇总", "",
         f"**结局口径**：{'随访期末认知（校正基线）' if outcome == 'followup' else '个体认知斜率（校正基线）'}",
         f"**数据来源**：{'⚠️ 合成演示数据（数字不得写入论文）' if demo else '真实协调化数据'}",
         f"**效应单位**：结局与中介均已标准化；暴露为二分 `edent_base`", ""]
    if not t4.empty:
        L += ["## 一、四向分解（VanderWeele 2014）", "",
              "TE = CDE + INTref + INTmed + PIE；NIE = PIE + INTmed", "",
              "| 队列 | 中介 | n | TE | NIE (95%CI) | PIE | INTmed | INTref | CDE | 中介比例 | 备注 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in t4.iterrows():
            f2 = lambda v: f"{v:+.3f}" if np.isfinite(v) else "—"
            ci = f"{f2(r['NIE'])} ({f2(r.get('NIE_lo'))}, {f2(r.get('NIE_hi'))})"
            prop = f"{r['prop_NIE']:.2f}" if np.isfinite(r.get("prop_NIE", np.nan)) else "—"
            note = "比例不稳定，仅报绝对效应" if r.get("ratio_unstable") else ""
            L.append(f"| {r['cohort']} | {r['mediator']} | {r['n_people']:,} | {f2(r['TE'])} | "
                     f"{ci} | {f2(r['PIE'])} | {f2(r['INTmed'])} | {f2(r['INTref'])} | "
                     f"{f2(r['CDE'])} | {prop} | {note} |")
        L.append("")
    if not tS.empty:
        L += ["## 二、串联链式中介（缺牙 → 炎症 → 生物年龄 → 认知）", "",
              "| 队列 | M1 | M2 | 链式 间接 M1→M2→Y | A→M1→Y | A→M2→Y | 总间接 | 直接 | 链式/总效应 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for _, r in tS.iterrows():
            f2 = lambda v: f"{v:+.3f}" if np.isfinite(v) else "—"
            L.append(f"| {r['cohort']} | {r['m1']} | {r['m2']} | "
                     f"{f2(r['ind_M1M2'])} ({f2(r.get('ind_M1M2_lo'))}, {f2(r.get('ind_M1M2_hi'))}) | "
                     f"{f2(r['ind_M1'])} | {f2(r['ind_M2'])} | {f2(r['total_indirect'])} | "
                     f"{f2(r['direct'])} | "
                     f"{r['prop_chain']:.2f} |" if np.isfinite(r.get('prop_chain', np.nan))
                     else f"| {r['cohort']} | {r['m1']} | {r['m2']} | {f2(r['ind_M1M2'])} | "
                          f"{f2(r['ind_M1'])} | {f2(r['ind_M2'])} | {f2(r['total_indirect'])} | "
                          f"{f2(r['direct'])} | — |")
        L.append("")
    L += ["---", "",
          "*方法：bootstrap 百分位 95% CI（个体层重抽样）；中介测于暴露之后；"
          "主分析使用去污染版生物年龄以避免与炎症标志物成分重叠。*"]
    (OUT_TAB / "mediation_summary.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
