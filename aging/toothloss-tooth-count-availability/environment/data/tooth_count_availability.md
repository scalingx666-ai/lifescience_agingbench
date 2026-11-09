# 剂量-反应（剩余牙数）可得性诊断

> 生成：`step16_tri_cohort_extras.py`｜**逐队列回原始码本核实**，不做假设

## 结论

**三队列（HRS/ELSA/CHARLS）的官方文件中均无连续「剩余牙数」变量**，
只有二分「是否全口失牙（edentulism）」。因此**剂量-反应无法在这三队列做真实估计**。

## 证据链

| 队列 | 文件 | 相关变量 | 性质 | 结论 |
|---|---|---|---|---|
| HRS | Harmonized HRS `H_HRS_d.dta` | `r8–r15noteeth` | 二分（0=no/1=yes，'lost all their teeth'） | ✗ 仅无牙颌 |
| HRS | 2016 core `H16C_R.dta` | `PC237` LOST PERMANENT TEETH | **分类档位**（1 / 5 / 8 / 9），5='5 or more'，非计数 | ✗ 非连续 |
| ELSA | Harmonized ELSA `h_elsa_g3.dta` | `r3/r5noteeth`；`r3/r5/r7dentalh` | 二分 + 自评口腔健康（有序） | ✗ 仅无牙颌/自评 |
| CHARLS | 2011/2013 Health_Status | `da040` Lost all of Teeth | 二分 | ✗ 仅无牙颌 |
| SHARE | harmonized 长表 | `remaining_teeth` | **连续 0–28**（实测 n=48,750） | ✓ 唯一可用 |

## 对稿件的处置建议

1. **Methods §2.2** 明确写：exposure 为二分 edentulism，因为三队列官方均无连续牙数；
   Limitations 已据此说明「无法描述剂量-反应」。
2. **若审稿人坚持要剂量-反应**，有两条可行路径：
   - 路径 A（推荐）：把 SHARE 纳入为**第四个队列**。SHARE 已有 `remaining_teeth`，
     可与已跑通的欧洲队列（ELSA）做「同一大陆内剂量-反应」补充分析，
     并作为 Supplementary Figure，不改动主结论。
   - 路径 B：改用**替代暴露**（如「缺牙年数」或「自报咀嚼困难」），
     但这两个变量跨队列构念不同构（config.py 已注明），可比性差，不推荐。
3. 现有 `sens_dose_response.csv` 里的 B1–B4 是 **SHARE 的认知轨迹**模型
   （随机斜率、n=46,575），**不是**本稿的缺牙×生物衰老剂量-反应，
   不可直接引用。

## SHARE `remaining_teeth` 分布（唯一可用队列）

- n = 48,750
- 中位 18｜均值 14.8｜SD 10.0｜范围 -2–28

| WHO 功能牙列分层 | n | % |
|---|---:|---:|
| 0（无牙颌） | 8,739 | 17.9% |
| 1–9 | 7,092 | 14.5% |
| 10–19 | 9,506 | 19.5% |
| ≥20（参照） | 22,734 | 46.6% |