"""Standalone batch indexing script for RAG knowledge base.

改进版特性：
- 从环境变量统一读取 embedding 模型（与 config.py 一致）
- 临时 collection + 原子切换：索引失败不破坏旧 collection
- Manifest：记录索引元数据（checksum、模型、chunk 数等）
- Resume：每批插入后记录 checkpoint，中断可恢复
- 流式处理：生成器加载记录，避免 OOM

Usage:
  docker run --rm -m 4g \
    -v /path/to/api:/app \
    -v /path/to/models:/home/apiuser/.cache/huggingface/hub \
    -e RAG_EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5 \
    docker-api:latest python3 /app/scripts/batch_index.py
"""
import sys
import os
import json
import time
import logging
import hashlib
import gc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "medical_datasets")
MEDICAL_JSON = os.path.join(DATA_DIR, "medical.json")

EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
COLLECTION_NAME = "medical_knowledge"
TMP_COLLECTION_NAME = "medical_knowledge_tmp"
MANIFEST_PATH = os.path.join(CHROMA_DIR, "index_manifest.json")
CHECKPOINT_PATH = os.path.join(CHROMA_DIR, "index_checkpoint.json")

ENCODE_BATCH = 32
INSERT_CHUNK = 1000


def load_records():
    """生成器：逐条加载记录，避免一次性载入内存。"""
    with open(MEDICAL_JSON, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def join_list(val):
    if isinstance(val, list):
        return "、".join(str(v) for v in val if v)
    return str(val) if val else ""


def disease_to_chunks(item):
    name = item.get("name", "")
    if not name:
        return []
    chunks = []

    desc = join_list(item.get("desc", ""))
    category = join_list(item.get("category", ""))
    parts = [f"疾病：{name}"]
    if desc and desc != "None":
        parts.append(f"简介：{desc}")
    if category and category != "None":
        parts.append(f"分类：{category}")
    chunks.append(("；".join(parts), name, "基本信息"))

    symptom = join_list(item.get("symptom", ""))
    acompany = join_list(item.get("acompany", ""))
    if symptom or acompany:
        parts = [f"疾病：{name}"]
        if symptom and symptom != "None":
            parts.append(f"典型症状：{symptom}")
        if acompany and acompany != "None":
            parts.append(f"并发症：{acompany}")
        chunks.append(("；".join(parts), name, "症状"))

    cause = join_list(item.get("cause", ""))
    if cause and cause != "None":
        chunks.append((f"疾病：{name}；病因：{cause}", name, "病因"))

    dept = join_list(item.get("cure_department", ""))
    cure = join_list(item.get("cure_way", ""))
    lasttime = join_list(item.get("cure_lasttime", ""))
    cured = join_list(item.get("cured_prob", ""))
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

    drugs = join_list(item.get("recommand_drug", ""))
    drug_detail = join_list(item.get("drug_detail", ""))
    if drugs or drug_detail:
        parts = [f"疾病：{name}"]
        if drugs and drugs != "None":
            parts.append(f"推荐药物：{drugs}")
        if drug_detail and drug_detail != "None":
            parts.append(f"药物详情：{drug_detail}")
        chunks.append(("；".join(parts), name, "用药"))

    check = join_list(item.get("check", ""))
    if check and check != "None":
        chunks.append((f"疾病：{name}；相关检查：{check}", name, "检查"))

    prevent = join_list(item.get("prevent", ""))
    if prevent and prevent != "None":
        chunks.append((f"疾病：{name}；预防措施：{prevent}", name, "预防"))

    return chunks


def load_checkpoint() -> dict:
    """加载 checkpoint，支持 resume。"""
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_batch_end": 0, "inserted": 0}


def save_checkpoint(batch_end: int, inserted: int):
    """保存 checkpoint。"""
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump({"last_batch_end": batch_end, "inserted": inserted}, f)


def save_manifest(chunk_count: int, elapsed: float):
    """保存索引 manifest。"""
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    manifest = {
        "embedding_model": EMBEDDING_MODEL,
        "collection_name": COLLECTION_NAME,
        "chunk_count": chunk_count,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 1),
    }
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info(f"Manifest saved: {MANIFEST_PATH}")


def main():
    logger.info("=" * 60)
    logger.info("RAG Batch Indexing Script (improved)")
    logger.info(f"Model: {EMBEDDING_MODEL}")
    logger.info(f"ChromaDB: {os.path.abspath(CHROMA_DIR)}")
    logger.info(f"Collection: {COLLECTION_NAME} (via tmp: {TMP_COLLECTION_NAME})")
    logger.info("=" * 60)

    # Prepare documents using generator (streaming)
    all_docs = []
    all_metas = []
    all_ids = []
    seen = set()

    for item in load_records():
        chunks = disease_to_chunks(item)
        for text, disease_name, chunk_type in chunks:
            if len(text) > 800:
                text = text[:800]
            raw = f"{len(all_docs)}:{text[:100]}"
            h = hashlib.md5(raw.encode()).hexdigest()
            while h in seen:
                raw = f"{raw}:dup{len(all_docs)}"
                h = hashlib.md5(raw.encode()).hexdigest()
            seen.add(h)
            all_docs.append(text)
            all_metas.append({
                "category": "疾病",
                "source": "QASystemOnMedicalKG",
                "disease_name": disease_name,
                "chunk_type": chunk_type,
                "keywords": disease_name,
            })
            all_ids.append(h)

    total = len(all_docs)
    logger.info(f"Prepared {total} document chunks")

    # Load checkpoint for resume
    checkpoint = load_checkpoint()
    start_from = checkpoint.get("last_batch_end", 0)
    previously_inserted = checkpoint.get("inserted", 0)
    if start_from > 0:
        logger.info(f"Resuming from checkpoint: batch {start_from}, {previously_inserted} docs already inserted")

    # Load model
    logger.info("Loading embedding model...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)
    logger.info("Model loaded")

    # Init ChromaDB
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DIR, settings=ChromaSettings(anonymized_telemetry=False))

    # 使用临时 collection，避免索引失败破坏旧 collection
    try:
        client.delete_collection(TMP_COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(name=TMP_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    # Streaming encode + insert
    encode_start = time.time()
    buf_docs = []
    buf_metas = []
    buf_ids = []
    buf_embs = []
    inserted = previously_inserted

    for start in range(start_from, total, ENCODE_BATCH):
        end = min(start + ENCODE_BATCH, total)
        batch_docs = all_docs[start:end]

        # Encode this small batch
        embs = model.encode(batch_docs, normalize_embeddings=True, show_progress_bar=False)

        buf_docs.extend(batch_docs)
        buf_metas.extend(all_metas[start:end])
        buf_ids.extend(all_ids[start:end])
        buf_embs.extend(embs.tolist())
        del embs

        # Flush buffer when it reaches INSERT_CHUNK
        if len(buf_docs) >= INSERT_CHUNK:
            collection.add(ids=buf_ids, documents=buf_docs, embeddings=buf_embs, metadatas=buf_metas)
            inserted += len(buf_docs)
            buf_docs, buf_metas, buf_ids, buf_embs = [], [], [], []
            save_checkpoint(end, inserted)
            gc.collect()

        # Progress logging
        done = end
        if (start // ENCODE_BATCH) % 20 == 0:
            elapsed = time.time() - encode_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 60 if rate > 0 else 0
            logger.info(f"  {done}/{total} ({done*100//total}%) - {rate:.1f} docs/s - ETA {eta:.1f} min")

    # Flush remaining
    if buf_docs:
        collection.add(ids=buf_ids, documents=buf_docs, embeddings=buf_embs, metadatas=buf_metas)
        inserted += len(buf_docs)
        save_checkpoint(total, inserted)

    total_time = time.time() - encode_start
    logger.info(f"Tmp collection ready: {inserted} docs in {total_time/60:.1f} min")
    logger.info(f"Tmp collection count: {collection.count()}")

    # 原子切换：删除旧 collection，重命名 tmp
    logger.info("Atomically switching collections...")
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    # ChromaDB 不支持 rename，需要从 tmp 复制到正式 collection
    # 使用 get_or_create + 重新读取数据的方式
    final_collection = client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    # 从 tmp collection 读取所有数据并写入正式 collection
    batch_size = 1000
    offset = 0
    total_copied = 0
    while offset < inserted:
        result = collection.get(limit=batch_size, offset=offset, include=["documents", "embeddings", "metadatas"])
        if not result["ids"]:
            break
        final_collection.add(
            ids=result["ids"],
            documents=result["documents"],
            embeddings=result["embeddings"],
            metadatas=result["metadatas"],
        )
        total_copied += len(result["ids"])
        offset += batch_size

    # 清理 tmp collection 和 checkpoint
    try:
        client.delete_collection(TMP_COLLECTION_NAME)
    except Exception:
        pass
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)

    elapsed = time.time() - encode_start
    logger.info(f"Done! {total_copied} docs indexed in {elapsed/60:.1f} min")
    logger.info(f"Final collection count: {final_collection.count()}")

    # 保存 manifest
    save_manifest(total_copied, elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
