"""
药物相互作用查询服务

数据来源：openFDA label API (api.fda.gov/drug/label.json)
真实逻辑：
  1. 查询药 A 的 FDA 官方标签（drug_interactions 字段）
  2. 在标签文本中搜索药 B 的名称
  3. 提取包含药 B 的上下文段落作为证据
  4. 同时反向查询：查药 B 的标签，看是否提到药 A
  只有 FDA 标签文本里真实出现对方药名才判定为有相互作用

不构造假数据，有多少说多少。
"""

import re
import httpx
import json as json_lib

# ── 中文药名 → 英文通用名（INN）映射 ──────────────────────────────────────────
ZH_TO_EN: dict[str, str] = {
    # 解热镇痛
    "阿司匹林": "aspirin",
    "布洛芬": "ibuprofen",
    "对乙酰氨基酚": "acetaminophen",
    "扑热息痛": "acetaminophen",
    "萘普生": "naproxen",
    "双氯芬酸": "diclofenac",
    "吲哚美辛": "indomethacin",
    "塞来昔布": "celecoxib",
    # 心血管
    "氨氯地平": "amlodipine",
    "美托洛尔": "metoprolol",
    "阿托伐他汀": "atorvastatin",
    "瑞舒伐他汀": "rosuvastatin",
    "辛伐他汀": "simvastatin",
    "硝苯地平": "nifedipine",
    "地高辛": "digoxin",
    "华法林": "warfarin",
    "氯吡格雷": "clopidogrel",
    "依那普利": "enalapril",
    "卡托普利": "captopril",
    "氢氯噻嗪": "hydrochlorothiazide",
    "螺内酯": "spironolactone",
    "呋塞米": "furosemide",
    # 抗感染
    "阿莫西林": "amoxicillin",
    "头孢克洛": "cefaclor",
    "头孢呋辛": "cefuroxime",
    "左氧氟沙星": "levofloxacin",
    "克拉霉素": "clarithromycin",
    "阿奇霉素": "azithromycin",
    "甲硝唑": "metronidazole",
    "氟康唑": "fluconazole",
    "利福平": "rifampin",
    "异烟肼": "isoniazid",
    # 内分泌
    "二甲双胍": "metformin",
    "格列苯脲": "glibenclamide",
    "格列美脲": "glimepiride",
    "胰岛素": "insulin",
    "左甲状腺素": "levothyroxine",
    # 消化
    "奥美拉唑": "omeprazole",
    "兰索拉唑": "lansoprazole",
    "雷贝拉唑": "rabeprazole",
    "西咪替丁": "cimetidine",
    "多潘立酮": "domperidone",
    "莫沙必利": "mosapride",
    # 神经精神
    "地西泮": "diazepam",
    "艾司唑仑": "estazolam",
    "氟西汀": "fluoxetine",
    "帕罗西汀": "paroxetine",
    "舍曲林": "sertraline",
    "卡马西平": "carbamazepine",
    "丙戊酸": "valproic acid",
    "苯妥英": "phenytoin",
    "氯硝西泮": "clonazepam",
    # 呼吸
    "沙丁胺醇": "albuterol",
    "茶碱": "theophylline",
    "氨茶碱": "aminophylline",
    "孟鲁司特": "montelukast",
    # 其他
    "地塞米松": "dexamethasone",
    "泼尼松": "prednisone",
    "甲泼尼龙": "methylprednisolone",
    "秋水仙碱": "colchicine",
    "别嘌醇": "allopurinol",
    "非布司他": "febuxostat",
}

OPENFDA_BASE = "https://api.fda.gov/drug"
DAILYMED_BASE = "https://dailymed.nlm.nih.gov/dailymed"
_TIMEOUT = 10.0


def _to_english(name: str) -> str:
    """中文 → 英文；若未命中则原样返回（可能已是英文）。"""
    return ZH_TO_EN.get(name.strip(), name.strip())


async def _fetch_drug_label(client: httpx.AsyncClient, drug_name: str) -> str | None:
    """
    从 openFDA label.json 获取药品说明书中的 drug_interactions 原文。
    返回字符串（可能很长），失败返回 None。
    """
    try:
        r = await client.get(
            f"{OPENFDA_BASE}/label.json",
            params={
                "search": f'openfda.generic_name:"{drug_name}"',
                "limit": 3,
            },
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        for result in data.get("results", []):
            di_list = result.get("drug_interactions", [])
            if di_list:
                return " ".join(di_list)  # 拼接所有段落
        return None
    except Exception as e:
        print(f"openFDA label fetch error ({drug_name}): {e}")
        return None


def _extract_mention_context(text: str, target: str, window: int = 300) -> str | None:
    """
    在 text 中找 target（不区分大小写），返回前后 window 个字符的上下文。
    找不到返回 None。
    """
    idx = text.lower().find(target.lower())
    if idx < 0:
        return None
    snippet = text[max(0, idx - 50): idx + window]
    # 清理多余空白
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


def _has_keyword_near_mention(
    text: str,
    target: str,
    keywords: list[str],
    window: int = 1000,
) -> bool:
    """
    在文本中查找 target 的所有出现位置，检查其附近 window 范围是否出现任一关键词。
    用于避免短片段截断导致漏判高风险。
    """
    text_lower = text.lower()
    target_lower = target.lower()
    start = 0
    while True:
        idx = text_lower.find(target_lower, start)
        if idx < 0:
            return False
        ctx = text_lower[max(0, idx - 120): idx + window]
        if any(kw in ctx for kw in keywords):
            return True
        start = idx + len(target_lower)



async def query_drug_interactions(drugs: list[str]) -> dict:
    """
    查询多药物相互作用。
    真实逻辑：
      - 查药 A 的 openFDA 标签 drug_interactions 文本
      - 在文本里搜索药 B 的名字是否出现
      - 同时反向：查药 B 的标签里是否提到药 A
      - 只有 FDA 原文中真实出现对方名字才判定为有相互作用
      - 无数据时如实返回"未在FDA标签中发现直接提及"
    """
    if len(drugs) < 2:
        return {
            "success": False,
            "message": "需要至少两种药物才能查询相互作用",
            "data": {},
        }

    async with httpx.AsyncClient() as client:
        # Step 1: 转换中文药名为英文
        en_names: list[str] = [_to_english(zh) for zh in drugs]

        # Step 2: 并发获取每个药物的 FDA 标签 drug_interactions 原文
        import asyncio
        label_texts: dict[str, str | None] = {}
        tasks = {en: _fetch_drug_label(client, en) for en in en_names}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for en, result in zip(tasks.keys(), results):
            label_texts[en] = result if isinstance(result, str) else None

        # Step 3: 两两配对，在 FDA 原文中搜索对方药名
        interaction_pairs: list[dict] = []

        for i in range(len(en_names)):
            for j in range(i + 1, len(en_names)):
                drug_a = en_names[i]
                drug_b = en_names[j]

                evidence_a_mentions_b: str | None = None  # drug_a 的标签提到 drug_b
                evidence_b_mentions_a: str | None = None  # drug_b 的标签提到 drug_a

                if label_texts.get(drug_a):
                    evidence_a_mentions_b = _extract_mention_context(
                        label_texts[drug_a], drug_b
                    )
                if label_texts.get(drug_b):
                    evidence_b_mentions_a = _extract_mention_context(
                        label_texts[drug_b], drug_a
                    )

                has_label_a = label_texts.get(drug_a) is not None
                has_label_b = label_texts.get(drug_b) is not None

                if evidence_a_mentions_b or evidence_b_mentions_a:
                    # FDA 标签里确实提到了对方 → 有真实文本依据
                    evidence_parts = []
                    source_drug = None
                    if evidence_a_mentions_b:
                        evidence_parts.append(
                            f"[{drug_a.upper()} 说明书原文] ...{evidence_a_mentions_b}..."
                        )
                        source_drug = drug_a
                    if evidence_b_mentions_a:
                        evidence_parts.append(
                            f"[{drug_b.upper()} 说明书原文] ...{evidence_b_mentions_a}..."
                        )
                        source_drug = source_drug or drug_b

                    evidence_text = " | ".join(evidence_parts)

                    # 根据关键词判断严重程度
                    high_keywords = [
                        "bleeding", "hemorrhage", "contraindicated",
                        "contraindication", "contraindications",
                        "avoid", "serious", "fatal", "life-threatening",
                        "toxicity", "toxic", "anticoagulant",
                        "renal impairment", "hepatic impairment",
                        "increased risk of bleeding",
                    ]
                    moderate_keywords = [
                        "caution", "monitor", "increase", "decrease",
                        "may", "potential", "interaction",
                    ]
                    evidence_lower = evidence_text.lower()
                    high_in_full_context = False
                    if label_texts.get(drug_a) and evidence_a_mentions_b:
                        high_in_full_context = high_in_full_context or _has_keyword_near_mention(
                            label_texts[drug_a],
                            drug_b,
                            high_keywords,
                        )
                    if label_texts.get(drug_b) and evidence_b_mentions_a:
                        high_in_full_context = high_in_full_context or _has_keyword_near_mention(
                            label_texts[drug_b],
                            drug_a,
                            high_keywords,
                        )

                    if high_in_full_context or any(kw in evidence_lower for kw in high_keywords):
                        severity = "high"
                    elif any(kw in evidence_lower for kw in moderate_keywords):
                        severity = "moderate"
                    else:
                        severity = "moderate"  # 只要有提及，至少是中等

                    interaction_pairs.append({
                        "drugs": [drug_a, drug_b],
                        "severity": severity,
                        "description": (
                            f"FDA 官方说明书文本中，{source_drug} 的相互作用章节提及了 "
                            f"{drug_b if source_drug == drug_a else drug_a}。"
                        ),
                        "fda_label_evidence": evidence_text[:500],
                        "source": "openFDA label.json (drug_interactions field)",
                        "api_url": f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{source_drug}\"",
                    })

                elif has_label_a or has_label_b:
                    # 拿到了标签，但没有互相提及 → 如实告知
                    fetched = []
                    if has_label_a:
                        fetched.append(f"{drug_a}（已获取）")
                    if has_label_b:
                        fetched.append(f"{drug_b}（已获取）")
                    interaction_pairs.append({
                        "drugs": [drug_a, drug_b],
                        "severity": "unknown",
                        "description": (
                            f"已从 openFDA 获取 {'、'.join(fetched)} 的 FDA 标签，"
                            f"但 drug_interactions 章节未直接提及对方药物名称。"
                            f"不代表无相互作用，请咨询医生或药师。"
                        ),
                        "fda_label_evidence": None,
                        "source": "openFDA label.json (no cross-mention found)",
                        "api_url": f"https://api.fda.gov/drug/label.json?search=openfda.generic_name:\"{drug_a}\"",
                    })

                else:
                    # 两个标签都没拿到
                    interaction_pairs.append({
                        "drugs": [drug_a, drug_b],
                        "severity": "unknown",
                        "description": (
                            f"openFDA 未找到 {drug_a} 或 {drug_b} 的标签数据，"
                            f"无法判断相互作用。"
                        ),
                        "fda_label_evidence": None,
                        "source": "openFDA label.json (no label data)",
                        "api_url": None,
                    })

        # Step 4: 汇总风险等级
        severity_order = {"high": 0, "moderate": 1, "unknown": 2, "low": 3}
        top_severity = min(
            (severity_order.get(p["severity"], 99) for p in interaction_pairs),
            default=2,
        )
        severity_map_reverse = {0: "high", 1: "moderate", 2: "unknown", 3: "low"}
        top_severity_str = severity_map_reverse.get(top_severity, "unknown")

        severity_zh = {
            "high": "高风险",
            "moderate": "中度风险",
            "unknown": "未能确认",
            "low": "低风险",
        }

        desc_lines = []
        for p in interaction_pairs[:3]:
            sv_label = severity_zh.get(p["severity"], p["severity"])
            desc_lines.append(f"【{sv_label}】{p['description']}")
            if p.get("fda_label_evidence"):
                desc_lines.append(f"  FDA原文：{p['fda_label_evidence'][:200]}...")

        return {
            "success": True,
            "message": "药物相互作用查询完成（基于 openFDA 标签原文）",
            "data": {
                "drugs": drugs,
                "en_names": en_names,
                "interaction_level": severity_zh.get(top_severity_str, "未能确认"),
                "description": "\n".join(desc_lines),
                "recommendation": (
                    "请务必告知医生正在服用的所有药物，在医生或药师指导下决定是否同用。"
                    if top_severity_str == "high"
                    else "建议告知医生或药师，在专业指导下调整用药方案。"
                ),
                "pairs": interaction_pairs,
                "source": "openFDA label.json drug_interactions field",
                "has_api_data": any(v is not None for v in label_texts.values()),
                "api_results_count": sum(1 for v in label_texts.values() if v is not None),
                "labels_fetched": {k: (v is not None) for k, v in label_texts.items()},
            },
        }
