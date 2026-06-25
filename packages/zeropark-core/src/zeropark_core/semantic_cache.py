import os
import uuid
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

class SemanticCache:
    """Qdrant-based Semantic Cache for LLM responses."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticCache, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            
            qdrant_url = os.getenv("QDRANT_URL")
            if qdrant_url:
                self.client = QdrantClient(url=qdrant_url)
            else:
                self.client = QdrantClient(location=":memory:")
                
            self.collection_name = "semantic_cache"
            self.dim = None
        except ImportError:
            self.client = None
            logger.warning("qdrant-client is not installed. Semantic Cache disabled.")

    def _ensure_collection(self, dim: int):
        if not self.client or self.dim is not None:
            return
        self.dim = dim
        from qdrant_client.models import Distance, VectorParams
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def similarity_search(self, query_emb: List[float], threshold: float = 0.95) -> Optional[str]:
        if not self.client:
            return None
            
        self._ensure_collection(len(query_emb))
        try:
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_emb,
                limit=1
            )
            hits = search_result.points
            if hits and hits[0].score >= threshold:
                return hits[0].payload.get("answer")
        except Exception as e:
            logger.error(f"Semantic Cache search failed: {e}")
        return None

    def set_cache(self, query_emb: List[float], answer: str):
        if not self.client:
            return
            
        self._ensure_collection(len(query_emb))
        try:
            from qdrant_client.models import PointStruct
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=query_emb,
                        payload={"answer": answer}
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Semantic Cache set failed: {e}")

semantic_cache = SemanticCache()
