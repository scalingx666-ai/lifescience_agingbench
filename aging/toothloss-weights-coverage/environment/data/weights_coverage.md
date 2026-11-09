# 抽样权重覆盖率与来源

> 生成：`step16_tri_cohort_extras.py`｜逐个从 Harmonized 官方文件核实

| 队列 | 权重变量 | 口径 | 来源文件 | 权重>0 人数 |
|---|---|---|---|---:|
| HRS | `r13nwtresp` | w13 物理测量样本权重（2016） | Gateway Harmonized HRS `H_HRS_d.dta` | 7,869 |
| ELSA | `r4cwtresp` | w4 核心样本横截面权重（2008/9） | Harmonized ELSA `h_elsa_g3.dta` | 9,805 |
| CHARLS | `Biomarker_weight` | 血样权重（含家户+个体无应答调整，2015） | CHARLS 2015 `Weights.dta` | 12,903 |

**命中共线性检查**：加权与未加权估计若差异 <0.3 年，说明抽样设计不改变结论。
