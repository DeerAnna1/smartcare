"""知识图谱数据服务 - 加载 medical.json 并提供查询接口。"""

import json
import logging
import re
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# ---------- 数据容器 ----------

_diseases: list[dict] = []          # 原始疾病记录
_disease_index: dict[str, dict] = {}   # name → record
_symptom_index: dict[str, list[str]] = {}   # symptom → [disease_name, ...]
_drug_index: dict[str, list[str]] = {}      # drug → [disease_name, ...]
_food_index: dict[str, list[str]] = {}      # food → [disease_name, ...]
_check_index: dict[str, list[str]] = {}     # check → [disease_name, ...]
_department_index: dict[str, list[str]] = {}  # dept → [disease_name, ...]

_loaded = False


def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    _load_data()
    _loaded = True


def _load_data():
    global _diseases, _disease_index, _symptom_index, _drug_index
    global _food_index, _check_index, _department_index

    # 兼容本地开发和 Docker 容器环境
    # 本地: .../Med-Help-Agent/services/api/app/services/kg_service.py → parents[4] = Med-Help-Agent
    # 容器: /app/app/services/kg_service.py → parents[2] = /app
    file_path = Path(__file__).resolve()
    for parent in file_path.parents:
        candidate = parent / "tmp" / "QASystemOnMedicalKG" / "data" / "medical.json"
        if candidate.exists():
            data_path = candidate
            break
    else:
        # 回退：尝试相对于项目根目录
        data_path = file_path.parents[2] / "tmp" / "QASystemOnMedicalKG" / "data" / "medical.json"
    if not data_path.exists():
        logger.warning("medical.json not found at %s — KG service will be empty", data_path)
        return

    logger.info("Loading medical.json from %s ...", data_path)
    diseases = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                diseases.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    _diseases = diseases
    logger.info("Loaded %d disease records", len(diseases))

    # 构建索引
    for d in diseases:
        name = d.get("name", "").strip()
        if not name:
            continue
        _disease_index[name] = d

        for s in (d.get("symptom") or []):
            s = s.strip()
            if s:
                _symptom_index.setdefault(s, []).append(name)

        for key in ("recommand_drug", "common_drug"):
            for dr in (d.get(key) or []):
                dr = dr.strip()
                if dr:
                    _drug_index.setdefault(dr, []).append(name)

        for key in ("do_eat", "not_eat", "recommand_eat"):
            for fd in (d.get(key) or []):
                fd = fd.strip()
                if fd:
                    _food_index.setdefault(fd, []).append(name)

        for ck in (d.get("check") or []):
            ck = ck.strip()
            if ck:
                _check_index.setdefault(ck, []).append(name)

        for dept in (d.get("cure_department") or []):
            dept = dept.strip()
            if dept:
                _department_index.setdefault(dept, []).append(name)

    logger.info(
        "KG indexes built: %d symptoms, %d drugs, %d foods, %d checks, %d departments",
        len(_symptom_index), len(_drug_index), len(_food_index),
        len(_check_index), len(_department_index),
    )


# ---------- 搜索 ----------

def search(query: str, entity_type: str = "all", limit: int = 20) -> list[dict]:
    """模糊搜索实体，返回匹配列表。"""
    _ensure_loaded()
    q = query.strip()
    if not q:
        return []

    results: list[dict] = []

    if entity_type in ("all", "disease"):
        for name, rec in _disease_index.items():
            if q in name:
                results.append({"type": "disease", "name": name, "desc": (rec.get("desc") or "")[:80]})
                if len(results) >= limit:
                    return results

    if entity_type in ("all", "symptom"):
        for name in _symptom_index:
            if q in name:
                results.append({"type": "symptom", "name": name, "desc": f"关联 {len(_symptom_index[name])} 种疾病"})
                if len(results) >= limit:
                    return results

    if entity_type in ("all", "drug"):
        for name in _drug_index:
            if q in name:
                results.append({"type": "drug", "name": name, "desc": f"关联 {len(_drug_index[name])} 种疾病"})
                if len(results) >= limit:
                    return results

    if entity_type in ("all", "food"):
        for name in _food_index:
            if q in name:
                results.append({"type": "food", "name": name, "desc": f"关联 {len(_food_index[name])} 种疾病"})
                if len(results) >= limit:
                    return results

    if entity_type in ("all", "check"):
        for name in _check_index:
            if q in name:
                results.append({"type": "check", "name": name, "desc": f"关联 {len(_check_index[name])} 种疾病"})
                if len(results) >= limit:
                    return results

    if entity_type in ("all", "department"):
        for name in _department_index:
            if q in name:
                results.append({"type": "department", "name": name, "desc": f"关联 {len(_department_index[name])} 种疾病"})
                if len(results) >= limit:
                    return results

    return results


# ---------- 节点详情 ----------

def get_node(entity_type: str, name: str) -> dict | None:
    """获取节点详情。"""
    _ensure_loaded()

    if entity_type == "disease":
        rec = _disease_index.get(name)
        if not rec:
            return None
        return {
            "type": "disease",
            "name": name,
            "data": {
                "desc": rec.get("desc", ""),
                "cause": rec.get("cause", ""),
                "prevent": rec.get("prevent", ""),
                "cure_way": rec.get("cure_way", []),
                "cure_lasttime": rec.get("cure_lasttime", ""),
                "cured_prob": rec.get("cured_prob", ""),
                "cost_money": rec.get("cost_money", ""),
                "get_prob": rec.get("get_prob", ""),
                "get_way": rec.get("get_way", ""),
                "easy_get": rec.get("easy_get", ""),
                "yibao_status": rec.get("yibao_status", ""),
                "category": rec.get("category", []),
                "symptom_count": len(rec.get("symptom") or []),
                "drug_count": len(rec.get("recommand_drug") or []),
                "check_count": len(rec.get("check") or []),
            },
        }

    # 非疾病节点，返回基本信息
    index_map = {
        "symptom": _symptom_index,
        "drug": _drug_index,
        "food": _food_index,
        "check": _check_index,
        "department": _department_index,
    }
    idx = index_map.get(entity_type)
    if not idx or name not in idx:
        return None

    return {
        "type": entity_type,
        "name": name,
        "data": {
            "related_diseases": idx[name],
            "related_count": len(idx[name]),
        },
    }


# ---------- 邻居节点和边 ----------

def get_neighbors(entity_type: str, name: str) -> dict:
    """获取节点的邻居（1跳），返回 React Flow 兼容格式。"""
    _ensure_loaded()
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()

    def _add_node(n_type: str, n_name: str, n_data: dict | None = None):
        nid = f"{n_type}_{n_name}"
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        nodes.append({"id": nid, "type": n_type, "label": n_name, "data": n_data or {}})

    def _add_edge(source: str, target: str, label: str, edge_type: str):
        eid = f"{source}_{target}_{edge_type}"
        edges.append({"id": eid, "source": source, "target": target, "label": label, "type": edge_type})

    if entity_type == "disease":
        rec = _disease_index.get(name)
        if not rec:
            return {"nodes": [], "edges": []}

        center_id = f"disease_{name}"
        _add_node("disease", name, {
            "desc": (rec.get("desc") or "")[:120],
            "category": rec.get("category", []),
        })

        # 症状
        for s in (rec.get("symptom") or [])[:15]:
            _add_node("symptom", s)
            _add_edge(center_id, f"symptom_{s}", "症状", "has_symptom")

        # 药物
        for dr in (rec.get("recommand_drug") or [])[:10]:
            _add_node("drug", dr)
            _add_edge(center_id, f"drug_{dr}", "推荐药物", "recommends_drug")

        # 检查
        for ck in (rec.get("check") or [])[:10]:
            _add_node("check", ck)
            _add_edge(center_id, f"check_{ck}", "检查", "requires_check")

        # 科室
        for dept in (rec.get("cure_department") or [])[:5]:
            _add_node("department", dept)
            _add_edge(center_id, f"department_{dept}", "科室", "treated_in")

        # 饮食建议
        for fd in (rec.get("do_eat") or [])[:8]:
            _add_node("food", fd)
            _add_edge(center_id, f"food_{fd}", "宜吃", "do_eat")

        # 并发症
        for ac in (rec.get("acompany") or [])[:5]:
            _add_node("disease", ac, {})
            _add_edge(center_id, f"disease_{ac}", "并发症", "acompany_with")

    else:
        # 非疾病节点：反向查找关联疾病
        index_map = {
            "symptom": _symptom_index,
            "drug": _drug_index,
            "food": _food_index,
            "check": _check_index,
            "department": _department_index,
        }
        idx = index_map.get(entity_type)
        if not idx or name not in idx:
            return {"nodes": [], "edges": []}

        center_id = f"{entity_type}_{name}"
        _add_node(entity_type, name)

        # 关联疾病（最多显示 10 个）
        for dname in idx[name][:10]:
            rec = _disease_index.get(dname)
            _add_node("disease", dname, {"desc": (rec.get("desc") or "")[:80] if rec else ""})

            # 边标签
            edge_label_map = {
                "symptom": "症状",
                "drug": "推荐药物",
                "food": "饮食相关",
                "check": "检查",
                "department": "科室",
            }
            _add_edge(f"{entity_type}_{name}", f"disease_{dname}", edge_label_map.get(entity_type, "关联"), f"related_{entity_type}")

    return {"nodes": nodes, "edges": edges}


# ---------- 子图（多跳） ----------

def get_subgraph(entity_type: str, name: str, depth: int = 1) -> dict:
    """获取以指定节点为中心的子图。depth=1 等同于 get_neighbors。"""
    _ensure_loaded()
    depth = min(depth, 2)  # 限制最大 2 跳

    result = get_neighbors(entity_type, name)
    if depth <= 1:
        return result

    # 2 跳：对第一跳的疾病节点再展开其症状和药物
    existing_node_ids = {n["id"] for n in result["nodes"]}
    existing_edge_ids = {e["id"] for e in result["edges"]}

    disease_nodes = [n for n in result["nodes"] if n["type"] == "disease" and n["id"] != f"disease_{name}"]

    for dn in disease_nodes[:5]:  # 最多展开 5 个疾病
        dname = dn["label"]
        rec = _disease_index.get(dname)
        if not rec:
            continue

        center_id = f"disease_{dname}"

        for s in (rec.get("symptom") or [])[:5]:
            sid = f"symptom_{s}"
            if sid not in existing_node_ids:
                existing_node_ids.add(sid)
                result["nodes"].append({"id": sid, "type": "symptom", "label": s, "data": {}})
            eid = f"{center_id}_{sid}_has_symptom"
            if eid not in existing_edge_ids:
                existing_edge_ids.add(eid)
                result["edges"].append({"id": eid, "source": center_id, "target": sid, "label": "症状", "type": "has_symptom"})

        for dr in (rec.get("recommand_drug") or [])[:3]:
            did = f"drug_{dr}"
            if did not in existing_node_ids:
                existing_node_ids.add(did)
                result["nodes"].append({"id": did, "type": "drug", "label": dr, "data": {}})
            eid = f"{center_id}_{did}_recommends_drug"
            if eid not in existing_edge_ids:
                existing_edge_ids.add(eid)
                result["edges"].append({"id": eid, "source": center_id, "target": did, "label": "推荐药物", "type": "recommends_drug"})

    return result


# ---------- 问诊上下文 ----------

def get_consultation_context(symptoms: list[str], diseases: list[str] | None = None) -> dict:
    """根据症状和候选疾病，生成知识图谱上下文（用于问诊嵌入）。"""
    _ensure_loaded()

    all_nodes: dict[str, dict] = {}
    all_edges: list[dict] = []
    seen_edges: set[str] = set()

    def _ensure_node(n_type: str, n_name: str, n_data: dict | None = None):
        nid = f"{n_type}_{n_name}"
        if nid not in all_nodes:
            all_nodes[nid] = {"id": nid, "type": n_type, "label": n_name, "data": n_data or {}}

    def _ensure_edge(source: str, target: str, label: str, edge_type: str):
        eid = f"{source}_{target}_{edge_type}"
        if eid not in seen_edges:
            seen_edges.add(eid)
            all_edges.append({"id": eid, "source": source, "target": target, "label": label, "type": edge_type})

    # 调用方可以传实体名，也可以传完整的自然语言对话。这里统一解析成图谱中
    # 实际存在的实体，避免依赖前端硬编码关键词和完全相等匹配。
    symptom_aliases = {"发烧": "发热", "喉咙痛": "咽痛", "喘不上气": "呼吸困难"}
    raw_symptom_text = " ".join(symptoms)
    for alias, canonical in symptom_aliases.items():
        if alias in raw_symptom_text:
            raw_symptom_text += f" {canonical}"
    resolved_symptoms = [name for name in _symptom_index if name in raw_symptom_text]
    resolved_symptoms.sort(key=len, reverse=True)
    # 较长实体优先，并限制规模，避免一段长对话生成过大的子图。
    symptoms = list(dict.fromkeys(resolved_symptoms))[:12]

    resolved_diseases = set(diseases or [])
    raw_disease_text = " ".join(diseases or [])
    resolved_diseases.update(name for name in _disease_index if name in raw_disease_text)

    # 根据症状查找关联疾病
    symptom_diseases: dict[str, list[str]] = {}
    for s in symptoms:
        s = s.strip()
        if s and s in _symptom_index:
            symptom_diseases[s] = _symptom_index[s][:5]
            _ensure_node("symptom", s)

    # 合并用户指定的候选疾病
    all_disease_names: set[str] = resolved_diseases
    for dlist in symptom_diseases.values():
        all_disease_names.update(dlist)

    # 构建子图
    for dname in list(all_disease_names)[:8]:
        rec = _disease_index.get(dname)
        if not rec:
            continue

        _ensure_node("disease", dname, {"desc": (rec.get("desc") or "")[:100]})

        # 连接症状
        for s in symptoms:
            s = s.strip()
            if s and s in (rec.get("symptom") or []):
                _ensure_edge(f"disease_{dname}", f"symptom_{s}", "症状", "has_symptom")

        # 药物
        for dr in (rec.get("recommand_drug") or [])[:5]:
            _ensure_node("drug", dr)
            _ensure_edge(f"disease_{dname}", f"drug_{dr}", "推荐药物", "recommends_drug")

        # 检查
        for ck in (rec.get("check") or [])[:5]:
            _ensure_node("check", ck)
            _ensure_edge(f"disease_{dname}", f"check_{ck}", "检查", "requires_check")

        # 科室
        for dept in (rec.get("cure_department") or [])[:3]:
            _ensure_node("department", dept)
            _ensure_edge(f"disease_{dname}", f"department_{dept}", "科室", "treated_in")

    return {
        "nodes": list(all_nodes.values()),
        "edges": all_edges,
        "symptom_diseases": symptom_diseases,
    }


# ---------- 文本摘要（用于 LLM 上下文注入） ----------

def get_context_summary(symptoms: list[str], diseases: list[str] | None = None) -> str:
    """生成知识图谱的文字摘要，用于注入 LLM 的 system prompt。"""
    _ensure_loaded()
    lines: list[str] = ["【医学知识图谱参考信息】"]

    # 症状 → 可能疾病
    if symptoms:
        lines.append("患者相关症状: " + "、".join(symptoms))
        for s in symptoms:
            s = s.strip()
            if s in _symptom_index:
                related = _symptom_index[s][:5]
                lines.append(f"  症状「{s}」常见于: {', '.join(related)}")

    # 候选疾病详情
    target_diseases = diseases or []
    if not target_diseases:
        # 从症状推断
        for s in symptoms:
            s = s.strip()
            if s in _symptom_index:
                target_diseases.extend(_symptom_index[s][:3])
        target_diseases = list(set(target_diseases))[:5]

    for dname in target_diseases:
        rec = _disease_index.get(dname)
        if not rec:
            continue
        lines.append(f"\n疾病「{dname}」:")
        if rec.get("desc"):
            lines.append(f"  简介: {rec['desc'][:150]}")
        if rec.get("symptom"):
            lines.append(f"  典型症状: {', '.join(rec['symptom'][:8])}")
        if rec.get("recommand_drug"):
            lines.append(f"  推荐药物: {', '.join(rec['recommand_drug'][:5])}")
        if rec.get("check"):
            lines.append(f"  建议检查: {', '.join(rec['check'][:5])}")
        if rec.get("cure_department"):
            lines.append(f"  就诊科室: {', '.join(rec['cure_department'])}")
        if rec.get("cure_way"):
            lines.append(f"  治疗方法: {', '.join(rec['cure_way'][:3])}")
        if rec.get("prevent"):
            lines.append(f"  预防建议: {rec['prevent'][:100]}")

    return "\n".join(lines) if len(lines) > 1 else ""
