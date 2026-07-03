"""RAG 医学知识库 API。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from pydantic import BaseModel

from app.api.deps.auth import get_current_user_required, get_current_admin_user
from app.core.database import get_db
from app.models.models import User
from app.services.rag_retriever import (
    add_documents,
    delete_documents_by_metadata,
    get_stats,
    search_documents,
)
from app.services.rag_loader import load_knowledge, load_documents_from_files, _split_text

router = APIRouter(prefix="/rag", tags=["RAG 知识库"])

RAG_IMAGE_DIR = Path(__file__).resolve().parents[3] / "uploads" / "knowledge-images"
RAG_DOCUMENT_DIR = Path(__file__).resolve().parents[3] / "uploads" / "knowledge-documents"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx", ".md"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_SIZE = 50 * 1024 * 1024


class LoadResponse(BaseModel):
    loaded: int
    categories: dict
    source: str = ""
    total_records: int = 0
    skipped: int = 0


class DocumentLoadRequest(BaseModel):
    file_paths: list[str]
    category: str = "医学文献"


class DocumentLoadResponse(BaseModel):
    loaded: int
    files: list[str]


class SearchItem(BaseModel):
    content: str
    metadata: dict
    score: float


@router.post("/load", response_model=LoadResponse)
async def load_medical_knowledge(
    user: User = Depends(get_current_admin_user),
):
    """加载内置医学知识到 ChromaDB 向量库。仅管理员可调用。"""
    result = await asyncio.to_thread(load_knowledge)
    return LoadResponse(**result)


@router.post("/load-documents", response_model=DocumentLoadResponse)
async def load_documents(
    body: DocumentLoadRequest,
    user: User = Depends(get_current_admin_user),
):
    """从文件列表加载文档到知识库（支持文本切分）。仅管理员可调用。

    注意：file_paths 必须是已鉴权的上传文件路径，不接受任意服务端路径。
    """
    # 安全检查：只允许访问 uploads 目录下的文件
    from pathlib import Path
    upload_dir = Path(__file__).resolve().parents[3] / "uploads"
    for fp in body.file_paths:
        resolved = Path(fp).resolve()
        if not str(resolved).startswith(str(upload_dir.resolve())):
            return DocumentLoadResponse(loaded=0, files=[], detail="只能访问已上传的文件")
    result = load_documents_from_files(body.file_paths, body.category)
    return DocumentLoadResponse(**result)


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., min_length=1, max_length=500, description="检索关键词"),
    top_k: int = Query(3, ge=1, le=10),
    score_threshold: float = Query(0.35, ge=0.0, le=1.0, description="最低相似度阈值"),
    use_mmr: bool = Query(True, description="是否使用 MMR 重排"),
    user: User = Depends(get_current_user_required),
):
    """返回结构化 RAG 检索结果。"""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="检索关键词不能为空")
    result = await asyncio.to_thread(
        search_documents,
        query,
        top_k,
        score_threshold,
        use_mmr,
    )
    return {"query": query, "result": result, "params": {"top_k": top_k, "score_threshold": score_threshold, "use_mmr": use_mmr}}


@router.get("/stats")
async def knowledge_stats(
    user: User = Depends(get_current_user_required),
):
    """返回知识库统计信息。"""
    return get_stats()


@router.get("/documents")
async def list_knowledge_documents(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """列出已入库的知识文档。"""
    from app.models.models import KnowledgeDocument
    from sqlalchemy import func, select

    # Count total
    count_q = select(func.count()).select_from(KnowledgeDocument)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # List documents
    q = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    docs = result.scalars().all()

    return {
        "total": total,
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "source_type": d.source_type,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "image_url": f"/api/v1/rag/documents/{d.id}/image" if d.source_type == "image" else None,
                "file_url": f"/api/v1/rag/documents/{d.id}/file" if d.source_type == "document" else None,
            }
            for d in docs
        ],
    }


@router.delete("/documents/{doc_id}")
async def delete_knowledge_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """删除知识文档及其 chunks。"""
    from app.models.models import KnowledgeDocument, KnowledgeChunk

    doc = await db.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # Delete chunks and the locally stored source file.
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id))
    if doc.source_type in ("image", "document") and doc.source_uri:
        source_path = Path(doc.source_uri)
        try:
            allowed_dir = RAG_IMAGE_DIR if doc.source_type == "image" else RAG_DOCUMENT_DIR
            source_path.resolve().relative_to(allowed_dir.resolve())
            source_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            # Never delete arbitrary paths recorded by other ingestion sources.
            pass
    try:
        await asyncio.to_thread(delete_documents_by_metadata, doc_id)
    except Exception:
        # 数据库记录仍应可删除；向量库不可用时不阻断清理操作。
        pass
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted", "id": doc_id}


@router.post("/ingest-file")
@router.post("/ingest-image")
async def ingest_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """上传图片或文档，提取文本并创建知识库记录。"""
    import uuid

    original_name = Path(file.filename or "document.txt").name
    ext = Path(original_name).suffix.lower()
    is_image = ext in ALLOWED_IMAGE_EXTENSIONS
    is_document = ext in ALLOWED_DOCUMENT_EXTENSIONS
    if not is_image and not is_document:
        raise HTTPException(status_code=400, detail="文件格式不支持，仅支持 JPG、PNG、WebP、PDF、DOCX、TXT、XLSX、MD")
    if is_image and file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="图片内容类型不支持，仅支持 JPG、PNG、WebP")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    max_size = MAX_IMAGE_SIZE if is_image else MAX_DOCUMENT_SIZE
    if len(content) > max_size:
        limit_mb = max_size // 1024 // 1024
        raise HTTPException(status_code=400, detail=f"文件不能超过 {limit_mb}MB")

    save_dir = RAG_IMAGE_DIR if is_image else RAG_DOCUMENT_DIR
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{uuid.uuid4()}{ext}"
    try:
        save_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="文件保存失败") from exc

    # Create document record and index extracted text into SQL and ChromaDB.
    from app.models.models import KnowledgeDocument, KnowledgeChunk
    source_type = "image" if is_image else "document"
    doc = KnowledgeDocument(
        title=original_name,
        source_type=source_type,
        source_uri=str(save_path),
        status="processing",
        chunk_count=0,
    )
    db.add(doc)
    try:
        await db.flush()

        extracted_text = ""
        extraction_status = "failed"
        if is_image:
            try:
                from app.api.v1.upload import _extract_text_via_llm_vision, _extract_text_via_ocr_space
                from app.core.config import get_settings

                app_settings = get_settings()
                if app_settings.OCR_PROVIDER.lower() == "ocr_space":
                    extracted_text, extraction_status = await _extract_text_via_ocr_space(content, original_name)
                if extraction_status != "success":
                    extracted_text, extraction_status = await _extract_text_via_llm_vision(content, ext)
            except Exception:
                extraction_status = "failed"
        else:
            from app.api.v1.upload import _extract_text_from_document
            extracted_text, extraction_status = await asyncio.to_thread(
                _extract_text_from_document, content, ext
            )
            if extraction_status != "success" or not extracted_text.strip():
                raise HTTPException(status_code=422, detail="文档中未提取到可索引文本")

        # OCR 服务不可用时至少索引标题，使图片仍能按文件名检索。
        searchable_text = extracted_text.strip() or f"图片文档：{Path(original_name).stem}"
        chunks = _split_text(searchable_text)
        category = "知识库图片" if is_image else "知识库文档"
        metadatas = [
            {
                "category": category,
                "source": original_name,
                "document_id": doc.id,
                "chunk_index": index,
            }
            for index, _ in enumerate(chunks)
        ]
        vector_ids = [f"{doc.id}:{index}" for index in range(len(chunks))]
        await asyncio.to_thread(add_documents, chunks, metadatas, vector_ids)

        for index, chunk in enumerate(chunks):
            db.add(KnowledgeChunk(
                document_id=doc.id,
                chunk_index=index,
                content=chunk,
                embedding_status="completed",
            ))
        doc.chunk_count = len(chunks)
        doc.status = "published"
        doc.error = "" if extraction_status == "success" else "OCR 不可用，当前仅支持按图片文件名检索"
        await db.commit()
        await db.refresh(doc)
    except Exception:
        try:
            if doc.id:
                await asyncio.to_thread(delete_documents_by_metadata, doc.id)
        except Exception:
            pass
        save_path.unlink(missing_ok=True)
        raise

    return {
        "id": doc.id,
        "title": doc.title,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "source_type": doc.source_type,
        "extraction_status": extraction_status,
    }

@router.get("/documents/{doc_id}/image")
async def get_document_image(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """获取文档图片。"""
    import os
    from fastapi.responses import FileResponse
    from app.models.models import KnowledgeDocument

    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if doc.source_type != "image" or not doc.source_uri:
        raise HTTPException(status_code=404, detail="该文档不是图片类型")

    if not os.path.exists(doc.source_uri):
        raise HTTPException(status_code=404, detail="图片文件不存在")

    return FileResponse(doc.source_uri)


# MIME 类型映射
DOCUMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".md": "text/markdown",
}


@router.get("/documents/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    """下载或在线预览文档文件。PDF 在浏览器中直接打开，其他格式触发下载。"""
    import os
    from fastapi.responses import FileResponse
    from app.models.models import KnowledgeDocument

    result = await db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    if doc.source_type != "document" or not doc.source_uri:
        raise HTTPException(status_code=404, detail="该文档不是文件类型")

    if not os.path.exists(doc.source_uri):
        raise HTTPException(status_code=404, detail="文档文件不存在")

    ext = Path(doc.source_uri).suffix.lower()
    media_type = DOCUMENT_MIME_TYPES.get(ext, "application/octet-stream")

    # PDF、文本、Word 在浏览器中直接打开，其他格式触发下载
    disposition_type = "inline" if ext in (".pdf", ".txt", ".md", ".docx") else "attachment"

    return FileResponse(
        doc.source_uri,
        media_type=media_type,
        filename=doc.title,
        content_disposition_type=disposition_type,
    )
