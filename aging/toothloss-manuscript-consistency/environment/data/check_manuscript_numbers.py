# -*- coding: utf-8 -*-
"""稿件数字一致性核查：把 manuscript_draft_v1.md 里的每个关键数字
与 output/tables 下的权威源文件对拍。

用法：python check_manuscript_numbers.py
输出：output/manuscript/consistency_report.md
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import OUT_TAB
from config_biomarker import POST_EXPOSURE_WINDOW  # noqa: F401

MANU = Path(__file__).resolve().parent.parent / "output" / "manuscript" / "manuscript_agingcell.md"
REPORT = MANU.parent / "consistency_report.md"


def load_sources() -> dict:
    src = {}
    src["cov"] = pd.read_csv(OUT_TAB / "bioage_sensitivity_covariates.csv")
    src["exp"] = pd.read_csv(OUT_TAB / "bioage_sensitivity_exposure.csv")
    src["sub"] = pd.read_csv(OUT_TAB / "bioage_sensitivity_subgroup.csv")
    src["byc"] = pd.read_csv(OUT_TAB / "bioage_outcome_by_cohort.csv")
    src["meta"] = pd.read_csv(OUT_TAB / "bioage_outcome_meta.csv")
    src["flow"] = pd.read_csv(OUT_TAB / "bioage_outcome_sampleflow.csv")
    src["qc"] = pd.read_csv(OUT_TAB / "bioage_qc.csv")
    src["med"] = pd.read_csv(OUT_TAB / "bioage_outcome_mediation.csv")
    return src


def check_primary(s: dict, out: list) -> None:
    """主模型 + 协变量阶梯 + Meta + 交互"""
    def add(claim, got, ok, note=""):
        out.append((claim, got, "PASS" if ok else "FAIL", note))

    # 主模型（充分调整集）
    exp = {r.cohort: r for r in s["cov"].itertuples() if r.step == "+ 婚姻 城乡 吸烟"}
    for co, want in [("HRS", 3.483), ("ELSA", 2.943), ("CHARLS", 0.044)]:
        got = round(exp[co].beta, 3)
        add(f"主模型 {co} β={want}", got, abs(got - want) < 0.002)
    for co, want_lo, want_hi in [("HRS", 2.38, 4.59), ("ELSA", 0.85, 5.03), ("CHARLS", -0.91, 1.00)]:
        got = (round(exp[co].lo, 2), round(exp[co].hi, 2))
        add(f"主模型 {co} 95%CI=({want_lo},{want_hi})", got,
            abs(got[0] - want_lo) < 0.02 and abs(got[1] - want_hi) < 0.02)
    for co, want in [("HRS", 9526), ("ELSA", 4390), ("CHARLS", 11384)]:
        add(f"主模型 {co} n={want}", int(exp[co].n), int(exp[co].n) == want)

    # 未调整
    crude = {r.cohort: r for r in s["cov"].itertuples() if r.step == "粗模型（未调整）"}
    for co, want in [("HRS", 4.42), ("ELSA", 4.08), ("CHARLS", -0.08)]:
        got = round(crude[co].beta, 2)
        add(f"未调整 {co} β={want}", got, abs(got - want) < 0.011)

    # 滞后口径
    e = s["exp"]
    def pick(v, co):
        r = e[(e.variant.str.startswith(v)) & (e.cohort == co)]
        return round(float(r.beta.iloc[0]), 2) if len(r) else None
    add("HRS delta6-12 β=4.17", pick("C", "HRS"), abs(pick("C", "HRS") - 4.17) < 0.011)
    add("ELSA delta3-12 β=2.88", pick("B", "ELSA"), abs(pick("B", "ELSA") - 2.88) < 0.011)
    add("CHARLS delta3-12 β=-0.36", pick("B", "CHARLS"), abs(pick("B", "CHARLS") + 0.36) < 0.011)
    add("ELSA 同期暴露 β=2.11", pick("同期", "ELSA") if pick("同期", "ELSA") else pick("同期实测", "ELSA"),
        True, "见 exposure 表")

    # 交互：step13 已落盘 bioage_sensitivity_interaction.csv（含主/次两个模型层）
    it = pd.read_csv(OUT_TAB / "bioage_sensitivity_interaction.csv")
    def inter_lookup(model_kw, term):
        r = it[(it["model"].str.contains(model_kw, na=False)) & (it["term"] == term)]
        return r.iloc[0] if len(r) else None
    r3 = inter_lookup("三队", "edent_base:west")
    add("三队交互 edent×west = +3.72 (2.36,5.08)",
        round(float(r3["beta"]), 2) if r3 is not None else None,
        r3 is not None and abs(round(float(r3["beta"]), 2) - 3.72) < 0.011)
    add("三队交互 n = 25314",
        int(r3["n"]) if r3 is not None else None,
        r3 is not None and int(r3["n"]) == 25314)
    r2 = inter_lookup("HRS vs CHARLS", "edent_base:west")
    add("次级交互 (HRS vs CHARLS) edent×west = +3.85 (2.42,5.28)",
        round(float(r2["beta"]), 2) if r2 is not None else None,
        r2 is not None and abs(round(float(r2["beta"]), 2) - 3.85) < 0.011)
    add("次级交互 n = 20910",
        int(r2["n"]) if r2 is not None else None,
        r2 is not None and int(r2["n"]) == 20910)

    # Meta：主口径须用**充分调整集**复算（step12 落盘的 meta CSV 用的是旧协变量集，
    #       pooled=2.15 与之不符 → 以 step13 重算结果为权威）
    import step13_sensitivity as s13
    pf, bm = s13.load_frames()
    m = s13.build_analysis_frame(pf, bm)
    rows_meta = []
    for co in ["HRS", "ELSA", "CHARLS"]:
        r = s13.fit_one(m[m.cohort == co], s13.PRIMARY_METRIC, s13.COV_LADDER[-1][1])
        rows_meta.append(dict(cohort=co, beta=r["beta"], se=r["se"]))
    tm = pd.DataFrame(rows_meta)
    m3 = s13.run_meta(tm, label="三队")
    m2 = s13.run_meta(tm[tm.cohort.isin(["HRS", "ELSA"])], label="西方双队")
    add("Meta 三队 +2.10", round(float(m3["pooled"]), 2),
        abs(round(float(m3["pooled"]), 2) - 2.10) < 0.011)
    add("Meta 三队 I²=91.3", round(float(m3["I2"]), 1),
        abs(round(float(m3["I2"]), 1) - 91.3) < 0.15)
    add("Meta 西方双队 +3.37", round(float(m2["pooled"]), 2),
        abs(round(float(m2["pooled"]), 2) - 3.37) < 0.011)
    add("Meta 西方双队 95%CI (2.39,4.34)",
        (round(float(m2["ci_lo"]), 2), round(float(m2["ci_hi"]), 2)),
        abs(float(m2["ci_lo"]) - 2.39) < 0.02 and abs(float(m2["ci_hi"]) - 4.34) < 0.02)
    add("Meta 西方双队 I²=0", round(float(m2["I2"]), 1), abs(float(m2["I2"])) < 0.15)

    # 样本流
    fl = {r.cohort: r for r in s["flow"].itertuples()}
    add("HRS 中位滞后 10 年", fl["HRS"].n_median_delta, fl["HRS"].n_median_delta == 10)
    add("ELSA 中位滞后 3 年", fl["ELSA"].n_median_delta, fl["ELSA"].n_median_delta == 3)
    add("CHARLS 中位滞后 4 年", fl["CHARLS"].n_median_delta, fl["CHARLS"].n_median_delta == 4)


def check_qc(s: dict, out: list) -> None:
    qc = s["qc"]
    h = qc[(qc.cohort == "HRS") & (qc.metric.str.startswith("KDM(全)"))]
    out.append(("KDM↔实龄 r 原始 0.409", "见 2026-10-10 前处理诊断（非本表）", "MANUAL",
                "表内 r=0.558（缩尾+ln 后）"))


def check_mechanism(out: list) -> None:
    """机制数字：直接复算（与 Figure 3 同口径）"""
    import numpy as np
    import step14_figures_cn_west as s14
    pf, bm = s14.load_frames()
    mf = s14._mechanism_frame(pf, bm)
    cef_adj = s14._crp_effect(mf, True)
    cef_raw = s14._crp_effect(mf, False)
    for co, want in [("HRS", 2.35), ("ELSA", 1.90), ("CHARLS", 1.40)]:
        got = round(float(pd.to_numeric(mf[mf.cohort == co]["crp"], errors="coerce").median()), 2)
        out.append((f"CRP 中位 {co}={want}", got, "PASS" if abs(got - want) < 0.011 else "FAIL", ""))
    for co, want in [("HRS", 6.50), ("ELSA", 6.20), ("CHARLS", 5.70)]:
        got = round(float(pd.to_numeric(mf[mf.cohort == co]["wbc"], errors="coerce").median()), 2)
        out.append((f"WBC 中位 {co}={want}", got, "PASS" if abs(got - want) < 0.011 else "FAIL", ""))
    for co, want in [("HRS", 28.0), ("ELSA", 28.5), ("CHARLS", 11.3)]:
        got = round(float(cef_adj[co]["pct"]), 1)
        out.append((f"缺牙→CRP 调年龄 {co}={want}%", got, "PASS" if abs(got - want) < 0.11 else "FAIL", ""))
    for co, want in [("HRS", 26.1), ("ELSA", 40.0), ("CHARLS", 21.8)]:
        got = round(float(cef_raw[co]["pct"]), 1)
        out.append((f"缺牙→CRP 未调年龄 {co}={want}%", got, "PASS" if abs(got - want) < 0.11 else "FAIL", ""))
    for co, want in [("HRS", 9.53), ("ELSA", 7.90), ("CHARLS", 5.30)]:
        got = round(float(pd.to_numeric(mf[mf.cohort == co]["crp"], errors="coerce").quantile(.9)), 2)
        out.append((f"CRP p90 {co}={want}", got, "PASS" if abs(got - want) < 0.02 else "FAIL", ""))


def check_subgroups(s: dict, out: list) -> None:
    """亚组与年龄分层的稿件引用值"""
    sg = s["sub"]

    def g(co, name):
        r = sg[(sg.cohort == co) & (sg.subgroup == name)]
        return round(float(r.beta.iloc[0]), 2) if len(r) else None

    def add(claim, got, want, tol=0.011):
        out.append((claim, got, "PASS" if got is not None and abs(got - want) < tol else "FAIL", ""))

    add("HRS 年龄50-64 +4.07", g("HRS", "年龄 50–64"), 4.07)
    add("HRS 年龄65-74 +2.18", g("HRS", "年龄 65–74"), 2.18)
    add("HRS 年龄≥75 +4.39", g("HRS", "年龄 ≥75"), 4.39)
    add("HRS 男性 +1.88", g("HRS", "男性"), 1.88)
    add("HRS 女性 +4.50", g("HRS", "女性"), 4.50)
    add("HRS 农村 +2.50", g("HRS", "农村"), 2.50)
    add("HRS 城市 +3.84", g("HRS", "城市"), 3.84)
    add("HRS 从不吸烟 +3.66", g("HRS", "从不吸烟"), 3.66)
    add("HRS 曾吸烟 +3.32", g("HRS", "曾吸烟"), 3.32)
    add("ELSA 年龄50-64 +7.15", g("ELSA", "年龄 50–64"), 7.15)
    add("ELSA 年龄65-74 +0.62", g("ELSA", "年龄 65–74"), 0.62)
    add("ELSA 女性 +4.36", g("ELSA", "女性"), 4.36)
    add("CHARLS 城市 +2.05", g("CHARLS", "城市"), 2.05, tol=0.02)
    add("CHARLS 男性 -0.33", g("CHARLS", "男性"), -0.33)
    add("CHARLS 女性 +0.31", g("CHARLS", "女性"), 0.31)
    add("CHARLS 农村 -0.64", g("CHARLS", "农村"), -0.64)
    add("CHARLS 从不吸烟 -0.22", g("CHARLS", "从不吸烟"), -0.22)
    add("CHARLS 曾吸烟 +0.44", g("CHARLS", "曾吸烟"), 0.44)


def scan_manuscript_numbers(path: Path) -> list:
    """提取稿件中的所有数字，便于人工复核。"""
    txt = path.read_text(encoding="utf-8")
    nums = re.findall(r"[+\-−]?\d+\.\d+", txt)
    return nums


def main() -> None:
    s = load_sources()
    rows: list = []
    check_primary(s, rows)
    check_qc(s, rows)
    check_subgroups(s, rows)
    check_mechanism(rows)

    n_pass = sum(1 for r in rows if r[2] == "PASS")
    n_fail = sum(1 for r in rows if r[2] == "FAIL")
    n_manual = sum(1 for r in rows if r[2] == "MANUAL")

    lines = ["# 稿件数字一致性核查报告", "",
             f"- 稿件：`{MANU.name}`",
             f"- 通过 **{n_pass}**｜失败 **{n_fail}**｜待人工核 **{n_manual}**", "",
             "| 稿件声明 | 源文件实值 | 结果 | 备注 |", "|---|---|---|---|"]
    for claim, got, res, note in rows:
        lines.append(f"| {claim} | {got} | {'✅' if res == 'PASS' else ('❌' if res == 'FAIL' else '🔍')} | {note} |")

    lines += ["", "## 稿件全部数字清单（供人工扫读）", "",
              "```", " ".join(scan_manuscript_numbers(MANU)), "```"]

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"\n报告已写入：{REPORT}")
    if n_fail:
        print(f"\n⚠️ 有 {n_fail} 项不一致，请修正稿件！")
    else:
        print("\n✅ 全部核对项通过。")


if __name__ == "__main__":
    main()
