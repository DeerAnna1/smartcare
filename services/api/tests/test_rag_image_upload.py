"""Knowledge-base image ingestion tests."""

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.api.v1 import rag


class FakeSession:
    def add(self, document):
        if hasattr(document, "source_uri"):
            self.document = document

    async def commit(self):
        return None

    async def flush(self):
        if not self.document.id:
            self.document.id = "test-document-id"

    async def refresh(self, document):
        return None


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_ingest_image_persists_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "RAG_IMAGE_DIR", tmp_path)
    monkeypatch.setattr(rag, "add_documents", lambda documents, metadatas, ids: len(documents))
    monkeypatch.setattr(rag, "delete_documents_by_metadata", lambda document_id: None)
    monkeypatch.setattr(rag, "_split_text", lambda text: [text])
    from app.api.v1 import upload
    monkeypatch.setattr(upload, "_extract_text_via_llm_vision", _fake_ocr)
    monkeypatch.setattr(upload, "_extract_text_via_ocr_space", _fake_ocr)
    session = FakeSession()

    result = await rag.ingest_image(
        make_upload("scan.png", b"png-data", "image/png"),
        session,
        None,
    )

    assert result["title"] == "scan.png"
    assert result["chunk_count"] == 1
    assert session.document.source_uri.startswith(str(tmp_path))
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.asyncio
async def test_ingest_image_rejects_non_image(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "RAG_IMAGE_DIR", tmp_path)

    with pytest.raises(HTTPException) as exc:
        await rag.ingest_image(
            make_upload("notes.txt", b"not-an-image", "text/plain"),
            FakeSession(),
            None,
        )

    assert exc.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


async def _fake_ocr(content: bytes, ext: str) -> tuple[str, str]:
    return "血压 120/80 mmHg", "success"
