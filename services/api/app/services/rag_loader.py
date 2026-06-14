"""RAG 数据加载逻辑 — 支持 QASystemOnMedicalKG 医学数据集和文档摄入。

数据来源：
1. QASystemOnMedicalKG (liuhuanyong) — 8808 条疾病知识，JSONL 格式
   包含：疾病名称、症状、病因、科室、治疗、用药、检查、预防、费用等
2. 用户上传的文档（PDF/DOCX/TXT/HTML）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.rag_retriever import add_documents, clear_collection
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 数据集存储目录
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "medical_datasets"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEDICAL_JSON = DATA_DIR / "medical.json"


def _load_medical_jsonl() -> list[dict]:
    """加载 QASystemOnMedicalKG 的 medical.json（JSONL 格式，每行一条 JSON）。"""
    if not MEDICAL_JSON.exists():
        logger.warning(f"数据集文件不存在: {MEDICAL_JSON}")
        return []
    records = []
    with open(MEDICAL_JSON, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(f"第 {line_num} 行 JSON 解析失败，跳过")
    logger.info(f"加载了 {len(records)} 条疾病记录")
    return records


def _join_list(val) -> str:
    """将列表或字符串值转为可读文本。"""
    if isinstance(val, list):
        return "、".join(str(v) for v in val if v)
    return str(val) if val else ""


def _disease_to_chunks(item: dict) -> list[tuple[str, str, str]]:
    """将疾病记录拆分为多个可检索的文本块。

    返回: [(text, disease_name, chunk_type), ...]
    每个 chunk 都带有疾病名称前缀，确保检索时有上下文。
    """
    name = item.get("name", "")
    if not name:
        return []

    chunks = []

    # 基本信息块：名称 + 简介 + 分类
    desc = _join_list(item.get("desc", ""))
    category = _join_list(item.get("category", ""))
    basic_parts = [f"疾病：{name}"]
    if desc and desc != "None":
        basic_parts.append(f"简介：{desc}")
    if category and category != "None":
        basic_parts.append(f"分类：{category}")
    chunks.append(("；".join(basic_parts), name, "基本信息"))

    # 症状块：症状 + 并发症
    symptom = _join_list(item.get("symptom", ""))
    acompany = _join_list(item.get("acompany", ""))
    if symptom or acompany:
        parts = [f"疾病：{name}"]
        if symptom and symptom != "None":
            parts.append(f"典型症状：{symptom}")
        if acompany and acompany != "None":
            parts.append(f"并发症：{acompany}")
        chunks.append(("；".join(parts), name, "症状"))

    # 病因块
    cause = _join_list(item.get("cause", ""))
    if cause and cause != "None":
        chunks.append((f"疾病：{name}；病因：{cause}", name, "病因"))

    # 治疗块：科室 + 治疗方式 + 周期 + 治愈率
    dept = _join_list(item.get("cure_department", ""))
    cure = _join_list(item.get("cure_way", ""))
    lasttime = _join_list(item.get("cure_lasttime", ""))
    cured = _join_list(item.get("cured_prob", ""))
    if any([dept, cure, lasttime, cured]):
        parts = [f"疾病：{name}"]
        if dept and dept != "None":
            parts.append(f"就诊科室：{dept}")
        if cure and cure != "None":
            parts.append(f"治疗方式：{cure}")
        if lasttime and lasttime != "None":
            parts.append(f"治疗周期：{lasttime}")
        if cured and cured != "None":
            parts.append(f"治愈率：{cured}")
        chunks.append(("；".join(parts), name, "治疗"))

    # 用药块
    drugs = _join_list(item.get("recommand_drug", ""))
    drug_detail = _join_list(item.get("drug_detail", ""))
    if drugs or drug_detail:
        parts = [f"疾病：{name}"]
        if drugs and drugs != "None":
            parts.append(f"推荐药物：{drugs}")
        if drug_detail and drug_detail != "None":
            parts.append(f"药物详情：{drug_detail}")
        chunks.append(("；".join(parts), name, "用药"))

    # 检查块
    check = _join_list(item.get("check", ""))
    if check and check != "None":
        chunks.append((f"疾病：{name}；相关检查：{check}", name, "检查"))

    # 预防块
    prevent = _join_list(item.get("prevent", ""))
    if prevent and prevent != "None":
        chunks.append((f"疾病：{name}；预防措施：{prevent}", name, "预防"))

    return chunks


def _split_text(text: str, chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[str]:
    """使用 langchain_text_splitters 切分长文本。"""
    if chunk_size is None:
        chunk_size = settings.RAG_CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = settings.RAG_CHUNK_OVERLAP

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " "],
        length_function=len,
    )
    return splitter.split_text(text)


def _parse_with_unstructured(file_path: str) -> str:
    """使用 unstructured 库解析文档（支持 PDF、DOCX、HTML 等复杂格式）。"""
    try:
        from unstructured.partition.auto import partition

        elements = partition(filename=file_path)
        text_parts = []
        for elem in elements:
            category = elem.category if hasattr(elem, "category") else ""
            text = str(elem).strip()
            if not text:
                continue
            if category == "Table":
                text_parts.append(f"[表格] {text}")
            else:
                text_parts.append(text)
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("unstructured 未安装，回退到基础解析")
        return ""
    except Exception as e:
        logger.warning(f"unstructured 解析失败: {e}")
        return ""


def load_knowledge() -> dict:
    """加载 QASystemOnMedicalKG 医学数据集到 ChromaDB。返回统计信息。"""
    records = _load_medical_jsonl()
    if not records:
        return {"loaded": 0, "categories": {"疾病": 0}, "source": "无数据"}

    clear_collection()

    all_docs: list[str] = []
    all_metas: list[dict] = []
    skipped = 0

    for item in records:
        chunks = _disease_to_chunks(item)
        if not chunks:
            skipped += 1
            continue

        for text, disease_name, chunk_type in chunks:
            # 长文本再切分（防止某些字段文本过长）
            sub_chunks = _split_text(text) if len(text) > settings.RAG_CHUNK_SIZE else [text]
            for i, chunk in enumerate(sub_chunks):
                meta = {
                    "category": "疾病",
                    "source": "QASystemOnMedicalKG",
                    "disease_name": disease_name,
                    "chunk_type": chunk_type,
                    "keywords": disease_name,
                }
                if len(sub_chunks) > 1:
                    meta["chunk_index"] = i
                    meta["total_chunks"] = len(sub_chunks)
                all_docs.append(chunk)
                all_metas.append(meta)

    count = 0
    if all_docs:
        count = add_documents(all_docs, all_metas)
        logger.info(f"成功加载 {count} 个文档片段到 ChromaDB（跳过 {skipped} 条空记录）")

    return {
        "loaded": count,
        "categories": {"疾病": len(records) - skipped},
        "source": "QASystemOnMedicalKG",
        "total_records": len(records),
        "skipped": skipped,
    }


def load_documents_from_files(file_paths: list[str], category: str = "医学文献") -> dict:
    """从文件列表加载文档，支持文本切分。

    支持 .txt, .md, .pdf, .docx, .html 格式。
    长文档会按 RAG_CHUNK_SIZE 切分后分别入库。
    """
    from pathlib import Path as P

    all_docs: list[str] = []
    all_metas: list[dict] = []

    for fp in file_paths:
        p = P(fp)
        if not p.exists():
            logger.warning(f"文件不存在: {fp}")
            continue

        ext = p.suffix.lower()
        text = ""

        if ext in (".txt", ".md"):
            text = p.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".pdf":
            text = _parse_with_unstructured(str(p))
            if not text:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(p))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                except Exception as e:
                    logger.warning(f"PDF 解析失败 {fp}: {e}")
                    continue
        elif ext == ".docx":
            text = _parse_with_unstructured(str(p))
            if not text:
                try:
                    from docx import Document
                    doc = Document(str(p))
                    text = "\n".join(para.text for para in doc.paragraphs if para.text)
                except Exception as e:
                    logger.warning(f"DOCX 解析失败 {fp}: {e}")
                    continue
        elif ext in (".html", ".htm"):
            text = _parse_with_unstructured(str(p))
            if not text:
                logger.warning(f"HTML 解析失败: {fp}")
                continue
        else:
            logger.warning(f"不支持的文件格式: {ext}")
            continue

        text = text.strip()
        if not text:
            continue

        chunks = _split_text(text)
        for i, chunk in enumerate(chunks):
            all_docs.append(chunk)
            all_metas.append({
                "category": category,
                "source": p.name,
                "keywords": "",
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

    if all_docs:
        count = add_documents(all_docs, all_metas)
        logger.info(f"从 {len(file_paths)} 个文件加载了 {count} 个文档片段")
        return {"loaded": count, "files": file_paths}

    return {"loaded": 0, "files": file_paths}
