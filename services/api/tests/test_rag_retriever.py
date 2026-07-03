"""Unit tests for the structured RAG retrieval contract."""

from app.services import rag_retriever


class FakeEmbeddingFunction:
    def encode_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


class FakeCollection:
    def count(self) -> int:
        return 2

    def query(self, **kwargs):
        assert kwargs["query_embeddings"] == [[1.0, 0.0]]
        return {
            "documents": [["高血压应定期监测血压", "普通健康知识"]],
            "metadatas": [[
                {"category": "慢病", "source": "测试知识库"},
                {"category": "常识", "source": "测试知识库"},
            ]],
            "distances": [[0.1, 0.8]],
            "embeddings": [[[1.0, 0.0], [0.0, 1.0]]],
        }


def test_search_documents_returns_structured_results(monkeypatch):
    monkeypatch.setattr(rag_retriever, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(rag_retriever, "_get_embedding_function", lambda: FakeEmbeddingFunction())
    monkeypatch.setattr(rag_retriever, "_get_reranker", lambda: None)

    results = rag_retriever.search_documents(
        "高血压",
        top_k=5,
        score_threshold=0.35,
        use_mmr=False,
    )

    assert results == [{
        "content": "高血压应定期监测血压",
        "metadata": {"category": "慢病", "source": "测试知识库"},
        "score": 0.9,
    }]


def test_retrieve_keeps_llm_context_format(monkeypatch):
    monkeypatch.setattr(
        rag_retriever,
        "search_documents",
        lambda *args, **kwargs: [{
            "content": "高血压应定期监测血压",
            "metadata": {"category": "慢病", "source": "测试知识库"},
            "score": 0.9,
        }],
    )

    context = rag_retriever.retrieve("高血压")

    assert context == "[慢病] (测试知识库) (相似度:0.9) 高血压应定期监测血压"
