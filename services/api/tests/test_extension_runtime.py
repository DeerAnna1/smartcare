from pathlib import Path

import pytest

from app.mcp.manager import MCPConfigurationError, MCPManager
from app.mcp.policy import classify_tool
from app.services.context_builder import select_relevant_skills, select_relevant_tools
from app.skills.loader import load_skill_packages
from app.services.scheduled_content import safe_fallback_content


def test_custom_skill_shadows_public(tmp_path: Path):
    for scope, description in (("public", "public"), ("custom", "custom")):
        package = tmp_path / scope / "demo"
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: demo\ndescription: {description}\n---\nDo the work.", encoding="utf-8"
        )
    loaded = load_skill_packages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].description == "custom"
    assert loaded[0].source_scope == "custom"


def test_progressive_selection_respects_agent_policy():
    skills = [{
        "skill_id": "literature", "name": "医学文献", "description": "PubMed PMID 研究检索",
        "keywords": ["文献"], "trigger_examples": [], "agents": ["collector"], "tools": [],
    }]
    assert select_relevant_skills(skills, "请搜索 PubMed 文献", "collector")
    assert not select_relevant_skills(skills, "请搜索 PubMed 文献", "risk")


def test_medical_literature_turn_only_loads_search_schema():
    skill = {
        "skill_id": "medical-literature-review",
        "tools": [
            {"name": "pubmed__pubmed_search_articles"},
            {"name": "pubmed__pubmed_fetch_articles"},
            {"name": "pubmed__pubmed_fetch_fulltext"},
        ],
    }
    selected = select_relevant_tools(skill, "搜索相关医学研究并标注 PMID")
    assert [tool["name"] for tool in selected] == ["pubmed__pubmed_search_articles"]


@pytest.mark.asyncio
async def test_mcp_manager_rejects_unimplemented_transport():
    manager = MCPManager()
    with pytest.raises(MCPConfigurationError, match="Streamable HTTP"):
        await manager.discover("demo", {"transport": "stdio", "enabled": True})


def test_mcp_tool_safety_classification():
    assert classify_tool("pubmed__search_articles") == (True, False)
    assert classify_tool("booking__create_appointment") == (False, True)
    assert classify_tool("custom", {"readOnlyHint": True, "destructiveHint": True}) == (True, True)


def test_scheduled_education_fallback_is_non_empty_and_safe():
    content = safe_fallback_content("每日血糖管理", "每日血糖管理科普")
    assert "记录血糖" in content
    assert "不能替代医生诊断" in content
