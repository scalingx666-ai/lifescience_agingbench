# Zenodo 上传元数据填写表（复制粘贴用）

> 上传地址：https://zenodo.org/uploads/new
> 建议上传类型：**Software**（若你希望别人以"下载代码复现"的视角引用）；若更强调数据/结果，可选 **Dataset**。
> 若走"代码+结果"混合包，**推荐 Software**，citation 更贴合。

---

## 1. 基本信息

| 字段 | 填写内容 |
|---|---|
| **Resource type** | Software |
| **Title** | Analysis code and summary results for: Tooth loss and accelerated biological ageing in later life: a cross-national comparison of three ageing cohorts |
| **Publication date** | 2026-10-10 |
| **Version** | 1.0.0 |
| **Language** | English |
| **DOI** | （留空，Zenodo 自动分配） |

---

## 2. Creators（作者，按顺序）

| 字段 | 填写内容 |
|---|---|
| 1 | Zhang, Churen |
| 2 | Han, Yangping |
| 3 | Liu, Zijian |
| 4 | Huang, Wenxia |

**Affiliation（四位统一填写）:**
`Department of Periodontology, Stomatological Hospital of Xiamen Medical College, Xiamen 361003, China`

**ORCID（仅第一作者有）:**
Zhang, Churen → `0000-0001-9070-7138`

---

## 3. Description（摘要，直接粘贴）

```
This archive contains the analysis code and summary result tables for a cross-national study of tooth loss (edentulism) and biological age acceleration in three population-based ageing cohorts (the Health and Retirement Study, the English Longitudinal Study of Ageing, and the China Health and Retirement Longitudinal Study), together with an independent cross-sectional extension in NHANES 2011-2014.

Biological age was estimated with the Klemera-Doubal method, and acceleration was defined as the residual after regression on chronological age. The pipeline covers cohort harmonisation of blood-based biomarkers, biological age estimation, cohort-specific linear models with meta-analysis, a region-by-exposure interaction test, a range of sensitivity analyses, and the NHANES inflammation extension.

The archive includes only code and derived summary results. Original cohort microdata are not redistributed and remain subject to each study's own access conditions. Derived harmonised data can be regenerated from the original files using the included build scripts.
```

---

## 4. Keywords（逐个添加）

```
tooth loss
edentulism
biological ageing
biological age acceleration
Klemera-Doubal method
C-reactive protein
inflammation
cross-national comparison
ageing cohorts
HRS
ELSA
CHARLS
NHANES
```

---

## 5. License

- **Code**: MIT License
- **Result tables and documentation**: CC BY 4.0

---

## 6. Related identifiers（可选，投稿后补）

| Relation | Identifier |
|---|---|
| is supplement to | （论文 DOI，录用后填） |
| is derived from | （如 HRS/ELSA/CHARLS/NHANES 官方门户 URL） |

---

## 7. 上传文件

- 推荐上传：`AgingCell_data_code_2026-10-10.zip`
- 若 Zenodo 自动解压后目录层级过深，可只传 zip 单文件。

---

## 8. ⚠️ 上传前检查清单

- [ ] zip 内**不含**任何原始队列微数据（HRS/ELSA/CHARLS/NHANES 原始文件）
- [ ] zip 内**不含** `harmonized_biomarkers.csv`（可由脚本再生，且含个体记录）
- [ ] zip 内**不含**稿件全文、cover letter、审稿人姓名邮箱
- [ ] 确认四位作者均同意按上述顺序署名公开
- [ ] 确认学校/医院对以 Zenodo 归档代码无额外审批要求
