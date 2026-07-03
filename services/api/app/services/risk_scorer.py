"""多因子语义风险评分模块。

综合分析用户症状描述和 AI 回复，使用加权评分系统识别健康风险。
不依赖 LLM 调用，通过症状组合、紧迫语言、危险信号等多维度打分。
"""

import logging
import re

logger = logging.getLogger(__name__)

# ─── 症状严重度评分（单项 0-3 分）─────────────────────────────────────────────

# 3 分：立即致命的症状
CRITICAL_SYMPTOMS = [
    (r"自杀|轻生|不想活|想死|结束生命", "自杀倾向"),
    (r"意识不清|昏迷|失去知觉|晕厥", "意识障碍"),
    (r"大出血|大量出血|止不住血|吐血|便血|咯血", "大出血"),
    (r"心脏骤停|心跳停止|没有呼吸", "心脏骤停"),
    (r"休克|虚脱", "休克"),
]

# 2 分：高度危险的症状
HIGH_RISK_SYMPTOMS = [
    (r"胸痛|胸疼|胸口痛|胸口疼|心脏痛|心前区痛|心绞痛", "胸痛"),
    (r"胸闷|胸口闷|憋气|透不过气|喘不上来气", "胸闷"),
    (r"呼吸困难|无法呼吸|喘不过气|窒息感|呼吸急促", "呼吸困难"),
    (r"剧烈头痛|突发剧烈头痛|雷击样头痛|炸裂般头痛", "剧烈头痛"),
    (r"急性腹痛|剧烈腹痛|腹部剧痛", "急性腹痛"),
    (r"骨折|严重外伤|开放性伤口", "严重外伤"),
    (r"高烧不退|高烧[34]\d|体温[34]\d|烧到[34]\d", "高热"),
    (r"心悸|心脏不舒服|心跳很快|心慌", "心悸"),
]

# 1 分：中等风险的症状
MEDIUM_RISK_SYMPTOMS = [
    (r"头晕|眩晕|天旋地转|头重脚轻", "头晕"),
    (r"恶心|呕吐|反胃", "消化道症状"),
    (r"高烧|发烧|发热|低烧", "发热"),
    (r"剧烈疼痛|剧痛|疼痛难忍|疼得厉害", "剧烈疼痛"),
    (r"出血|流血", "出血"),
    (r"肿胀|水肿", "肿胀"),
    (r"麻木|失去感觉", "麻木"),
    (r"视力模糊|看不清|眼前发黑", "视觉障碍"),
    (r"耳鸣|听力下降", "听觉异常"),
]

# ─── 紧迫语言检测（额外加分）─────────────────────────────────────────────────

URGENCY_PATTERNS = [
    (r"要死了|快死了|不行了|撑不住了|要命|活不了", 3, "濒死表达"),
    (r"受不了了|太难受了|疼死了|痛死了|难受死了", 2, "极度痛苦表达"),
    (r"很严重|非常严重|特别严重|越来越严重|加重|恶化", 2, "严重程度强调"),
    (r"突然|突发|一下子|猛地|忽然", 1, "突发性描述"),
    (r"很担心|害怕|恐惧|吓死了", 1, "恐惧情绪"),
    (r"120|急救|急诊|救护车", 2, "主动求助急救"),
]

# ─── 危险组合检测（额外加分）─────────────────────────────────────────────────

DANGEROUS_COMBOS = [
    {
        "name": "疑似急性心梗",
        "requires": [r"胸[痛闷]", r"放射|左肩|左臂|后背|下巴"],
        "bonus": 3,
        "description": "胸痛/胸闷 + 放射痛 = 疑似心梗",
    },
    {
        "name": "疑似脑卒中",
        "requires": [r"头痛|头晕", r"麻木|无力|口齿不清|说不清话"],
        "bonus": 3,
        "description": "头痛/头晕 + 神经症状 = 疑似脑卒中",
    },
    {
        "name": "心肺联合危险",
        "requires": [r"胸[痛闷]|心脏", r"呼吸困难|喘不过气|憋气"],
        "bonus": 2,
        "description": "心脏症状 + 呼吸困难",
    },
    {
        "name": "出血+休克",
        "requires": [r"出血|流血", r"头晕|意识模糊|面色苍白|冷汗"],
        "bonus": 2,
        "description": "出血 + 休克征兆",
    },
    {
        "name": "高热+意识障碍",
        "requires": [r"高烧|发烧|体温\d", r"意识不清|昏迷|说胡话|神志不清"],
        "bonus": 2,
        "description": "高热 + 意识障碍",
    },
]

# ─── AI 回复风险信号检测 ──────────────────────────────────────────────────────

AI_RISK_SIGNALS = [
    (r"拨打\s*120|立即就医|马上去急诊|紧急就医|尽快就医", 2, "AI建议紧急就医"),
    (r"高风险|高危|危险信号|严重", 1, "AI识别高风险"),
    (r"停止.*问诊|暂停.*问诊|人工接管", 2, "AI触发接管"),
]


def _extract_text(content) -> str:
    """从消息内容中提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(parts)
    return str(content) if content else ""


def score_risk(messages: list[dict]) -> dict:
    """对对话消息进行多因子风险评分。

    Args:
        messages: 完整对话消息列表 [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        {"score": 0-10, "level": "...", "reason": "...", "evidence": [...], "details": {...}}
    """
    # 分离用户消息和 AI 消息
    user_texts = []
    ai_texts = []
    for m in messages:
        text = _extract_text(m.get("content", ""))
        if not text:
            continue
        if m.get("role") == "user":
            user_texts.append(text)
        else:
            ai_texts.append(text)

    # 合并文本用于分析
    all_user_text = "\n".join(user_texts)
    all_ai_text = "\n".join(ai_texts)
    combined_text = all_user_text + "\n" + all_ai_text

    total_score = 0
    evidence = []
    details = {"symptom_scores": [], "urgency_bonus": 0, "combo_bonus": 0, "ai_signal_bonus": 0}

    # ── 1. 症状严重度评分 ──
    for pattern, name in CRITICAL_SYMPTOMS:
        if re.search(pattern, all_user_text):
            total_score += 3
            evidence.append(f"[危急] {name}")
            details["symptom_scores"].append({"name": name, "score": 3, "level": "critical"})

    for pattern, name in HIGH_RISK_SYMPTOMS:
        if re.search(pattern, all_user_text):
            total_score += 2
            evidence.append(f"[高危] {name}")
            details["symptom_scores"].append({"name": name, "score": 2, "level": "high"})

    for pattern, name in MEDIUM_RISK_SYMPTOMS:
        if re.search(pattern, all_user_text):
            total_score += 1
            evidence.append(f"[中危] {name}")
            details["symptom_scores"].append({"name": name, "score": 1, "level": "medium"})

    # ── 2. 紧迫语言加分 ──
    urgency_total = 0
    for pattern, bonus, name in URGENCY_PATTERNS:
        if re.search(pattern, all_user_text):
            urgency_total += bonus
            evidence.append(f"[紧迫] {name}")
    urgency_total = min(urgency_total, 5)  # 上限 5 分
    total_score += urgency_total
    details["urgency_bonus"] = urgency_total

    # ── 3. 危险组合加分 ──
    combo_total = 0
    for combo in DANGEROUS_COMBOS:
        matches = sum(1 for p in combo["requires"] if re.search(p, all_user_text))
        if matches == len(combo["requires"]):
            combo_total += combo["bonus"]
            evidence.append(f"[组合] {combo['name']}：{combo['description']}")
    combo_total = min(combo_total, 5)  # 上限 5 分
    total_score += combo_total
    details["combo_bonus"] = combo_total

    # ── 4. AI 回复风险信号加分 ──
    ai_total = 0
    for pattern, bonus, name in AI_RISK_SIGNALS:
        if re.search(pattern, all_ai_text):
            ai_total += bonus
            evidence.append(f"[AI] {name}")
    ai_total = min(ai_total, 3)  # 上限 3 分
    total_score += ai_total
    details["ai_signal_bonus"] = ai_total

    # ── 5. 计算最终分数（归一化到 0-10）──
    # 原始分理论上最高约 3*1 + 2*8 + 1*9 + 5 + 5 + 3 = 43
    # 映射到 0-10：score * 10 / 43，但使用更直观的分段
    raw_score = total_score

    if raw_score >= 15:
        final_score = 10
    elif raw_score >= 12:
        final_score = 9
    elif raw_score >= 9:
        final_score = 8
    elif raw_score >= 7:
        final_score = 7
    elif raw_score >= 5:
        final_score = 6
    elif raw_score >= 3:
        final_score = 4
    elif raw_score >= 2:
        final_score = 3
    elif raw_score >= 1:
        final_score = 2
    else:
        final_score = 0

    # 确定等级
    if final_score >= 9:
        level = "critical"
    elif final_score >= 7:
        level = "high"
    elif final_score >= 4:
        level = "elevated"
    else:
        level = "normal"

    # 生成原因摘要
    if evidence:
        reason = f"检测到 {len(evidence)} 项风险信号（原始分 {raw_score}）"
    else:
        reason = "未检测到显著风险信号"

    return {
        "score": final_score,
        "level": level,
        "reason": reason,
        "evidence": evidence,
        "details": details,
    }
