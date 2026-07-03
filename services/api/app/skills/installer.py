from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

from app.core.config import get_settings


class SkillInstallError(ValueError):
    pass


def install_skill_archive(data: bytes, max_uncompressed_bytes: int = 5 * 1024 * 1024) -> Path:
    root = Path(get_settings().SKILLS_PATH) / "custom"
    root.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillInstallError("无效的 .skill/ZIP 文件") from exc
    members = archive.infolist()
    if not members or sum(item.file_size for item in members) > max_uncompressed_bytes:
        raise SkillInstallError("Skill 包为空或解压后超过 5MB")
    roots: set[str] = set()
    for item in members:
        path = Path(item.filename)
        if path.is_absolute() or ".." in path.parts or item.is_dir() and len(path.parts) == 0:
            raise SkillInstallError("Skill 包包含不安全路径")
        if path.parts:
            roots.add(path.parts[0])
    if len(roots) != 1:
        raise SkillInstallError("Skill 包必须只有一个顶层目录")
    package_name = next(iter(roots))
    if not package_name.replace("-", "").replace("_", "").isalnum():
        raise SkillInstallError("Skill 目录名不合法")
    target = (root / package_name).resolve()
    if target.exists():
        shutil.rmtree(target)
    for item in members:
        destination = (root / item.filename).resolve()
        if root.resolve() not in destination.parents and destination != root.resolve():
            raise SkillInstallError("Skill 包路径越界")
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(item))
    if not (target / "SKILL.md").is_file():
        shutil.rmtree(target, ignore_errors=True)
        raise SkillInstallError("Skill 包缺少顶层 SKILL.md")
    return target
