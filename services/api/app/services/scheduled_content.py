"""Safe deterministic content for scheduled health education fallback."""


def safe_fallback_content(topic: str, title: str) -> str:
    normalized = topic.casefold()
    if "血糖" in normalized or "糖尿病" in normalized:
        advice = (
            "- 按医生建议记录血糖、饮食和活动情况，观察连续趋势，不根据单次读数自行调整药物。\n"
            "- 主食注意总量和搭配，优先选择蔬菜、全谷物及适量优质蛋白；规律活动并避免久坐。\n"
            "- 如果出现意识异常、明显乏力、持续呕吐，或血糖异常并伴随不适，应及时就医。"
        )
    elif "维生素c" in normalized or "维生素 C" in topic:
        advice = (
            "- 日常可从新鲜蔬菜和水果获得维生素 C，均衡饮食通常比单一补充剂更重要。\n"
            "- 使用补充剂前应查看成分和用量，避免同时服用多种含维生素 C 的产品。\n"
            "- 有肾结石、肾功能异常、孕期或正在长期用药时，补充前应咨询医生或药师。"
        )
    else:
        advice = (
            "- 保持规律饮食、适量运动和充足睡眠，并记录身体变化。\n"
            "- 健康指标应结合连续趋势和个人病史判断，不根据单次结果自行用药。\n"
            "- 出现持续或加重的不适时，应及时咨询专业医务人员。"
        )
    return f"## {title or topic}\n\n{advice}\n\n> 本内容仅用于健康科普，不能替代医生诊断和个体化治疗建议。"
