# -*- coding: utf-8 -*-
"""
selftest_biomarker.py   机制层自检（合成数据 + 已知真值）
==========================================================
不依赖任何真实数据，验证四件事：
  ① PhenoAge 公式行为正确（对实龄/组分单调、能回收实龄）；
  ② KDM 能回收实龄且 BA−CA 均值≈0；
  ③ 四向分解**代数恒等式** TE = CDE+INTref+INTmed+PIE 精确成立；
  ④ 四向分解与链式中介能在已知 DGP 下**回收真值**（容差内）；
  ⑤ 全缺失协变量不会清空整个队列（ELSA 无 rural 的坑）；
  ⑥ 衰老结局层：OLS 回收总效应、事件计数正确、实龄系数≈0、中介回收真值、
     E-value 行为正确、时序过滤生效。

用法：
    python selftest_biomarker.py         # 全绿则 exit 0
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_biomarker import demo_biomarkers                       # noqa: E402
from step10_mediation import fourway, serial, _design, COVS        # noqa: E402
from step11_biologicage import (phenoage, kdm_bioage,             # noqa: E402
                                age_acceleration, normalise_units,
                                preprocess_for_kdm)

warnings.filterwarnings("ignore")

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = ""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'✓' if ok else '✗'} {name}" + (f"   [{detail}]" if detail else ""))


# ---------------------------------------------------------------- ① PhenoAge
def t_phenoage():
    print("\n[①] PhenoAge（Levine 2018）")
    base = dict(albumin=42.0, creatinine=78.0, glucose=5.0, crp=1.0,
                lymph_pct=30.0, mcv=90.0, rdw=13.0, alp=75.0, wbc=6.5)
    mk = lambda **kw: pd.DataFrame([{**base, "age": 60, **kw}])

    pa0 = float(phenoage(mk()).iloc[0])
    pa_old = float(phenoage(mk(age=75)).iloc[0])
    pa_rdw = float(phenoage(mk(rdw=16)).iloc[0])          # RDW 权重最大 → 明显更老
    pa_crp = float(phenoage(mk(crp=8.0)).iloc[0])
    pa_alb = float(phenoage(mk(albumin=48.0)).iloc[0])    # 白蛋白系数为负 → 更年轻

    check("PhenoAge 随实龄递增", pa_old > pa0, f"{pa0:.1f} → {pa_old:.1f}")
    check("PhenoAge 对 RDW 敏感（权重最大项）", pa_rdw > pa0 + 5, f"{pa0:.1f} → {pa_rdw:.1f}")
    check("PhenoAge 随 CRP 升高", pa_crp > pa0, f"{pa0:.1f} → {pa_crp:.1f}")
    check("PhenoAge 随白蛋白升高而降低", pa_alb < pa0, f"{pa0:.1f} → {pa_alb:.1f}")

    bm = demo_biomarkers(n=3000, cohorts=("NHANES",))
    pa = phenoage(bm)
    r = np.corrcoef(bm["age"], pa)[0, 1]
    check("PhenoAge 能回收实龄（r > 0.85）", r > 0.85, f"r = {r:.3f}")
    check("PhenoAge 缺组分时返回全 NaN",
          bool(phenoage(bm.drop(columns=["albumin"])).isna().all()))


# ---------------------------------------------------------------- ② KDM
def t_kdm():
    print("\n[②] KDM（Klemera-Doubal）")
    rng = np.random.default_rng(7)
    n = 6000
    age = rng.uniform(40, 85, n)
    d = pd.DataFrame({"age": age})
    for j, (b, s) in enumerate([(0.30, 3.0), (0.55, 8.0), (-0.02, 0.5),
                                (0.09, 4.0), (0.05, 1.0), (0.04, 1.2)]):
        d[f"m{j}"] = 30 + b * age + rng.normal(0, s, n)

    ba, fit = kdm_bioage(d, [f"m{j}" for j in range(6)])
    ok = ba.notna()
    r = np.corrcoef(age[ok], ba[ok])[0, 1]
    diff = float(np.mean(ba[ok] - age[ok]))
    check("KDM 回收实龄（r > 0.85）", r > 0.85, f"r = {r:.3f}")
    check("BA − CA 均值 ≈ 0（|diff| < 2 年）", abs(diff) < 2.0, f"diff = {diff:+.2f} 年")

    accel, info = age_acceleration(ba, d["age"])
    check("年龄加速与实龄正交（|r| < 0.02）",
          abs(np.corrcoef(accel[ok], age[ok])[0, 1]) < 0.02,
          f"r = {np.corrcoef(accel[ok], age[ok])[0, 1]:+.4f}")

    ba_n, _ = kdm_bioage(d, ["m0", "m1"])              # 标志物不足
    check("标志物不足时返回 NaN 而非报错", bool(ba_n.isna().all()))

    d2 = d.copy(); d2["creatinine"] = 1.1              # mg/dL → 应被识别并 ×88.42
    nd = normalise_units(d2.rename(columns={}))
    check("单位换算：疑似 mg/dL 的肌酐被转换",
          "creatinine" not in nd.columns or nd["creatinine"].median() > 50)

    # —— HRS VBS 白蛋白为 g/dL（实测均值≈3.93），必须 ×10 转 g/L ——
    d3 = pd.DataFrame({"albumin": [3.5, 3.9, 4.2, 4.0, 3.7]})   # g/dL
    n3 = normalise_units(d3)
    check("单位换算：g/dL 白蛋白被 ×10 转 g/L",
          abs(n3["albumin"].median() - 39.0) < 2.0,
          f"median = {n3['albumin'].median():.2f} g/L")
    d4 = pd.DataFrame({"albumin": [38.0, 42.0, 40.5, 44.0, 39.0]})  # 已是 g/L
    n4 = normalise_units(d4)
    check("单位换算：已是 g/L 的白蛋白不被误改",
          abs(n4["albumin"].median() - 40.5) < 0.5,
          f"median = {n4['albumin'].median():.2f} g/L")
    # HRS 真实空腹血糖均值 ≈ 111.9 mg/dL → 应转 mmol/L（≈6.2）
    d5 = pd.DataFrame({"glucose": [95.0, 112.0, 105.0, 130.0, 90.0]})
    n5 = normalise_units(d5)
    check("单位换算：mg/dL 空腹血糖转 mmol/L",
          abs(n5["glucose"].median() - 105.0 * 0.05551) < 0.05,
          f"median = {n5['glucose'].median():.2f} mmol/L")


# ---------------------------------------------------------------- ③ 代数恒等式
def t_kdm_prep():
    print("\n[②b] KDM 输入前处理（缩尾 + 右偏取对数）")
    rng = np.random.default_rng(11)
    n = 8000
    age = rng.uniform(40, 90, n)
    d = pd.DataFrame({"age": age})
    d["m0"] = 30 + 0.30 * age + rng.normal(0, 3.0, n)                  # 近正态
    d["m1"] = 100 + 0.55 * age + rng.normal(0, 8.0, n)
    d["m2"] = np.exp(0.020 * (age - 60) + rng.normal(0, 1.6, n))       # 强右偏（log 空间线性）
    d["m3"] = np.exp(0.030 * (age - 60) + rng.normal(0, 1.4, n))
    ms = ["m0", "m1", "m2", "m3"]

    ba_raw, _ = kdm_bioage(d, ms)
    d_p, info = preprocess_for_kdm(d, ms)
    ba_pre, _ = kdm_bioage(d_p, ms)
    ok = ba_raw.notna() & ba_pre.notna()
    r_raw = float(np.corrcoef(age[ok], ba_raw[ok])[0, 1])
    r_pre = float(np.corrcoef(age[ok], ba_pre[ok])[0, 1])
    check("前处理不劣化并提升 KDM↔实龄相关", r_pre >= r_raw - 0.01,
          f"r {r_raw:.3f} → {r_pre:.3f}")
    check("强右偏标志物被识别并取对数",
          all(k in info for k in ("m2", "m3")), str(list(info)))

    # 幂等性：对已处理的输入再处理不应继续变形（偏度已降下来）
    d_p2, info2 = preprocess_for_kdm(d_p, ms)
    check("前处理近似幂等（二次调用不再取对数）",
          not any(k in info2 for k in ("m2", "m3")), str(list(info2)))


# ---------------------------------------------------------------- ③ 代数恒等式
def t_identity():
    print("\n[③] 四向分解代数恒等式")
    rng = np.random.default_rng(11)
    n = 4000
    A = rng.binomial(1, 0.2, n).astype(float)
    C = rng.normal(0, 1, (n, 3))
    M = 1 + 0.7 * A + 0.4 * C[:, 0] + rng.normal(0, 1, n)
    Y = -0.3 * A - 0.5 * M + 0.2 * A * M + 0.6 * C[:, 0] + rng.normal(0, 1, n)
    r = fourway(Y, A, M, C)
    resid = r["TE"] - (r["CDE"] + r["INTref"] + r["INTmed"] + r["PIE"])
    check("TE = CDE + INTref + INTmed + PIE", abs(resid) < 1e-9, f"残差 = {resid:.2e}")
    check("NIE = PIE + INTmed",
          abs(r["NIE"] - (r["PIE"] + r["INTmed"])) < 1e-12)


# ---------------------------------------------------------------- ④ 真值回收
def t_recovery():
    print("\n[④] 已知 DGP 下的真值回收")
    rng = np.random.default_rng(2026)
    n = 40000
    A = rng.binomial(1, 0.15, n).astype(float)
    C = rng.normal(0, 1, (n, 2))
    M = 0.8 + 0.60 * A + 0.30 * C[:, 0] + rng.normal(0, 1, n)
    Y = (1.0 - 0.30 * A - 0.40 * M + 0.15 * A * M
         + 0.5 * C[:, 0] - 0.2 * C[:, 1] + rng.normal(0, 1, n))
    r = fourway(Y, A, M, C)
    truth = {"CDE": -0.30, "PIE": -0.40 * 0.60, "INTmed": 0.15 * 0.60,
             "INTref": 0.15 * 0.80, "TE": -0.30 + 0.15 * 0.80 + 0.15 * 0.60 - 0.24}
    for k, v in truth.items():
        check(f"四向分解回收 {k}", abs(r[k] - v) < 0.02, f"估 {r[k]:+.3f} / 真 {v:+.3f}")

    # 链式
    M1 = 0.5 * A + 0.4 * C[:, 0] + rng.normal(0, 1, n)
    M2 = 0.3 * A + 0.5 * M1 + 0.3 * C[:, 0] + rng.normal(0, 1, n)
    Y2 = (-0.2 * A - 0.25 * M1 - 0.30 * M2 + 0.5 * C[:, 0] + rng.normal(0, 1, n))
    s = serial(Y2, A, M1, M2, C)
    for k, v in {"ind_M1": 0.5 * -0.25, "ind_M1M2": 0.5 * 0.5 * -0.30,
                 "ind_M2": 0.3 * -0.30, "direct": -0.20}.items():
        check(f"链式中介回收 {k}", abs(s[k] - v) < 0.02, f"估 {s[k]:+.3f} / 真 {v:+.3f}")


# ---------------------------------------------------------------- ⑤ 缺失协变量
def t_missing_cov():
    print("\n[⑤] 全缺失协变量处理（ELSA 无 rural 的坑）")
    rng = np.random.default_rng(5)
    n = 3000
    d = pd.DataFrame({
        "cohort": "ELSA", "id": np.arange(n),
        "edent_base": rng.binomial(1, 0.2, n),
        "age_c": rng.normal(0, 8, n), "female": rng.binomial(1, .5, n),
        "edu_years": rng.normal(10, 3, n), "married": rng.binomial(1, .6, n),
        "rural": np.nan,                                   # ← 整列缺失
        "ever_smoke": rng.binomial(1, .4, n),
        "cog_base": rng.normal(0, 1, n),
        "mediator": rng.normal(0, 1, n),
        "cog_fu": rng.normal(0, 1, n),
    })
    for c in ("rural",):
        assert c in COVS
    out = _design(d, "mediator", "cog_fu")
    check("rural 全缺失时仍能构建设计矩阵（不清空队列）",
          out is not None and out[0].shape[0] > 2000,
          f"n = {0 if out is None else out[0].shape[0]}")


# ---------------------------------------------------------------- ⑥ 衰老结局层
def t_bioage_outcome():
    print("\n[⑥] 生物年龄结局层（缺牙 → 衰老加速）")
    from step12_bioage_outcome import (fit_exposure, mediate_cont,
                                       e_value_continuous, build_frame, DEMO_TRUTH)
    rng = np.random.default_rng(31)
    n = 40000
    A = rng.binomial(1, 0.18, n).astype(float)
    C3 = rng.normal(0, 1, (n, 3))
    M = DEMO_TRUTH["a"] * A + rng.normal(0, 1, n)                       # 炎症
    Y = DEMO_TRUTH["c"] * A + DEMO_TRUTH["b"] * M + rng.normal(0, 1.6, n)
    d = pd.DataFrame({"cohort": "X", "id": np.arange(n), "edent_base": A,
                      "age_c": C3[:, 0], "female": rng.binomial(1, .5, n),
                      "edu_years": C3[:, 1], "married": rng.binomial(1, .6, n),
                      "ever_smoke": rng.binomial(1, .4, n),
                      "kdm_clean_accel": Y, "crp": M})

    r = fit_exposure(d, "kdm_clean_accel")
    check("OLS 回收总效应（0.45 ± 0.03）",
          abs(r["beta"] - DEMO_TRUTH["total"]) < 0.03,
          f"估 {r['beta']:+.3f} / 真 {DEMO_TRUTH['total']:+.3f}")
    check("n_events 用未中心化暴露计数（非 0）",
          r["n_events"] == int(A.sum()), f"n_events = {r['n_events']} / 真 {int(A.sum())}")
    check("实龄系数 ≈ 0（accel 已与实龄正交）",
          abs(r["age_c_beta"]) < 0.02, f"β_age = {r['age_c_beta']:+.4f}")

    med = mediate_cont(Y, A, M, C3)
    for k, v in (("a", DEMO_TRUTH["a"]), ("b", DEMO_TRUTH["b"]),
                 ("NIE", DEMO_TRUTH["nie"])):
        check(f"中介回收 {k}", abs(med[k] - v) < 0.03, f"估 {med[k]:+.3f} / 真 {v:+.3f}")
    check("中介比例 ≈ 1/3", abs(med["prop"] - DEMO_TRUTH["prop"]) < 0.05,
          f"估 {med['prop']:.3f} / 真 {DEMO_TRUTH['prop']:.3f}")

    e0 = e_value_continuous(0.0, 1.0)["E_point"]
    e1 = e_value_continuous(0.5, 1.0)["E_point"]
    e2 = e_value_continuous(1.0, 1.0)["E_point"]
    check("E-value：效应为 0 时 = 1", abs(e0 - 1.0) < 1e-9, f"{e0:.3f}")
    check("E-value 随效应单调递增", e0 < e1 < e2, f"{e0:.2f} < {e1:.2f} < {e2:.2f}")

    # 时序强制：血样必须晚于/等于暴露年
    d2 = pd.DataFrame({
        "cohort": "X", "id": [1, 2, 3, 4], "wave": 1, "year": [2010] * 4,
        "time_c": [0] * 4, "age": [60, 61, 62, 63], "age_c": [0, 1, 2, 3],
        "female": [1, 0, 1, 0], "edu_years": [10, 12, 9, 11],
        "married": [1, 1, 0, 1], "rural": [0, 1, 0, 1], "ever_smoke": [0, 1, 1, 0],
        "edent_base": [1, 0, 1, 0], "cog_z": [0., 1., 2., 3.],
    })
    peo = pd.DataFrame({"cohort": ["X"] * 4, "id": [1, 2, 3, 4],
                        "year": [2012, 2012, 2005, 2012],          # id3 血样早于暴露 → 应剔除
                        "age": [62, 63, 57, 65],
                        "kdm_clean_accel": [1., 2., 3., 4.],
                        "kdm_accel": [1., 2., 3., 4.],
                        "phenoage_accel": [1., 2., 3., 4.]})
    m, info = build_frame(d2, "X", peo, demo=False, seed=1, window=12)
    check("时序过滤：血样早于暴露者被剔除",
          info.get("n_kept") == 3, f"保留 {info.get('n_kept')} / 合并 4")


if __name__ == "__main__":
    print("=" * 62)
    print("机制层自检（合成数据，与真实数据无关）")
    print("=" * 62)
    for fn in (t_phenoage, t_kdm, t_kdm_prep, t_identity, t_recovery,
               t_missing_cov, t_bioage_outcome):
        fn()
    print("\n" + "=" * 62)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "; ".join(FAIL))
    print("=" * 62)
    sys.exit(1 if FAIL else 0)
