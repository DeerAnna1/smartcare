from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import SkillPackage


@dataclass(frozen=True)
class LoadedSkill:
    name: str
    display_name: str
    description: str
    instructions: str
    source_scope: str
    package_path: str
    version: str = "1.0.0"
    license: str = ""
    allowed_tools: tuple[str, ...] = ()
    trigger_examples: tuple[str, ...] = ()
    agent_allowlist: tuple[str, ...] = ()
    risk_level: str = "low"


def _parse_skill(path: Path, source_scope: str) -> LoadedSkill:
    raw = path.read_text(encoding="utf-8")
    metadata: dict = {}
    instructions = raw
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
    if match:
        metadata = yaml.safe_load(match.group(1)) or {}
        instructions = raw[match.end():].strip()
    name = str(metadata.get("name") or path.parent.name).strip()
    if not name or not instructions:
        raise ValueError(f"Invalid SKILL.md: {path}")
    return LoadedSkill(
        name=name,
        display_name=str(metadata.get("display-name") or metadata.get("display_name") or name).strip(),
        description=str(metadata.get("description", "")).strip(),
        instructions=instructions,
        source_scope=source_scope,
        package_path=str(path.parent.resolve()),
        version=str(metadata.get("version", "1.0.0")),
        license=str(metadata.get("license", "")),
        allowed_tools=tuple(metadata.get("allowed-tools") or metadata.get("allowed_tools") or ()),
        trigger_examples=tuple(metadata.get("trigger-examples") or metadata.get("trigger_examples") or ()),
        agent_allowlist=tuple(metadata.get("agents") or ()),
        risk_level=str(metadata.get("risk-level", "low")),
    )


def load_skill_packages(base_path: str | Path | None = None) -> list[LoadedSkill]:
    root = Path(base_path or get_settings().SKILLS_PATH)
    selected: dict[str, LoadedSkill] = {}
    for scope in ("public", "custom"):
        directory = root / scope
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("SKILL.md")):
            skill = _parse_skill(path, scope)
            selected[skill.name] = skill
    return list(selected.values())


async def sync_skill_packages(db: AsyncSession, base_path: str | Path | None = None) -> list[LoadedSkill]:
    loaded = load_skill_packages(base_path)
    for item in loaded:
        result = await db.execute(select(SkillPackage).where(SkillPackage.skill_id == item.name))
        row = result.scalar_one_or_none()
        manifest = {
            "license": item.license,
            "allowed_tools": list(item.allowed_tools),
            "agents": list(item.agent_allowlist),
            "risk_level": item.risk_level,
        }
        if row is None:
            row = SkillPackage(skill_id=item.name, name=item.display_name)
            db.add(row)
        row.name = item.display_name
        row.description = item.description
        row.instructions = item.instructions
        row.source_scope = item.source_scope
        row.source_type = "manual"
        row.package_path = item.package_path
        row.version = item.version
        row.trigger_examples = json.dumps(item.trigger_examples, ensure_ascii=False)
        row.manifest_json = json.dumps(manifest, ensure_ascii=False)
    await db.flush()
    return loaded
