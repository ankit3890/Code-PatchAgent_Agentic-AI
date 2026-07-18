import hashlib
import logging
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.embedding import EmbeddingModel

from config import settings


logger = logging.getLogger(__name__)


def _make_id(document: Document) -> str:
    """
    Build a stable, deterministic ID for a chunk so re-indexing the
    same file/chunk overwrites the previous entry instead of
    duplicating it.
    """
    path = document.metadata.get("path", "")
    chunk_index = document.metadata.get("chunk_index", 0)
    key = f"{path}::{chunk_index}"
    # Hash to keep IDs a predictable length/charset regardless of path content.
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class CodeVectorStore:
    """
    Handles indexing and retrieval of code documents using ChromaDB.
    """

    def __init__(
        self,
        persist_directory: str = settings.persist_directory,
        collection_name: str = "default",
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        self.embedding_model = EmbeddingModel().get_embedding_model()

        self.vector_store = self._new_vector_store()

    def _new_vector_store(self) -> Chroma:
        return Chroma(
            persist_directory=self.persist_directory,
            collection_name=self.collection_name,
            embedding_function=self.embedding_model,
        )

    def add_documents(
        self,
        documents: list[Document],
        batch_size: int = settings.default_batch_size,
    ):
        """
        Add documents to Chroma, batching to avoid overly large single
        calls and using stable IDs so re-indexing the same file/chunk
        overwrites rather than duplicates.
        """
        if not documents:
            logger.info("No documents to add, skipping.")
            return

        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            ids = [_make_id(doc) for doc in batch]
            self.vector_store.add_documents(batch, ids=ids)
            logger.info(
                "Indexed batch %d-%d of %d documents",
                start,
                start + len(batch),
                len(documents),
            )

    def similarity_search(
        self,
        query: str,
        k: int = settings.default_top_k,
        filter: dict | None = None,
    ) -> list[Document]:
        """
        Retrieve the top-k most relevant documents.

        Args:
            filter: Optional Chroma metadata filter, e.g.
                {"extension": ".py"}.
        """
        return self.vector_store.similarity_search(query, k=k, filter=filter)

    def max_marginal_relevance_search(
        self,
        query: str,
        k: int = settings.default_top_k,
        fetch_k: int = settings.default_fetch_k,
        filter: dict | None = None,
    ) -> list[Document]:
        """
        Max Marginal Relevance search for more diverse top-k results.
        """
        return self.vector_store.max_marginal_relevance_search(
            query, k=k, fetch_k=fetch_k, filter=filter
        )

    def similarity_search_with_score(
        self,
        query: str,
        k: int = settings.default_top_k,
        filter: dict | None = None,
    ):
        """
        Retrieve top-k documents paired with similarity scores.
        Lower score = more similar.
        """
        return self.vector_store.similarity_search_with_score(
            query, k=k, filter=filter
        )

    def delete_collection(self):
        """
        Delete all indexed documents and reinitialize the underlying
        collection so this instance remains usable afterward.
        """
        self.vector_store.delete_collection()
        self.vector_store = self._new_vector_store()

    def get_collection_count(self) -> int:
        """
        Number of chunks currently indexed in this collection.
        """
        # `_collection` is a private attribute of langchain_chroma's Chroma
        # wrapper; fall back to counting returned ids if it's ever removed.
        try:
            return self.vector_store._collection.count()
        except AttributeError:
            return len(self.vector_store.get()["ids"])

    def as_retriever(
        self,
        search_type: str = "mmr",
        k: int = settings.default_top_k,
        fetch_k: int = settings.default_fetch_k,
    ):
        """
        Returns a LangChain Retriever backed by this collection.
        Useful for LangGraph, RetrievalQA, or agent tool wiring.
        """
        kwargs = {"k": k}
        if search_type == "mmr":
            kwargs["fetch_k"] = fetch_k

        return self.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=kwargs,
        )
    
    def delete_by_path(self, path: str):
        """
        Delete all chunks belonging to a specific file.
        """

        self.vector_store.delete(
            where={"path": path}
        )