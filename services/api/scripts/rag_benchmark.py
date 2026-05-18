#!/usr/bin/env python3
"""RAG 检索质量评估脚本。

计算 recall@k 和 MRR (Mean Reciprocal Rank) 指标。
用法: cd services/api && python -m scripts.rag_benchmark
"""
from __future__ import annotations

import json
import sys
import os

# 确保 app 包可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag_retriever import retrieve, _get_collection

# ─── Ground Truth 评估集 ─────────────────────────────────────────────────────
# 每条: (query, expected_keywords, expected_category)
# expected_keywords: 检索结果中应包含的关键词列表（命中任一即算相关）
# expected_category: 期望命中的知识类别

GROUND_TRUTH: list[tuple[str, list[str], str]] = [
    # 疾病分诊
    ("血压高头晕怎么办", ["高血压", "收缩压"], "疾病分诊"),
    ("血糖高口渴多尿", ["糖尿病", "血糖"], "疾病分诊"),
    ("胸痛放射到左肩", ["冠心病", "胸痛", "心绞痛"], "疾病分诊"),
    ("发烧咳嗽鼻塞", ["感冒", "上呼吸道感染"], "疾病分诊"),
    ("喘不上气呼吸困难", ["哮喘", "喘息"], "疾病分诊"),
    ("拉肚子呕吐腹痛", ["胃肠炎", "腹泻"], "疾病分诊"),
    ("偏头疼恶心", ["偏头痛", "头痛"], "疾病分诊"),
    ("心跳快手抖怕热", ["甲亢", "甲状腺"], "疾病分诊"),
    ("尿频尿急尿痛", ["尿路感染", "泌尿"], "疾病分诊"),
    ("紧张焦虑睡不着", ["焦虑", "焦虑障碍"], "疾病分诊"),
    ("头晕乏力面色苍白", ["贫血", "血红蛋白"], "化验解读"),
    ("脚趾关节红肿痛", ["痛风", "尿酸"], "疾病分诊"),
    # 化验解读
    ("白细胞偏高是什么意思", ["白细胞", "WBC", "感染"], "化验解读"),
    ("血红蛋白低怎么回事", ["血红蛋白", "贫血", "Hb"], "化验解读"),
    ("血小板减少怎么办", ["血小板", "PLT"], "化验解读"),
    ("转氨酶高是什么原因", ["ALT", "转氨酶", "肝"], "化验解读"),
    ("肌酐高肾功能不好", ["肌酐", "eGFR", "肾"], "化验解读"),
    ("空腹血糖7点多", ["血糖", "糖尿病", "空腹"], "化验解读"),
    ("血脂高胆固醇高", ["血脂", "胆固醇", "LDL"], "化验解读"),
    ("TSH高甲减", ["TSH", "甲减", "甲状腺"], "化验解读"),
    ("尿蛋白阳性", ["尿蛋白", "尿常规", "肾"], "化验解读"),
    # 药物知识
    ("阿司匹林饭前还是饭后吃", ["阿司匹林", "肠溶片"], "药物知识"),
    ("二甲双胍副作用", ["二甲双胍", "胃肠道"], "药物知识"),
    ("他汀类药物肌肉痛", ["他汀", "肌肉", "横纹肌溶解"], "药物知识"),
    ("布洛芬和阿司匹林能一起吃吗", ["布洛芬", "阿司匹林"], "药物知识"),
    ("华法林饮食注意", ["华法林", "维生素K", "INR"], "药物知识"),
    # 急救知识
    ("胸痛怀疑心梗怎么办", ["胸痛", "心梗", "120", "急救"], "急救知识"),
    ("中风怎么急救", ["中风", "脑卒中", "FAST"], "急救知识"),
    ("过敏性休克怎么处理", ["过敏", "休克", "肾上腺素"], "急救知识"),
    ("低血糖出冷汗", ["低血糖", "糖", "心慌"], "急救知识"),
    ("中暑高热怎么办", ["中暑", "热射病"], "急救知识"),
]


def run_benchmark(top_k: int = 3, score_threshold: float = 0.0) -> dict:
    """运行 RAG benchmark，返回评估结果。"""
    collection = _get_collection()
    doc_count = collection.count()
    if doc_count == 0:
        print("错误：知识库为空，请先加载知识 (POST /rag/load)")
        return {"error": "empty_collection"}

    print(f"知识库文档数: {doc_count}")
    print(f"评估集大小: {len(GROUND_TRUTH)} 条")
    print(f"参数: top_k={top_k}, score_threshold={score_threshold}")
    print("=" * 60)

    recalls_at_k: list[float] = []
    reciprocal_ranks: list[float] = []
    category_hits: dict[str, list[bool]] = {}
    failures: list[dict] = []

    for query, expected_kw, expected_cat in GROUND_TRUTH:
        result_text = retrieve(query, top_k=top_k, score_threshold=score_threshold, use_mmr=False)
        result_lower = result_text.lower()

        # 检查是否命中任一期望关键词
        kw_hits = [kw for kw in expected_kw if kw.lower() in result_lower]
        cat_hit = f"[{expected_cat}]" in result_text

        # Recall@k: 是否至少命中一个期望关键词
        recall = 1.0 if kw_hits else 0.0
        recalls_at_k.append(recall)

        # MRR: 第一个命中文档的排名倒数
        # 简化：按 --- 分割结果，找到第一个包含关键词的段落位置
        rr = 0.0
        if kw_hits:
            segments = result_text.split("\n---\n")
            for rank, seg in enumerate(segments, 1):
                if any(kw.lower() in seg.lower() for kw in kw_hits):
                    rr = 1.0 / rank
                    break
        reciprocal_ranks.append(rr)

        # 分类别统计
        if expected_cat not in category_hits:
            category_hits[expected_cat] = []
        category_hits[expected_cat].append(recall > 0)

        if recall == 0:
            failures.append({
                "query": query,
                "expected_keywords": expected_kw,
                "expected_category": expected_cat,
                "result_preview": result_text[:200] if result_text else "(空)",
            })

        status = "PASS" if recall > 0 else "FAIL"
        print(f"  [{status}] {query} → 命中: {kw_hits or '无'}")

    # 汇总
    avg_recall = sum(recalls_at_k) / len(recalls_at_k) if recalls_at_k else 0.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0

    category_summary = {}
    for cat, hits in category_hits.items():
        cat_recall = sum(hits) / len(hits) if hits else 0.0
        category_summary[cat] = {"count": len(hits), "recall": round(cat_recall, 3)}

    print("=" * 60)
    print(f"Recall@{top_k}: {avg_recall:.3f}")
    print(f"MRR:         {mrr:.3f}")
    print(f"\n分类别 Recall:")
    for cat, info in category_summary.items():
        print(f"  {cat}: {info['recall']:.3f} ({info['count']} 条)")

    if failures:
        print(f"\n失败用例 ({len(failures)} 条):")
        for f in failures:
            print(f"  - {f['query']} (期望: {f['expected_keywords']})")

    return {
        "recall_at_k": round(avg_recall, 3),
        "mrr": round(mrr, 3),
        "top_k": top_k,
        "score_threshold": score_threshold,
        "total_queries": len(GROUND_TRUTH),
        "passed": sum(recalls_at_k),
        "failed": len(GROUND_TRUTH) - sum(recalls_at_k),
        "category_summary": category_summary,
        "failures": failures,
    }


if __name__ == "__main__":
    # 确保知识库已加载
    stats = _get_collection().count()
    if stats == 0:
        print("知识库为空，先加载内置知识...")
        from app.services.rag_loader import load_knowledge
        result = load_knowledge()
        print(f"已加载 {result['loaded']} 条知识，类别: {result['categories']}")

    benchmark_result = run_benchmark(top_k=3, score_threshold=0.0)

    # 保存结果
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "rag_benchmark_result.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到: {output_path}")
