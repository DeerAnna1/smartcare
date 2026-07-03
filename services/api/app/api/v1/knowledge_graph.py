"""知识图谱 API 端点。"""

from fastapi import APIRouter, HTTPException, Query

from app.services import kg_service

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    type: str = Query("all", description="实体类型: all|disease|symptom|drug|food|check|department"),
    limit: int = Query(20, ge=1, le=50),
):
    """搜索知识图谱实体。"""
    results = kg_service.search(q, entity_type=type, limit=limit)
    return {"results": results, "total": len(results)}


@router.get("/node/{entity_type}/{name}")
async def get_node_detail(entity_type: str, name: str):
    """获取节点详情。"""
    valid_types = {"disease", "symptom", "drug", "food", "check", "department"}
    if entity_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的实体类型: {entity_type}")

    node = kg_service.get_node(entity_type, name)
    if not node:
        raise HTTPException(status_code=404, detail=f"未找到 {entity_type}: {name}")
    return node


@router.get("/neighbors/{entity_type}/{name}")
async def get_neighbors(entity_type: str, name: str):
    """获取节点的邻居（1跳）。"""
    valid_types = {"disease", "symptom", "drug", "food", "check", "department"}
    if entity_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的实体类型: {entity_type}")

    result = kg_service.get_neighbors(entity_type, name)
    return result


@router.get("/subgraph/{entity_type}/{name}")
async def get_subgraph(
    entity_type: str,
    name: str,
    depth: int = Query(1, ge=1, le=2, description="跳数: 1 或 2"),
):
    """获取以指定节点为中心的子图。"""
    valid_types = {"disease", "symptom", "drug", "food", "check", "department"}
    if entity_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的实体类型: {entity_type}")

    result = kg_service.get_subgraph(entity_type, name, depth=depth)
    return result


@router.get("/consultation-context")
async def get_consultation_context(
    symptoms: str = Query("", description="症状，逗号分隔"),
    diseases: str = Query("", description="候选疾病，逗号分隔"),
):
    """根据症状和候选疾病，获取问诊相关的知识图谱子图。"""
    symptom_list = [s.strip() for s in symptoms.split(",") if s.strip()] if symptoms else []
    disease_list = [d.strip() for d in diseases.split(",") if d.strip()] if diseases else []

    if not symptom_list and not disease_list:
        raise HTTPException(status_code=400, detail="至少提供一个症状或疾病")

    result = kg_service.get_consultation_context(symptom_list, disease_list)
    return result


@router.get("/context-summary")
async def get_context_summary(
    symptoms: str = Query("", description="症状，逗号分隔"),
    diseases: str = Query("", description="候选疾病，逗号分隔"),
):
    """获取知识图谱的文字摘要（用于 LLM 上下文注入）。"""
    symptom_list = [s.strip() for s in symptoms.split(",") if s.strip()] if symptoms else []
    disease_list = [d.strip() for d in diseases.split(",") if d.strip()] if diseases else []

    summary = kg_service.get_context_summary(symptom_list, disease_list)
    return {"summary": summary}
