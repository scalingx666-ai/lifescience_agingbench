# -*- coding: utf-8 -*-
"""
多队列口腔功能衰退 × 认知轨迹  ——  分析工程配置
==================================================
所有路径、队列元数据、变量字典、模型设定集中在此文件。
改数据/改模型只改这里，其余脚本不用动。
"""
import os
from pathlib import Path

# ---------- 路径 ----------
ROOT       = Path(__file__).resolve().parents[1]        # 02_数据分析/
DATA_RAW   = ROOT / "data" / "raw"                       # 各队列原始文件放这里
DATA_HARM  = ROOT / "data" / "harmonized"                # 协调化后的长表
OUT_TAB    = ROOT / "output" / "tables"
OUT_FIG    = ROOT / "output" / "figures"
for _d in (DATA_RAW, DATA_HARM, OUT_TAB, OUT_FIG):
    _d.mkdir(parents=True, exist_ok=True)

# ---------- 分析框架（时间轴口径）----------
# ⚠️ 2026-10-07 投稿前审查（P0 时序缺陷）后的定案：
#   · "anchored"（默认，**主分析**）= 以「该人首次实测口腔暴露的波次」为 t=0，
#     只保留 year ≥ 暴露年的观测。由 step1c_anchor.py 生成。
#     理由：原口径下 38.9% 的个体（HRS 93.6%/ELSA 83.8%/SHARE 64.1%）暴露实测
#     晚于首次认知观测 → 未来暴露被用到过去结局上，与「前瞻设计」声明矛盾。
#   · "original" = 以「该人首次观测年」为 t=0（旧口径，含暴露前观测），
#     现降为敏感性分析（Supplementary S6）。
# 用法：设环境变量 ANALYSIS_FRAME=original 即可整套切回旧口径复算。
ANALYSIS_FRAME = os.environ.get("ANALYSIS_FRAME", "anchored").strip().lower()
_FRAME_FILE = {
    "anchored": "harmonized_long_anchored.csv",
    "original": "harmonized_long.csv",
}
if ANALYSIS_FRAME not in _FRAME_FILE:
    raise ValueError(f"ANALYSIS_FRAME 只能是 {list(_FRAME_FILE)}，收到 {ANALYSIS_FRAME!r}")
HARM_LONG = DATA_HARM / _FRAME_FILE[ANALYSIS_FRAME]      # ← 全管线统一入口
HARM_FILE_NAME = _FRAME_FILE[ANALYSIS_FRAME]

# ---------- 队列清单 ----------
# 5 队列主分析 + NHANES 仅作客观测量校准（不进主模型）
COHORTS = ["CHARLS", "HRS", "ELSA", "SHARE", "KLoSA"]
CALIBRATION_COHORT = "NHANES"

# ---------- 变量字典（一手核实结果，2026-10）----------
# status: verified = 已下载官方一手文件逐字确认；flagged = 变量名待从数据文件最终确认
VAR_DICT = {
    "CHARLS": {
        "edentulism": {
            "var": "DA040",
            "label_en": "Have you lost all of your teeth?",
            "label_zh": "您的牙齿是否已经掉光？",
            "coding": {1: 1, 2: 0},          # 1=是(无牙颌) / 2=否
            "waves": {"2011": "W1 全国基线", "2013": "W2", "2015": "W3", "2018": "W4"},
            "source": "官方 2011 家户问卷 .doc + 2013/2015/2018 Codebook",
            "status": "verified",
        },
        "denture":  {"var": "da040_w4_1", "waves": {"2018": "W4 仅此一次"}, "status": "verified",
                     "note": "Wear Denture, 29.73%"},
        "chewing":  {"var": "da040_w4_2", "waves": {"2018": "W4 仅此一次"}, "status": "verified",
                     "note": "Difficulty Chewing Hard Food, 38.29%"},
        "oral_visit": {"var": "eh001-eh003(2013) / eh002-eh006(2015)", "status": "verified"},
        "cognition": {
            "var": "词表即时回忆 + 延迟回忆 + 连续减 7 + 定向（复合分）",
            "status": "verified",
            "note": ("即时/延迟回忆为**逐词记录**（2011/2013/2015=dc006s*/dc027s*；2018=dc028_w4_s*/dc047_w4_s*；"
                     "2020=dc012_s*/dc028_s*），须按项计分；定向力 dc001s1-3+dc002+dc003（2018/2020 另名）。"),
        },
        "note": "无客观牙周检查；2020(W5) 无任何口腔变量。无牙颌可做 2011→2018 四次重复测量。",
    },
    "HRS": {
        "edentulism": {
            "var": "C237",                      # Blaise 名 C237_Lostpermteeth
            "raw_var": "r11c237（2012=Wave11）/ r8c237（2006=Wave8）/ r14c237（2018=Wave14）",
            "label_en": "Have you lost all of your upper and lower natural permanent teeth?",
            "label_zh": "您是否已失去全部上下颌天然恒牙？",
            "coding": {1: 1, 5: 0},             # 1=YES(无牙颌) / 5=NO / 8=DK / 9=RF
            "waves": {"2006": "Wave 8", "2012": "Wave 11（常作基线）", "2018": "Wave 14"},
            "prevalence": "~12.2% (2012)",
            "skip_logic": "新受访者每波必答；核心重访者仅每三波一次（2006→2012→2018→2024）",
            "source": "HRS 官方 Section C 问卷 PDF 六份（2006/2010/2012/2014/2018/2022）逐字确认",
            "status": "verified",
        },
        "cognition": {
            "var": "cog27（Langa-Weir 总分，RAND HRS）",
            "status": "verified",
            "note": ("RAND HRS 命名 R{w}IMRC/R{w}DLRC/R{w}SER7/R{w}MSTOT/R{w}COGTOT/R{w}COG27；"
                     "w = HRS 波号（2006=W8 / 2012=W11 / 2018=W14）。⚠️ 需 RAND HRS 或 HRS 认知插补文件。"),
        },
        "note": "无客观牙周检查。另：2018 波存在『口腔健康与口腔服务』实验模块（随机子样本，n≈1,268），含自评口腔健康/失牙数/义齿/OHRQoL 五条目 —— 可作敏感性分析或补充分析，但非全样本。",
    },
    "ELSA": {
        "edentulism": {
            "var": "HEDENT",
            "label_en": "In relation to dental health, which of the following applies to you?",
            "label_zh": "就您的牙科健康而言，以下哪种情况符合您？",
            "coding": {1: 1, 2: 0, 3: 0, 4: 1},  # 1无牙+义齿/4两者皆无 = 无牙颌；2/3 = 有天然牙
            "waves": {"W3": "2006-07（已确认）", "W5": "2010-11（同模块重复，变量名沿用）"},
            "source": "ELSA Wave 3 官方 codebook（UKDS SN5050 文档，变量位置 P2496）逐字确认",
            "status": "verified",
        },
        "tooth_count_cat": {
            "var": "HEDNTD",
            "label_en": "How many natural teeth have you got? (None at all / 1-9 / 10-19 / 20 or more)",
            "waves": {"W7": "2014-15（仅此一次；可二分为 <20 牙 vs ≥20 牙）"},
            "source": "ELSA Wave 7 官方问卷 PDF 逐字确认",
            "status": "verified",
        },
        "self_rated_oral": {"var": "HEDNTA", "label_en": "dental health excellent→poor",
                            "waves": {"W3": "2006-07", "W7": "2014-15"}, "status": "verified"},
        "OIDP": {"var": "HEDNTB", "label_en": "5 条目口腔影响量表（吃/说/笑/情绪/社交）",
                 "waves": {"W3": "2006-07", "W7": "2014-15"}, "status": "verified"},
        "denture_upper": {"var": "HEDNTF", "waves": {"W7": "2014-15"}, "status": "verified"},
        "denture_lower": {"var": "HEDNTG", "waves": {"W7": "2014-15"}, "status": "verified"},
        "cognition": {
            "var": "记忆（memory）+ 执行功能（executive）复合分",
            "status": "verified",
            "note": "即时 CFLISEN / 延迟 CFLISD；执行功能 CFANI（动物流畅）+ 字母划消；总分 CFIND。",
        },
        "note": "口腔暴露在 W3 / W5 / W7 三波。W3 与 W5 为四分类『牙科健康状态』题（无牙颌+义齿/天然牙+义齿/仅天然牙/两者皆无）；W7 改为分类牙数。W3/W5 → 轨迹（2 点）；W7 → 功能牙列（<20 牙）。",
    },
    "SHARE": {
        "missing_teeth": {
            "var": "PH092_MissingNatTeeth",
            "label_en": "number of missing natural teeth (1-30)",
            "transform": "remaining = 28 - PH092",
            "waves": {"W5": "2013（仅此一次）"},
            "source": "SHARE W5 官方问卷 + Scales Manual rel.8",
            "status": "verified",
        },
        "all_natural":  {"var": "PH091_AllNaturTeeth", "waves": {"W5": "2013"}, "status": "verified"},
        "artificial":   {"var": "PH094_ArtificialTeeth", "waves": {"W5": "2013"},
                         "label_en": "Fully / Partially / Not at all（修复程度三分级）", "status": "verified"},
        "oral_visit":   {"var": "HC010_SNaDentist", "waves": {"W5": "2013", "W6": "2015", "W7": "2017", "W8": "2019-20"},
                         "status": "verified"},
        "cognition": {
            "var": "认知模块 CF（即刻 / 延迟词表回忆 + 言语流畅）",
            "status": "verified",
            "note": "即时 cf008tot / 延迟 cf016tot（gv_health 生成变量，另见 cf 模块原始题 cf008/cf016）；流畅 cf010_。",
        },
        "note": "牙齿变量只在 W5。无咀嚼变量。→ 只能做 W5 单波暴露 + 后续认知随访（窗口可达 8 年）。",
    },
    "KLoSA": {
        # 2026-10-02 第二轮一手核实：KEIS 官网从本机链路不可达，改用两条**本地可达**通道取到官方一手文件：
        #   ① 镜像 medaibox.com → 《KLoSA Wave 9 官方码本》(xlsx)
        #   ② OSF 公开注册 osf.io/8cnwu → 《KLoSA W8 结构化码本》+《W8 问卷》+《2024 User Guide》
        # 结论 A（终判）：口腔模块（牙数 + GOHAI）**自 Wave 7（2018）起新增**。官方 User Guide 原文：
        #   "The number of natural teeth variables was newly created by adding relevant questions
        #    (Cadd_06) in Wave 7"；"…newly created by adding related items to Wave 7 (Cadd_07~Cadd_18,
        #    12 questions)"；且变更清单标题即「Added/Modified questions in Wave 7」。
        #   → 此前据 G2G 索引得出的「始自 2020」系**假阴性**（G2G 2016/2018 索引不全，overview_id=null），已纠正。
        # 结论 B（头号陷阱）：**G2G 题目库/问卷题号 ≠ 数据集变量名**。
        #   问卷 C093/C094/C095 = 戴义齿/戴义齿咀嚼/不戴义齿咀嚼；
        #   数据集 w08C085/C086/C087 = 同三题；而数据集 w08C093/C094/C095 = 手指痛/胸痛/胃痛。
        #   ⇒ 按题号硬编码取数会**静默取错列** → 抽取一律先按**变量标签**匹配。
        "edentulism": {
            "var": "naturalteeth（结构化/轻量版派生变量；官方名 w__naturalteeth）",
            "derive_from": "Cadd_06a–d 四小项",
            "formula": "naturalteeth = (28 + Cadd_06d 剩余智齿) − Cadd_06a 种植牙 − Cadd_06b 义齿内牙 − Cadd_06c 待修复缺失牙",
            "label_en": "Number of natural teeth (including wisdom teeth)",
            "label_zh": "天然牙数（含智齿）",
            "coding": "edent = 1 if naturalteeth == 0 else 0",
            "waves": {"2018": "W7（模块首次引入）", "2020": "W8", "2022": "W9"},
            "source": "KLoSA 官方 2024 User Guide + W8/W9 官方码本",
            "status": "verified",
        },
        "teeth_battery": {
            "var": "Cadd_06a / Cadd_06b / Cadd_06c / Cadd_06d",
            "dataset_var": "w07Cadd_06a … w09Cadd_06d",
            "label_en": ("Number of implant teeth / Number of teeth in dentures / Number of teeth that need "
                         "implant or denture treatment but are left missing / Number of wisdom teeth remaining now"),
            "sentinel": "全口义齿填 100（按 28 颗假牙计）；单颌全口义齿填 55",
            "waves": {"2018": "W7 起", "2020": "W8", "2022": "W9"},
            "source": "W8 问卷 <Dental health> 原题 + W8/W9 官方码本逐字确认",
            "status": "verified",
        },
        "denture_wear": {
            "var": "C085（数据集名）",
            "dataset_var": "w07C085 … = Usual usage of dentures",
            "questionnaire_no": "C093（问卷/G2G 题号；⚠️ 不等于数据集变量名）",
            "label_en": "Now I have some questions about your dental health. Do you wear dentures?",
            "coding": {1: 1, 5: 0},
            "waves": {"2018": "W7", "2020": "W8", "2022": "W9"},
            "status": "verified",
            "warning": "W7 及更早波的**数据集变量名**未逐波核实（本机仅有 W8/W9 码本）→ 早期波按**变量标签**匹配，勿按题号硬编码。",
        },
        "chew_with_denture": {
            "var": "C086（数据集名）",
            "dataset_var": "w07C086 … = Hard food mastication with denture",
            "questionnaire_no": "C094",
            "label_en": "How easily can you chew solid foods, such as meat or apples, if you wear dentures?",
            "coding": {1: "Very well", 2: "Pretty well", 3: "Fair", 4: "Not well", 5: "Not at all"},
            "waves": {"2018": "W7", "2020": "W8", "2022": "W9"},
            "status": "verified",
        },
        "chew_without_denture": {
            "var": "C087（数据集名）",
            "dataset_var": "w07C087 … = Hard food mastication without denture",
            "questionnaire_no": "C095",
            "label_en": "How well can you chew solid foods, such as meat or apples, without dentures?",
            "coding": {1: "Very well", 2: "Pretty well", 3: "Fair", 4: "Not well", 5: "Not at all",
                       "note": "数值越大越差；正向分 = 6 − 原值"},
            "waves": {"2018": "W7", "2020": "W8", "2022": "W9"},
            "status": "verified",
        },
        "GOHAI": {
            "var": "Cadd_07 … Cadd_18（12 条目）",
            "dataset_var": "w07Cadd_07 … w09Cadd_18；派生变量 w__gohai",
            "label_en": "Geriatric Oral Health Assessment Index（韩版 12 条目，6 点量表 Always→None）",
            "scoring": "每项 0–5；**反向计分 3 项**（Cadd_09 吞咽舒适 / Cadd_11 进食无不适 / Cadd_13 满意外观）；总分 0–60，越高越好",
            "waves": {"2018": "W7 起", "2020": "W8", "2022": "W9"},
            "source": "官方 User Guide（指定 Cadd_09/11/13 反向计分）+ W8/W9 码本",
            "status": "verified",
        },
        "oral_visit": {
            "var": "问卷题号 CC27(2006) / C330(2008-2012) / C348(2014-2022)",
            "label_en": "number of dental visits since previous interview",
            "note": "⚠️ 上述为**问卷题号**，数据集变量名待核（受同一陷阱影响）；仅作辅助变量，不进主模型。",
            "status": "flagged",
        },
        "cognition": {
            "var": "K-MMSE 各条目（C4. Cognition 模块，题号 C401–C419）",
            "items": ("即时 3 词回忆 `C406`（0–3）/ 延迟 3 词回忆 `C412`（0–3）/ "
                      "时间·地点定向 `C402`(星期) `C403`(季节) `C404`(地点) `C405` / "
                      "连续减 7 `C407`–`C411`（0–5）/ 命名 `C413`(表) `C414`(笔) / "
                      "复述句 `C415` / 三步指令 `C416` / 闭眼 `C417` / 写句 `C418` / 画五边形 `C419`"),
            "note": ("2026-10-05 最终结论（G2G 题库 API 逐题核对 + 已发表论文交叉印证）：\n"
                     "  ① **模块与题号已一手确认**：KLoSA 主问卷 C 节存在独立的「C4. Cognition」模块"
                     "（`module_title='C4. Cognition'`），题号 C401–C419；其中 C401 为导语（非计分），"
                     "C402–C419 为 K-MMSE 条目。已发表论文亦有硬证据："
                     "“The Mini-Mental State Examination score [C401‐C419 in the KLoSA inquiries]”(PMC6851663)。\n"
                     "  ② **即时/延迟回忆口径**：均为 **3 词**（0–3 分），与其余队列 10 词不可直接等同 —— "
                     "这是跨队列比较的硬限制，必须在局限性中明写。\n"
                     "  ③ **落库路线（2026-10-05 定案）= 走 Harmonized KLoSA**：原始数据集列名"
                     "不在 KEIS 公开分发的 W8/W9 码本中（Section 仅 CV/A/Ba/Bb/C/D/E/F/G，须另申请授权）；"
                     "故改按 **G2G 协调化命名**取数 —— 即时 `RwIMRC_K`(C406) / 延迟 `RwDLRC_K`(C412)"
                     "（CANDID《Cognitive Data Guide》逐队列对照表确认；KLoSA 记忆题为 3 词 MMSE，"
                     "故带 `_K` 访问研究后缀，与 MHAS=`_M`、CRELES=`_CR` 同律）。\n"
                     "  ④ 状态 = **harmonized**（协调化命名已定案、适配器已就绪）；备路线 raw_qno"
                     "（KEIS 原始 C4xx 列名）待授权数据落地后核对。两条路并存，取列后**强制校验变量标签**"
                     "并在日志标注来源。"),
            "status": "harmonized",
        },
        "note": ("无牙颌轨迹：W7→W8→W9（2018/2020/2022，跨 4 年），与认知随访同期对齐；"
                 "义齿/咀嚼为长期重复测量（W7–W9 已核；更早波待核）。KLoSA 全问卷**无**"
                 "『是否失去全部牙齿』题 → 无牙颌只能由天然牙数级联推导。"
                 "咬合/咀嚼量表与 ELSA(OIDP)/CHARLS(二分咀嚼困难) 不同构，不可直接合并。"),
    },
}

# ---------- KLoSA 抽取规格（机器可读；与上方 VAR_DICT['KLoSA'] 互为对照）----------
KLOSA_WAVE_YEAR = {1: 2006, 2: 2008, 3: 2010, 4: 2012, 5: 2014, 6: 2016, 7: 2018, 8: 2020, 9: 2022}

# ⚠️⚠️ 头号陷阱（2026-10-02 一手证实）：G2G 题目库 / 问卷题号 ≠ KLoSA 数据集变量名。
#   问卷（W8）C093/C094/C095 = 戴义齿 / 戴义齿咀嚼 / 不戴义齿咀嚼；
#   数据集（W8 官方码本）w08C085/C086/C087 = 同三题；
#   而数据集 w08C093/C094/C095 = 「手指痛 / 胸痛 / 胃痛」。
#   ⇒ 按题号硬编码取数会静默取错列 → **一律先按变量标签匹配**，代码表仅作后备且命中后仍校验标签。
KLOSA_ORAL_LABEL_PHRASES = {           # 归一化后的标签短语（小写、去非字母数字）
    "denture_wear": "usualusageofdentures",
    "chew_with":    "hardfoodmasticationwithdenture",
    "chew_without": "hardfoodmasticationwithoutdenture",
}
KLOSA_DENTURE_CHEW_CODES = {           # W7–W9 官方码本数据集变量名（后备）
    "denture_wear": "c085", "chew_with": "c086", "chew_without": "c087",
}
KLOSA_ORAL_MODULE_FIRST_YEAR = 2018    # 口腔模块（牙数电池 + GOHAI）自 Wave 7（2018）起

# 牙数电池 Cadd_06a–d（官方语义：种植牙 / 义齿内牙 / 待修复缺失牙 / 剩余智齿）
KLOSA_TEETH_BATTERY = "cadd_06"        # 兼容写法（若数据里是单列）
KLOSA_TEETH_SUBITEMS = {"implant": "cadd_06a", "denture_teeth": "cadd_06b",
                        "missing_untreated": "cadd_06c", "wisdom": "cadd_06d"}
KLOSA_TEETH_BATTERY_SUBITEMS = list(KLOSA_TEETH_SUBITEMS.values())          # 兼容旧名
KLOSA_TEETH_BATTERY_SUBITEMS_OLD = [f"cadd_06_{k}" for k in (1, 2, 3, 4)]   # 旧猜测写法（一并兜底）

# GOHAI（Cadd_07–18；官方指定 Cadd_09/11/13 反向计分）
KLOSA_GOHAI_ITEMS   = [f"cadd_{i:02d}" for i in range(7, 19)]
KLOSA_GOHAI_REVERSE = ["cadd_09", "cadd_11", "cadd_13"]
KLOSA_DERIVED = {"natural_teeth": "naturalteeth", "gohai": "gohai"}         # 结构化/轻量版派生变量

# 认知：KLoSA 主问卷 C 节存在独立的「C4. Cognition」模块（题号 C401–C419），
#   题号已由 G2G 题库 API 逐题核对（2026-10-05）+ 论文 [C401-C419] 交叉印证；
#   但 **C4 段不在 KEIS 公开分发的 W8/W9 码本中** → 数据集列名须授权后或走 Harmonized KLoSA。
# ⇒ **落库路线（2026-10-05 定案）= harmonized**：按 G2G 协调化命名取数（见下方 KLOSA_HARMONIZED_COG），
#   备路线 raw_qno（按 KEIS 原始 C4xx 题号取列）保留，供授权数据落地后核对。
#   两条路取列后**都必须校验变量标签**（含 word/recall/orient/단어/기억 等），
#   标签不符即告警并记录 cog_src=⚠️qno_unverified，供人工终判。
#   ⚠️ W1(2006) 为旧编号：即时回忆 CD06 / 连续减7 CD07A / 延迟回忆 CD12（本适配器不覆盖 W1，留档）。
#   ⚠️ C4 内部题号**跨波有漂移**：C401 在 2016+ 波为模块导语，而 C405 在 2012/2014 波为「地址定向」；
#      但**核心题号稳定**（C406 即时 / C407 起减7 / C412 延迟 / C419 画图，各波一致）→ 主结局不受影响。
KLOSA_COG_STATUS = "harmonized"        # 主路线：G2G 协调化命名（RwIMRC_K / RwDLRC_K）
KLOSA_COG_STATUS_RAW = "qno_verified"  # 备路线：KEIS 原始 C4xx 题号（数据集列名待授权核对）
KLOSA_COG_MAP = {
    # K-MMSE（KLoSA「C4. Cognition」模块，逐题语义已核对）
    "immediate":   ["c406"],                                    # 即时 3 词回忆（0–3）
    "delayed":     ["c412"],                                    # 延迟 3 词回忆（0–3）
    "orientation": ["c402", "c403", "c404"],            # 星期/季节/地点；⚠️ C401 为导语、C405=地址定向(2012/2014)，跨波题号有漂移
    "serial7":     ["c407", "c408", "c409", "c410", "c411"],    # 连续减 7（0–5）
    "naming":      ["c413", "c414"],                            # 命名：表/笔（0–2）
    "phrase":      ["c415"],                                    # 复述句子（0–1）
    "command":     ["c416"],                                    # 三步指令（0–3）
    "eyes":        ["c417"],                                    # 闭眼（0–1）
    "sentence":    ["c418"],                                    # 写一句完整句子（0–1）
    "pentagon":    ["c419"],                                    # 画重叠五边形（0–1）
}
KLOSA_COG_MAP_W1_OLD = {"immediate": ["cd06"], "serial7": ["cd07a"], "delayed": ["cd12"]}   # 留档
KLOSA_COG_ALIASES = ["mmse", "kmmse", "mmsescore", "mmsetotal"]   # 优先尝试的派生 K-MMSE 总分
KLOSA_COG_VERIFY_LABELS = ["word", "recall", "delayed", "immediate", "orient", "memory",
                           "season", "week", "place", "pentagon", "subtract", "sentence",
                           "name", "repeat", "단어", "기억", "회상"]   # 命中列的标签至少含其一才认

# ---------- Harmonized KLoSA（G2G 协调化）认知规格：主路线 ----------
# 决策（2026-10-05）：KLoSA 认知改走 **Harmonized KLoSA**，绕开「KEIS 原表 C4xx 列名须授权码本」卡点。
# 一手依据：CANDID《Cognitive Data Guide》（本地归档 evidence/candid_cognitive_data_guide.pdf, 103 页）
#   逐队列对照表 —— KLoSA 协调化名：即时 `RwIMRC_K`(C406) / 延迟 `RwDLRC_K`(C412)
#   / 连续减7 `RwSER7`(C407–C411) / 日期 `RwDAT`(C401) / 星期 `RwDW`(C402)
#   / 定向 `RwORIENT`(C401+C402) / 画图 `RwDRAW`(C419)（‘w’ = 波号）。
# 命名规约：G2G 协调化文件为『人×波』**宽表**（每人一行，各波变量带 `r{波号}` 前缀）；
#   概念若与其它队列**不可比**则加访问研究后缀 —— KLoSA 记忆题是 MMSE **3 词**（其余队列 10 词）
#   ⇒ 记忆两变量带 `_K`（`RwIMRC_K`/`RwDLRC_K`），其余概念**不带**后缀（对照 MHAS=`_M`、CRELES=`_CR`）。
#   数据集内列名一律小写 → `r{w}imrc_k` / `r{w}dlrc_k` / `r{w}ser7` / `r{w}draw` …
#   ⚠️ 大小写与实际列名以数据落地时的抽取日志为准（本适配器**大小写不敏感** + 标签兜底 + 强制校验标签）。
# 波次：K-MMSE 于 W3–W6（2010–2016）确认施测（CANDID）；W7/W8（2018/2020）主问卷仍含 C4 模块
#   （G2G 题库 API 逐题核实 C406/C412/C419 命中）⇒ **与口腔暴露波次重叠，KLoSA 可进主模型**。
KLOSA_HARMONIZED_SUFFIX_DOC = "G2G 协调化：记忆题带 _K 后缀（不可比概念），其余不带后缀"
KLOSA_HARMONIZED_COG = {
    # concept: {stem, suffix, valid, labels}
    "immediate":   {"stem": "imrc",   "suffix": "_k", "valid": (0, 15),
                    "labels": ["immediate word recall", "word immediate recall", "immediate recall"]},
    "delayed":     {"stem": "dlrc",   "suffix": "_k", "valid": (0, 15),
                    "labels": ["delayed word recall", "word delayed recall", "delayed recall"]},
    "serial7":     {"stem": "ser7",   "suffix": "",   "valid": (0, 5),
                    "labels": ["serial 7", "serial7"]},
    "orientation": {"stem": "orient", "suffix": "",   "valid": (0, 9),
                    "labels": ["orientation"]},
    "date":        {"stem": "dat",    "suffix": "",   "valid": (0, 3),
                    "labels": ["date"]},
    "dayofweek":   {"stem": "dw",     "suffix": "",   "valid": (0, 1),
                    "labels": ["day of the week"]},
    "drawing":     {"stem": "draw",   "suffix": "",   "valid": (0, 1),
                    "labels": ["drawing", "pentagon"]},
}
KLOSA_HARMONIZED_COG_WAVES = [3, 4, 5, 6, 7, 8, 9]        # 认知可得波（波号）；W1(2006) 旧编号另存

KLOSA_ALIASES = {          # 别名（大小写/下划线不敏感；找不到时回退到变量标签匹配）
    "id":         ["pid", "p_id", "id", "idind", "hhidpn", "caseid", "hhid", "householdid"],
    "age":        ["age", "agey", "cage", "age_y", "age_year"],
    "female":     ["gender", "sex", "female", "c002"],
    "edu_years":  ["edu", "eduy", "edu_y", "education", "educyear", "yearsofeducation"],
    "married":    ["marital", "maritalstatus", "married", "mstat", "marriage"],
    "rural":      ["rural", "urban", "region", "area", "urbanicity", "ruralurban"],
    "ever_smoke": ["eversmoke", "smoke", "smoking", "cigarette", "smokeev"],
}
KLOSA_VALID = {            # 有效值区间；区间外（DK/RF/异常码）一律置 NaN
    "denture_wear": (1, 5), "chew_with": (1, 5), "chew_without": (1, 5),
    "gohai_item": (1, 6), "oral_visit": (0, 3650),
}

# ==========================================================================
# 五队列：通用适配器规格（机器可读）
# --------------------------------------------------------------------------
# 设计原则（与 KLoSA 段同源）：
#   · 暴露 / 次要暴露：**已回官方码本核实的变量名放在 codes**（dataset 变量名，非问卷题号）；
#     通用引擎按 priority 先试 codes、再试 labels；命中来源写入诊断日志。
#   · 认知（cog）：2026-10-02 逐队列回官方码本核实（status=verified）；
#     KLoSA=harmonized（走 G2G 协调化命名 RwIMRC_K/RwDLRC_K；备路线 raw_qno 保留）。
#     结构固定为 episodic.immediate / episodic.delayed（主结局「情景记忆」两分量）+ mental.* + total。
#     字段可用 by_year 做**逐波覆盖**（CHARLS 各波命名差异极大，必须逐波给）。
#     逐词记录型（items）由 step1._score_items 按官方计分规则汇总；命中列名 + 标签全部写日志。
#     **取不到认知 → 该波跳过**（不产生无信息记录），绝不用可疑列硬凑。
#   · 多文件/多模块（如 SHARE 的 gv_health + cf）→ 按 id 外连接合并。
# ==========================================================================

# 协变量通用别名（各队列可按需覆盖；KLoSA 用 config.KLOSA_ALIASES）
GENERIC_ALIASES = {
    "id":         ["mergeid", "hhidpn", "idauniq", "idind", "personalid", "caseid", "householdid", "id"],
    "age":        ["age", "agey", "ragey", "age_y", "age_year", "ageint"],
    "female":     ["ragender", "indsex", "gender", "sex", "female", "ragender"],
    "edu_years":  ["eduyears", "educyears", "edu_y", "education", "isced", "edu", "radeg"],
    "married":    ["mstat", "maritalstatus", "marital", "married", "marstat", "couple"],
    "rural":      ["rural", "urbanrural", "urban", "region", "area", "urb"],
    "ever_smoke": ["eversmoke", "smokeev", "smoking", "smoke", "cigarette", "smokev"],
}

# ---- HRS 核心问卷（非 RAND）原始认知变量名后备映射 ------------------------------
# 用途：当只下到 HRS 核心问卷文件（无 RAND HRS Longitudinal File / 认知插补文件）时仍能取到认知；
#       仅作 RAND 命名（r8imrc/r11imrc…）取不到时的**后备**。
# 命名规约：核心问卷 = **波次首字母前缀 + 题号**（RAND HRS Fat File 首字母表；
#           Ofstedal et al. DR-006 Table 3 逐波列名核对）：
#           2006=K(W8) / 2008=L / 2010=M / 2012=N(W11) / 2014=O(W12) / 2016=P / 2018=Q(W14) / 2020=R
# 逐题（以 W11=N 为例，G2G 题库 API 逐题核对 2026-10-05）：
#   ND103 学习 10 词 → ND106M「Now please tell me the words you can recall」= 即时回忆；
#   ND142–ND146 = 连续减 7 五次（原始数字，非得分）；ND148M = 延迟回忆。
# ⚠️ 核心问卷的减 7 存**原始数字** → 须走 score=subtract7 官方计分（同 CHARLS）。
HRS_CORE_PREFIX = {2006: "k", 2008: "l", 2010: "m", 2012: "n",
                   2014: "o", 2016: "p", 2018: "q", 2020: "r"}
HRS_CORE_COG = {
    "immediate": {y: [f"{p}106m", f"{p}106"] for y, p in HRS_CORE_PREFIX.items()},
    "delayed":   {y: [f"{p}148m", f"{p}148"] for y, p in HRS_CORE_PREFIX.items()},
    "serial7":   {y: [f"{p}142", f"{p}143", f"{p}144", f"{p}145", f"{p}146"]
                  for y, p in HRS_CORE_PREFIX.items()},
}

COHORT_PROFILES = {
    "CHARLS": {
        "dir": "CHARLS",
        "wave_years": [2011, 2013, 2015, 2018],   # 2020(W5) 无任何口腔变量
        "base_year": 2011,
        "base_wave": 1,                            # 2011 = Wave 1（供「按波次号命名」的文件换算年份）
        "carry_baseline_exposure": False,          # 暴露在每波都有 → 无需前移
        "priority": "code",
        "id_aliases": ["id", "householdid", "hhid", "pid", "personalid", "personal_id"],
        "doc_keywords": ["codebook", "questionnaire", "qnaire", "readme", "dictionary",
                         "guide", "mapping", "label", "harmonized", "code_book"],
        "exposure": {
            "codes": ["da040"],
            "labels": ["lostallyourteeth", "lostallofyourteeth", "lostallofteeth", "lostallteeth"],
            "coding": {1: 1, 2: 0}, "valid": (1, 2),
            "note": "1=是(牙齿掉光) / 2=否；无牙颌。2011/2013/2015/2018 四波。无牙齿数变量。",
        },
        "secondary": {
            "denture": {"codes": ["da040_w4_1"], "labels": ["weardenture"],
                        "coding": {1: 1, 2: 0}, "valid": (1, 2), "note": "仅 2018"},
            "chew":    {"codes": ["da040_w4_2"], "labels": ["difficultychewinghardfood", "chewinghardfood"],
                        "coding": {1: 1, 2: 0}, "valid": (1, 2), "note": "仅 2018；二分困难"},
        },
        "oral_visit": {"codes": ["eh001", "eh002", "eh003", "eh004", "eh005", "eh006"],
                       "labels": ["dentalvisit", "dentist", "dentalcare"]},
        "cog": {
            "status": "verified",
            "source": ("CHARLS 官方问卷原件 + G2G 题库 API（2026-10-05 终判）：即时/延迟回忆的逐词记录"
                       "变量名、定向力 5 项、**连续减 7 = DC019–DC023**、**画图 = DC025** 均逐波核对；"
                       "2018(W4) 起减 7 = DC014_W4_1–5、画图 = DC024_W4。"),
            "episodic": {
                "immediate": {
                    # 逐词记录 → 需按项计分（见 step1 _score_items）
                    "by_year": {
                        "2011": {"items": {"pattern": r"^dc006s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                        "2015": {"items": {"pattern": r"^dc006s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                        "2013": {"items": {"pattern": r"^dc006_1_s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11}}},
                        "2018": {"items": {"pattern": r"^dc028_w4_s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                        "2020": {"items": {"pattern": r"^dc012_s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                    },
                    "labels": ["immediate word recall", "immediate recall", "word recall"],
                    "valid": (0, 10),
                    "note": "第 1 试次即时回忆；2018 年起改用 HCAP 词表并有 3 轮即时回忆，本变量只取第 1 试次。",
                },
                "delayed": {
                    "by_year": {
                        "2011": {"items": {"pattern": r"^dc027s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11}}},
                        "2013": {"items": {"pattern": r"^dc027s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11}}},
                        "2015": {"items": {"pattern": r"^dc027s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                        "2018": {"items": {"pattern": r"^dc047_w4_s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                        "2020": {"items": {"pattern": r"^dc028_s(\d{1,2})$", "n_items": 10,
                                           "special": {"none": 11, "refuse": 12}}},
                    },
                    "labels": ["delayed word recall", "delayed recall"],
                    "valid": (0, 10),
                },
            },
            "mental": {
                "orientation": {
                    "by_year": {
                        "2011": {"codes": ["dc001s1", "dc001s2", "dc001s3", "dc002", "dc003"]},
                        "2013": {"codes": ["dc001s1", "dc001s2", "dc001s3", "dc002", "dc003"]},
                        "2015": {"codes": ["dc001s1", "dc001s2", "dc001s3", "dc002", "dc003"]},
                        "2018": {"codes": ["dc001_w4", "dc006_w4", "dc003_w4", "dc005_w4", "dc002_w4"]},
                        "2020": {"codes": ["dc001", "dc005", "dc003", "dc004", "dc002"]},
                    },
                    "sum_codes": True, "valid": (0, 5),
                    "note": ("5 项（年/月/日/星期/季节）正确数之和（0–5）。⚠️ 同名题号跨波含义漂移："
                             "dc002 早期=星期、2020=季节；dc003 早期=季节、2020=日期 → 必须按波取。"),
                },
                "serial7": {
                    # 连续减 7 存的是**受访者报出的原始数字**（93/86/79…），不能直接求和，
                    # 必须走官方计分（score=subtract7，见 step1._score_subtract7）。
                    "score": "subtract7", "standard": [93, 86, 79, 72, 65],
                    "by_year": {
                        "2011": {"codes": ["dc019", "dc020", "dc021", "dc022", "dc023"]},
                        "2013": {"codes": ["dc019", "dc020", "dc021", "dc022", "dc023"]},
                        "2015": {"codes": ["dc019", "dc020", "dc021", "dc022", "dc023"]},
                        "2018": {"codes": ["dc014_w4_1", "dc014_w4_2", "dc014_w4_3",
                                           "dc014_w4_4", "dc014_w4_5"]},
                        "2020": {"codes": ["dc007_1", "dc007_2", "dc007_3",
                                           "dc007_4", "dc007_5"]},
                    },
                    "labels": ["serial 7", "subtract 7", "minus 7", "100 minus 7"],
                    "valid": (0, 5),
                    "note": ("✅ 官方终判（2026-10-05）：CHARLS 2011 全国基线问卷原件逐字 + G2G 题库 API "
                             "2013/2015/2018/2020 逐波核对 → 连续减 7 = DC019–DC023（2011/2013/2015）、"
                             "DC014_W4_1–DC014_W4_5（2018 HCAP）、DC007_1–DC007_5（2020）。"
                             "官方计分：第 1 题须=93；第 2–5 题=标准答案 86/79/72/65 或恰好=本人上一题−7；"
                             "5 题答案须全读到才计 0–5，任一缺失→整段缺失。⚠️ DC014=「I felt fearful」"
                             "(CES-D 抑郁)、DC024=「是否使用纸笔」标记——二者**都不是**减 7 题（旧第三方指南记错）。"),
                },
                "drawing": {
                    # 视觉构建（重叠五边形）：1=Drew / 2=Failed → coding 映射为 1/0
                    "coding": {1: 1, 2: 0}, "valid": (1, 2),
                    "by_year": {
                        "2011": {"codes": ["dc025"]}, "2013": {"codes": ["dc025"]},
                        "2015": {"codes": ["dc025"]},
                        "2018": {"codes": ["dc024_w4"]},   # 2018 起画图题改用 DC024_W4
                    },
                    "labels": ["pentagon", "copy the drawing", "draw that picture"],
                    "note": ("✅ 官方终判（2026-10-05）：画重叠五边形 = DC025（2011/2013/2015）、"
                             "DC024_W4（2018）。⛔ 旧记的 dc014 实为 CES-D 抑郁条目「I felt fearful」。"
                             "1=Drew the picture / 2=Failed to draw → 本规格输出 1/0。"),
                },
            },
        },
    },
    # ------------------------------------------------------------------
    "HRS": {
        "dir": "HRS",
        # 暴露波 ∩ 认知随访波：C237 每三波一次（2006/2012/2018）；RAND 认知各波皆有 → 2012–2020
        "wave_years": [2006, 2012, 2014, 2016, 2018, 2020],
        "base_year": 2012,
        "base_wave": 11,                           # 2012 = Wave 11（HRS 波号）
        # 2014/2016/2020 无 C237 → 用 2012 基线暴露前移补齐（step1 _carry_baseline_exposure）
        "carry_baseline_exposure": True,
        "priority": "code",
        "id_aliases": ["hhidpn", "hhid", "pn", "id"],
        "doc_keywords": ["codebook", "questionnaire", "qnaire", "readme", "dictionary",
                         "guide", "mapping", "label", "harmonized", "code_book"],
        "exposure": {
            "codes": ["c237", "r8c237", "r11c237", "r14c237", "r11c237", "c237_lostpermteeth"],
            "labels": ["lostallyourupperandlower", "lostallofyourupperandlower", "lostpermteeth",
                       "lostallofyourupper"],
            "coding": {1: 1, 5: 0}, "valid": (1, 5),
            "note": "1=YES(无牙颌) / 5=NO / 8=DK / 9=RF。原始带波次前缀 r{wave}c237。",
        },
        "secondary": {},
        "oral_visit": {"codes": [], "labels": ["dentist", "dental"]},
        "cog": {
            "status": "verified",
            "source": ("RAND HRS Longitudinal File 文档（rand.org / hrsdata.isr.umich.edu）+ "
                       "HRS《Imputation of Cognitive Functioning Measures 1992–2020》：命名规则 R{w}{item}，"
                       "w 为 HRS 波号（2006=W8、2012=W11、2018=W14）。"),
            "episodic": {
                "immediate": {
                    "by_year": {"2006": {"codes": ["r8imrc"]}, "2012": {"codes": ["r11imrc"]},
                                "2018": {"codes": ["r14imrc"]}},
                    "core_fallback": HRS_CORE_COG["immediate"],   # 只有核心问卷时的后备原始名
                    "labels": ["immediate recall", "immediate word recall"], "valid": (0, 10),
                },
                "delayed": {
                    "by_year": {"2006": {"codes": ["r8dlrc"]}, "2012": {"codes": ["r11dlrc"]},
                                "2018": {"codes": ["r14dlrc"]}},
                    "core_fallback": HRS_CORE_COG["delayed"],
                    "labels": ["delayed recall", "delayed word recall"], "valid": (0, 10),
                },
            },
            "mental": {
                "mstot": {
                    "by_year": {"2006": {"codes": ["r8mstot"]}, "2012": {"codes": ["r11mstot"]},
                                "2018": {"codes": ["r14mstot"]}},
                    "labels": ["mental status"], "valid": (0, 15),
                    "note": "精神完整性总分（TICS）= 连续减7+倒背20+命名+日期定向，0–15。",
                },
                "serial7": {
                    "by_year": {"2006": {"codes": ["r8ser7"]}, "2012": {"codes": ["r11ser7"]},
                                "2018": {"codes": ["r14ser7"]}},
                    "score": "subtract7", "standard": [93, 86, 79, 72, 65],
                    "core_fallback": HRS_CORE_COG["serial7"],
                    "labels": ["serial 7"], "valid": (0, 5),
                    "note": ("RAND 的 r{w}ser7 已是 0–5 得分；核心问卷 ND142–ND146 为原始数字 → "
                             "core_fallback 走 subtract7 官方计分。"),
                },
            },
            "total": {
                "by_year": {"2006": {"codes": ["r8cog27", "r8cogtot", "r8tr20"]},
                            "2012": {"codes": ["r11cog27", "r11cogtot", "r11tr20"]},
                            "2018": {"codes": ["r14cog27", "r14cogtot", "r14tr20"]}},
                "labels": ["total cognition", "cognition score", "cog27"], "valid": (0, 35),
                "note": ("cog27 = 总分 0–27（词表回忆+连续减7+倒背20，W3 起）；"
                         "cogtot = 总分 0–35；tr20 = 词表回忆总分 0–20。"),
            },
            "prereq": ("首选 RAND HRS Longitudinal File（或 HRS 认知插补文件）；"
                       "**若只下到 HRS 核心问卷**，则由 core_fallback 映射（波次首字母前缀 + 题号，"
                       "如 W11 即时=`N106M`、延迟=`N148M`、减7=`N142`–`N146`）取数。"),
        },
    },
    # ------------------------------------------------------------------
    "ELSA": {
        "dir": "ELSA",
        "wave_years": [2006, 2008, 2010, 2012, 2014, 2016],   # W3..W8（2006=W3）
        "base_year": 2006,
        "base_wave": 3,                            # 2006 = ELSA Wave 3
        # HEDENT 只在 W3(2006)/W5(2010) → 其余波用 2006 基线暴露前移补齐
        "carry_baseline_exposure": True,
        "priority": "code",
        "id_aliases": ["idauniq", "idauniq_", "id", "hhidpn"],
        "doc_keywords": ["codebook", "questionnaire", "qnaire", "readme", "dictionary",
                         "guide", "mapping", "label", "harmonized", "code_book", "userguide"],
        "exposure": {
            "codes": ["hedent"],
            "labels": ["inrelationtodentalhealth", "whichofthefollowingappliestoyou"],
            "coding": {1: 1, 2: 0, 3: 0, 4: 1}, "valid": (1, 4),
            "note": "四分类：1 无天然牙+义齿 / 2 天然牙+义齿 / 3 仅天然牙 / 4 两者皆无 → edentate={1,4}。W3/W5。",
        },
        "secondary": {
            "tooth_count_cat": {"codes": ["hedntd"], "labels": ["howmanynaturalteeth"],
                                "valid": (1, 4), "note": "W7；1=None/2=1-9/3=10-19/4=≥20 → <20 牙=功能牙列不足"},
            "self_rated_oral": {"codes": ["hednta"], "labels": ["dentalhealth", "oralhealth"], "valid": (1, 5)},
            "OIDP":            {"codes": ["hedntb"], "labels": ["oralimpact", "oidp"], "valid": (0, 5)},
            "denture_upper":   {"codes": ["hedntf"], "labels": ["upperdenture"], "valid": (1, 2)},
            "denture_lower":   {"codes": ["hedntg"], "labels": ["lowerdenture"], "valid": (1, 2)},
        },
        "oral_visit": {"codes": [], "labels": ["dentist", "dental"]},
        "cog": {
            "status": "verified",
            "source": ("CANDID《Cognitive Data Guide》（TILDA/CLOSER 跨队列变量对照，含 ELSA 逐变量来源）+ "
                       "UKDS《ELSA Wave 5 Derived Variables》用户指南（cflisen/cflisd/cfrecal/cfanig 派生代码）。"),
            "episodic": {
                "immediate": {"codes": ["cflisen", "cflisn", "cflis"],
                              "labels": ["immediate word list recall", "immediate recall", "words recalled"],
                              "valid": (0, 10),
                              "note": "CFLISEN = 即时词表回忆正确数（0–10）。"},
                "delayed":   {"codes": ["cflisd"],
                              "labels": ["delayed word list recall", "words recalled after delay", "delayed recall"],
                              "valid": (0, 10),
                              "note": "CFLISD = 延迟回忆正确数（0–10）；官方标签『Number of words recalled after delay』。"},
            },
            "mental": {
                "fluency":     {"codes": ["cfani"], "labels": ["animal", "fluency"], "valid": (0, 63),
                                "note": "CFANI = 1 分钟内说出动物数；CFANIG 为派生分级。"},
                "orientation": {"codes": ["cfdatd", "cfdatm", "cfdaty", "cfday"], "sum_codes": True, "valid": (0, 4),
                                "note": "日期定向 4 项：日 CFDATD / 月 CFDATM / 年 CFDATY / 星期 CFDAY。"},
                "numeracy":    {"codes": ["cfmscr", "cfsuma"], "valid": (0, 6),
                                "note": "CFMSCR 合并 CFSUMA–CFSUMF。"},
                "prospective": {"codes": ["cfmersp", "cfmem"], "valid": (0, 5)},
            },
            "total": {"codes": ["cfind"], "labels": ["total cognitive"],
                      "note": "CFIND = 记忆指数 + 执行指数；部分发布版未含（文档标注 not included in this release）。"},
        },
    },
    # ------------------------------------------------------------------
    "SHARE": {
        "dir": "SHARE",
        # 牙齿变量仅 W5(2013)；认知随访 W6(2015)/W7(2017)/W8(2019-20) → 载入 4 波
        "wave_years": [2013, 2015, 2017, 2019],
        "base_year": 2013,
        "base_wave": 5,                            # 2013 = SHARE Wave 5
        # 暴露只在 2013 → W6–W8 用 2013 基线暴露前移补齐（这正是「2013 暴露 → 最长 8 年认知轨迹」的关键）
        "carry_baseline_exposure": True,
        "priority": "code",
        "id_aliases": ["mergeid", "id"],
        "doc_keywords": ["codebook", "questionnaire", "qnaire", "readme", "dictionary",
                         "guide", "mapping", "label", "harmonized", "release", "code_book"],
        "exposure": {
            "codes": ["ph092_missingnatteeth", "ph092"],
            "labels": ["missingnaturalteeth", "numberofmissing"],
            "derive": "remaining_from_missing", "base_teeth": 28, "valid": (1, 30),
            "note": "PH092=缺失天然牙数(1-30) → remaining=max(0,28-PH092)；remaining==0 → 无牙颌。须在方法学明写 28 颗假设。",
        },
        "secondary": {
            "all_natural": {"codes": ["ph091_allnaturteeth", "ph091"], "labels": ["allnaturalteeth"], "valid": (1, 2)},
            "artificial":  {"codes": ["ph094_artificialteeth", "ph094"], "labels": ["artificialteeth", "denture"], "valid": (1, 3)},
        },
        "oral_visit": {"codes": ["hc010_snadentist", "hc010"], "labels": ["dentist"]},
        "cog": {
            "status": "verified",
            "source": ("SHARE《Scales and Multi-Item Indicators》rel. 9.0.0（10 词回忆与言语流畅的生成变量说明）+ "
                       "SHARE Data Archive（sharew{N}_gv_health / _cf 模块变量清单）。"),
            "episodic": {
                "immediate": {"codes": ["cf008tot", "cf008"],
                              "labels": ["immediate word recall", "first trial"], "valid": (0, 10),
                              "note": "cf008tot = 即时（第一试次）10 词回忆正确数，生成于 gv_health 模块。"},
                "delayed":   {"codes": ["cf016tot", "cf016"],
                              "labels": ["delayed word recall", "after a delay"], "valid": (0, 10),
                              "note": "cf016tot = 延迟 10 词回忆正确数。"},
            },
            "mental": {
                "fluency":  {"codes": ["cf010_", "cf010"], "labels": ["verbal fluency", "animal"],
                             "valid": (0, 100), "note": "cf010_ = 60 秒内动物命名数。"},
                "numeracy": {"codes": ["numeracy2", "numeracy"], "valid": (0, 9),
                             "note": "numeracy（W1/2/4/5）；numeracy2（W4 起，减法）。"},
                "self_mem": {"codes": ["cf103"], "valid": (1, 5), "note": "自评记忆（RwSLFMEM）。"},
            },
            "note": ("W5(2013) 单波口腔暴露 + W6–W9 认知随访 → 可做『2013 暴露 → 最长 8 年认知轨迹』。"
                     "⚠️ SHARE 词表回忆无时间上限（其他队列限 2 分钟）→ 跨队列比较的限制。"),
        },
    },
}

# ==========================================================================
# 校准队列 NHANES（不进主模型）：客观测量校准 + 机制验证
# --------------------------------------------------------------------------
# 角色：唯一有**客观口腔检查**（牙列 + 牙周）的队列 →
#   ① 校准其余 5 队列的**自报**口腔暴露（敏感度/特异度/错分方向与幅度）；
#   ② 在客观金标准下检验『牙周炎 → 认知』机制链是否成立。
# 周期重叠（决定性约束）：认知模块只做 2011–2012、2013–2014 两周期 → 口腔 × 认知只有这两个周期。
#   牙列检查：1 岁+；牙周检查：30 岁+ 且有天然牙、无抗生素预防禁忌；
#   认知模块：**60 岁+**，且需读写英语/西语/韩语/越南语/中文，proxy 不做
#   → 每周期可用约 1.6–1.7 千人（2013–14 CFASTAT 分布：1510 人做了至少 1 项）。
# 变量名来源（2026-10-02 逐字核实）：CDC 官方码本页 CFQ_G / CFQ_H、OHXDEN_G / OHXDEN_H、OHXPER_G。
#   ✅ 已确认 CFQ_G(2011–12) 与 CFQ_H(2013–14) 变量名**完全一致**；OHXDEN_G 与 OHXDEN_H 亦一致。
#   ✅ OHXPER 变量名 = OHX{牙位 2 位}{测量 2 位}{位点 1 位}，测量 ∈ {PC 袋深, CJ FGM–CEJ, LA 附着丧失}，
#      位点 ∈ {S 近中颊, M 中央颊, D 远中颊, A 近中舌, L 中央舌, P 远中舌}（示例：OHX02PCS）。
# ==========================================================================

NHANES_CYCLES = {2011: "G", 2013: "H"}      # 周期起始年 -> 官方文件后缀
NHANES_COG_AGE_MIN = 60                     # 认知模块年龄门槛
NHANES_ORAL_AGE_MIN = 30                    # 牙周检查年龄门槛（牙列检查为 1 岁+）

# ⚠️ 旧版手写 NHANES_SPEC 已删除 —— 改为下方**由一手核实常量派生**的版本，避免双份定义互相覆盖。
#    （旧版两处已证有误：① perio.pd_pattern 写成 ^ohx(\d{2})p([dmspla])$，而真实变量是 2 位测量码
#      OHXnnPC{site}，该正则**一个都匹配不到**；② covariates.married 写成 dmdmartz，实为 DMDMARTL。）

# ==========================================================================
# NHANES —— 客观测量校准队列（CALIBRATION_COHORT；**不进主模型**）
# --------------------------------------------------------------------------
# 定位（2026-10-02 定案）：
#   NHANES 与 HRS 家族**无协调化变量**，且是**横断面**设计（无个体认知随访）
#   → 不做纵向认知轨迹建模。它只承担三件事：
#     ① 口腔暴露的**客观测量校准**：临床检查的真实牙数/无牙颌，用于校准各队列
#        的自报牙数（SHARE/KLoSA 的"缺了几颗"敏感度 21%–91%）；
#     ② 认知量表的**分布校准**：CERAD 三试次 + 延迟回忆 + 动物流畅 + DSST，
#        用于判断"各队列 z 分是否可比、天花板/地板效应有多大"；
#     ③ 客观牙周炎测量（CHARLS/HRS/ELSA/SHARE/KLoSA **全部缺失**的变量）。
#
# ⚠️ 与其余队列的三处结构差异（决定了它必须用**专用适配器** adapt_nhanes()）：
#   1) 文件是 SAS XPORT（*.XPT），不是 .dta/.sav；键是 SEQN，不是 hhidpn/idauniq/mergeid。
#   2) 分"周期"（2011-12 = _G；2013-14 = _H）而不是"波次"；两周期是**独立横断面**，
#      **不是**同一批人的两次随访 → time_c 恒为 0。
#   3) 需要复杂抽样权重（WTMEC2YR / SDMVSTRA / SDMVPSU）才能做全国代表性估计。
#
# 文件命名（CDC 2024 后迁移到 /Nchs/Data/Nhanes/Public/<起始年>/DataFiles/）：
#   DEMO_<cycle>.XPT  OHXDEN_<cycle>.XPT  OHXPER_<cycle>.XPT  CFQ_<cycle>.XPT  OHQ_<cycle>.XPT
#   例：https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2011/DataFiles/OHXDEN_G.XPT
# ==========================================================================
NHANES_CYCLE_SUFFIX = {"G": 2011, "H": 2013}   # 后缀 -> 起始年（与上方 NHANES_CYCLES 互逆；勿再定义 NHANES_CYCLES）
NHANES_MODULES = {                     # 模块键 -> 文件名前缀（stem 前缀匹配，大小写不敏感）
    "demo":  "DEMO",
    "den":   "OHXDEN",
    "per":   "OHXPER",
    "cfq":   "CFQ",
    "ohq":   "OHQ",
}
NHANES_ID = "SEQN"
NHANES_WEIGHT_VAR = "WTMEC2YR"         # MEC 检查权重（口腔检查/牙周/认知均用此权重）
NHANES_STRATA_VAR = "SDMVSTRA"
NHANES_PSU_VAR    = "SDMVPSU"

# --- 口腔：牙齿计数（OHXDEN，≥1 岁）-------------------------------------------------
# OHX01TC … OHX32TC，逐牙一位；官方取值编码（CDC 2011-2012/2013-2014 码本逐字确认）：
#   1 = 乳牙（deciduous）存在    2 = 恒牙存在    3 = 种植体
#   4 = 该牙缺失                 5 = 恒牙牙根残片存在   9 = 无法评估
# ⚠️ 官方**没有**现成的"牙数汇总变量"，也没有 OHXEDENT → 必须自己按编码汇总。
NHANES_TOOTH_PATTERN   = r"^OHX(\d{2})TC$"
NHANES_TOOTH_PRESENT   = [1, 2, 3, 5]   # 口内有牙体/种植体/残根 → "有牙"
NHANES_TOOTH_NATURAL   = [1, 2]         # 仅天然牙（乳牙 + 恒牙）→ 无牙颌判定依据
NHANES_TOOTH_IMPLANT   = 3
NHANES_TOOTH_CANTASSESS= 9
NHANES_THIRD_MOLARS    = [1, 16, 17, 32]  # 4×2 第三磨牙牙位号（FDI 之外的 NHANES 序号）
NHANES_MIN_ASSESSED    = 28             # 至少 28/32 牙位有明确评估，牙数/无牙颌才作数
NHANES_DEN_SUMMARY = {"exam_status": "OHDEXSTS", "dentition_status": "OHDDESTS",
                      "implant_q": "OHXIMP"}
# OHDEXSTS / OHDDESTS：1=Complete, 2=Partial, 3=Not Done（两者编码相同，非"牙列类型"）

# --- 牙周：OHXPER（≥30 岁）---------------------------------------------------------
# 命名：OHX{牙位号 2 位}{测量类型}{位点字母}
#   测量类型：PC = FGM→龈沟底（探诊深度, 0–8mm）
#             CJ = FGM→CEJ（牙龈退缩, −10…+1mm）
#             LA = 计算附着丧失（0–12mm）
#   位点字母：S=近中颊(MF) M=中央颊(MdF) D=远中颊(DF) A=近中舌(ML) L=中央舌(MdL) P=远中舌(DL)
#   99 = Cannot be assessed（该位点无法评估）；. = 数据缺失
#   ⚠️ CDC/AAP 病例定义只用**邻面位点** = {S, D, A, P}
NHANES_PERIO_PATTERN   = r"^OHX(\d{2})(PC|CJ|LA)([SMDALP])$"
NHANES_PERIO_INTERPROX = ["S", "D", "A", "P"]      # 邻面（近中/远中）
NHANES_PERIO_SITE_ALL  = {"S": "mesiofacial", "M": "midfacial", "D": "distofacial",
                          "A": "mesiolingual", "L": "midlingual", "P": "distolingual"}
NHANES_PERIO_CANTASSESS= 99
NHANES_PERIO_MIN_SITES = 6                          # 至少 6 个位点可评估才判病例
NHANES_PERIO_SUMMARY = {"perio_status": "OHDPDSTS", "medical_exclusion": "OHDEXCLU"}
# CDC/AAP（2012）病例定义：
#   中度 = ≥2 个**不同牙**的邻面位点 AL≥4mm  或  ≥2 个不同牙的邻面位点 PD≥5mm
#   重度 = ≥2 个不同牙的邻面位点 AL≥6mm  且  ≥1 个邻面位点 PD≥5mm
NHANES_PERIO_MOD_AL, NHANES_PERIO_MOD_PD = 4, 5
NHANES_PERIO_SEV_AL, NHANES_PERIO_SEV_PD = 6, 5

# --- 认知：CFQ（≥60 岁；2011-2012 与 2013-2014 命名完全一致，已逐字确认）----------------
#   CFDCST1/2/3 = CERAD 三试次即时回忆（0–10 各）→ 合计 0–30
#   CFDCSR      = CERAD 延迟回忆（0–10）
#   CFDAST      = 动物流畅（60 秒，0–~100）
#   CFDDS       = DSST 数字符号替换（0–133）
#   CFASTAT     = 认知功能完成状态；CFALANG = 施测语言
#   CFDCIT1/2/3 / CFDCIR = 闯入词（intrusions）；CFDCCS/CFDRNC/CFDAPP/CFDDPP/CFDARNC/CFDDRNC = 其他派生
#   ⚠️ 跨队列对齐的关键：HRS 家族"即时词表回忆"是**单试次 0–10** → 与 NHANES 的
#      CFDCST1（第一试次 0–10）同口径；**不要**用三试次合计 0–30 去和 HRS 比。
NHANES_COG = {
    "status": "verified",
    "source": ("NHANES 2011-2012（CFQ_G）与 2013-2014（CFQ_H）官方数据文件 + 码本，"
               "CDC/NCHS，变量名与标签逐字确认（2026-10-02）。"),
    "age_eligibility": "60+",
    "immediate_trial1": {"codes": ["CFDCST1"], "valid": (0, 10)},
    "immediate_total":  {"codes": ["CFDCST1", "CFDCST2", "CFDCST3"], "sum": True, "valid": (0, 30)},
    "delayed":          {"codes": ["CFDCSR"], "valid": (0, 10)},
    "fluency":          {"codes": ["CFDAST"], "valid": (0, 100)},
    "dsst":             {"codes": ["CFDDS"], "valid": (0, 133)},
    "status_var": "CFASTAT", "language_var": "CFALANG",
    # 主校准口径 = 第一试次即时(0–10) + 延迟(0–10) → 与 HRS/ELSA/SHARE/CHARLS/KLoSA 的
    # "即时+延迟"情景记忆复合分同构
    "primary": ["immediate_trial1", "delayed"],
}

# --- 协变量映射（NHANES DEMO）-----------------------------------------------------
NHANES_DEMO_MAP = {
    "age": "RIDAGEYR", "sex": "RIAGENDR", "edu_cat": "DMDEDUC2", "marital": "DMDMARTL",
    "race_eth": "RIDRETH1", "race_eth3": "RIDRETH3",
}
# DMDEDUC2（20 岁以上成人教育程度）→ 近似受教育年数
NHANES_EDU_YEARS = {1: 6, 2: 10, 3: 12, 4: 14, 5: 16}
NHANES_MARRIED_CODES = [1, 6]          # 1=Married, 6=Living with partner → married=1
# ⚠️ NHANES 无 rural/urban 变量（地理限制访问）→ rural 恒 NaN；
#    吸烟需另下 SMQ_<cycle>.XPT（SMQ020 = 一生是否抽 ≥100 支）→ 未下时为 NaN。
# --- 机器可读汇总（step1 adapt_nhanes() 消费；由上方常量派生，单一事实来源）-------------
NHANES_SPEC = {
    "dir": "NHANES",
    "id_aliases": [NHANES_ID],
    "cycles": NHANES_CYCLES,
    "modules": NHANES_MODULES,
    "cog": {
        "status": NHANES_COG["status"],
        "source": NHANES_COG["source"],
        "age_min": NHANES_COG_AGE_MIN,
        "episodic": {
            # 主口径：CERAD **第一试次**（0–10）+ 延迟（0–10）
            # → 与 HRS 家族"单试次即时 0–10 + 延迟 0–10"同构，跨队列校准才有意义
            "immediate": {"codes": NHANES_COG["immediate_trial1"]["codes"],
                          "valid": NHANES_COG["immediate_trial1"]["valid"]},
            "delayed":   {"codes": NHANES_COG["delayed"]["codes"],
                          "valid": NHANES_COG["delayed"]["valid"]},
        },
        "mental": {
            "immediate_total": {"codes": NHANES_COG["immediate_total"]["codes"], "sum_codes": True,
                                "valid": NHANES_COG["immediate_total"]["valid"]},
            "fluency": {"codes": NHANES_COG["fluency"]["codes"],
                        "valid": NHANES_COG["fluency"]["valid"]},
            "dsst":    {"codes": NHANES_COG["dsst"]["codes"],
                        "valid": NHANES_COG["dsst"]["valid"]},
        },
        "status_var": NHANES_COG["status_var"], "language_var": NHANES_COG["language_var"],
    },
    "dentition": {
        "tooth_pattern": NHANES_TOOTH_PATTERN,
        "present_natural": NHANES_TOOTH_NATURAL,      # {1,2} 天然牙 → 无牙颌判定
        "present_any": NHANES_TOOTH_PRESENT,          # {1,2,3,5} 口内有牙体/种植体/残根
        "implant_code": NHANES_TOOTH_IMPLANT,
        "cannot_assess": NHANES_TOOTH_CANTASSESS,
        "third_molars": NHANES_THIRD_MOLARS,
        "min_assessed": NHANES_MIN_ASSESSED,          # 32 牙位中至少 28 个有明确评估
        "min_assessed_28": 24,                        # 去掉 4 颗第三磨牙后，28 位中至少 24 个
        "summary": NHANES_DEN_SUMMARY,
    },
    "perio": {
        "pd_pattern":         r"^OHX\d{2}PC[SMDALP]$",   # 探诊深度（FGM→龈沟底）
        "la_pattern":         r"^OHX\d{2}LA[SMDALP]$",   # 计算附着丧失
        "recession_pattern":  r"^OHX\d{2}CJ[SMDALP]$",   # FGM→CEJ（牙龈退缩）
        "interproximal": NHANES_PERIO_INTERPROX,         # 邻面位点 S/D/A/P
        "cannot_assess": NHANES_PERIO_CANTASSESS,
        "min_sites": NHANES_PERIO_MIN_SITES,
        "mod_al": NHANES_PERIO_MOD_AL, "mod_pd": NHANES_PERIO_MOD_PD,
        "sev_al": NHANES_PERIO_SEV_AL, "sev_pd": NHANES_PERIO_SEV_PD,
        "summary": NHANES_PERIO_SUMMARY,
    },
    "covariates": {
        "age":     ["RIDAGEYR"],
        "female":  ["RIAGENDR"],                       # 1=男 / 2=女
        "edu":     ["DMDEDUC2"],                       # 1–5 分级（非受教育年数）
        "married": ["DMDMARTL"],                       # 1=已婚 / 6=同居
        "smoke":   ["SMQ020"],                         # 1=一生抽过≥100 支 / 2=否
        "race":    ["RIDRETH1", "RIDRETH3"],
        "weight":  [NHANES_WEIGHT_VAR],
        "strata":  [NHANES_STRATA_VAR],
        "psu":     [NHANES_PSU_VAR],
    },
    "edu_years_map": NHANES_EDU_YEARS,
    "married_codes": NHANES_MARRIED_CODES,
}


# ---------- 认知结局协调化 ----------
# 各队列认知量表不同 -> 一律在【队列 × 波次】内部标准化为 z 分（mean 0, sd 1）
# ⚠️ 主结局口径（2026-10-02 定案）：**情景记忆 = 即时 + 延迟词表回忆**（五队列全部可得）。
#    各队列题量不同（CHARLS/HRS/ELSA/SHARE=10 词；KLoSA=3 词；NHANES 即时为 3 试次合计 0–30）
#    → 只能靠队列×波次内 z 分对齐，**不可比较原始分**（须在局限性中明写）。
#    NHANES 作为校准队列时用"第一试次 0–10 + 延迟 0–10"（= NHANES_COG['primary']）与上述同构。
COG_WAVES = {
    "CHARLS": ["2011", "2013", "2015", "2018", "2020"],   # 认知 5 波；口腔暴露 2011–2018
    "HRS":    ["2006", "2008", "2010", "2012", "2014", "2016", "2018", "2020"],
    "ELSA":   ["2006", "2008", "2010", "2012", "2014", "2016", "2018"],
    "SHARE":  ["2013", "2015", "2017", "2019"],
    "KLoSA":  ["2006", "2008", "2010", "2012", "2014", "2016", "2018", "2020", "2022"],
    "NHANES": ["2011", "2013"],
}

# 认知分量列名（step1 输出 -> step2/3 可选使用）
COG_COMPONENT_COLS = ["cog_immediate", "cog_delayed", "cog_mental", "cog_total"]

# ---------- 模型设定 ----------
# ⚠️ 主口径用 **edent_base（基线时不变暴露）** 而非时变的 `edent`：
#    口腔状况会随随访变化，用当期测量做暴露会引入「暴露-结局同时性 / 反向因果」
#    （认知下降者可能减少牙科就诊、报告更多牙齿脱落）。基线暴露是流行病学标准做法。
#    时变暴露 `edent` 作为敏感性分析（见 step5 的 M2）。
FORMULA = "cog_z ~ edent_base * time_c + age_c + female + edu_years + married + rural + ever_smoke"
FORMULA_TV = "cog_z ~ edent * time_c + age_c + female + edu_years + married + rural + ever_smoke"
RANDOM_EFFECT = "~time_c"           # 随机截距 + 随机斜率（失败自动降为随机截距）
PRIMARY_TERM = "edent_base:time_c"  # 主效应：无牙颌者认知下降速度的额外变化

# ---------- 输出 ----------
SEED = 20261002
