from typing import Optional

from langchain_core.documents import Document

from rag.vector_store import CodeVectorStore

from config import settings

class CodeRetriever:
    """
    High-level interface for retrieving relevant code chunks.

    This class wraps CodeVectorStore and provides different retrieval
    strategies for the agents.
    """

    def __init__(
        self,
        vector_store: Optional[CodeVectorStore] = None,
        persist_directory: str | None = None,
        collection_name: str = "default",
    ):
        persist_directory = persist_directory or settings.persist_directory
        """
        Args:
            vector_store:
                Existing CodeVectorStore instance.

            persist_directory:
                Used only when vector_store is None.

            collection_name:
                Repository collection to search.
        """

        self.vector_store = vector_store or CodeVectorStore(
            persist_directory=persist_directory,
            collection_name=collection_name,
        )

    def search(
        self,
        query: str,
        k: int = settings.default_top_k,
        filter: Optional[dict] = None,
    ) -> list[Document]:
        """
        Standard semantic similarity search.
        """

        return self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=filter,
        )

    def search_mmr(
        self,
        query: str,
        k: int = settings.default_top_k,
        fetch_k: int = settings.default_fetch_k,
        filter: Optional[dict] = None,
    ) -> list[Document]:
        """
        Max Marginal Relevance search.

        Returns diverse results instead of multiple nearly identical chunks.
        """

        return self.vector_store.max_marginal_relevance_search(
            query=query,
            k=k,
            fetch_k=fetch_k,
            filter=filter,
        )

    def search_with_scores(
        self,
        query: str,
        k: int = settings.default_top_k,
        filter: Optional[dict] = None,
    ) -> list[tuple[Document, float]]:
        """
        Returns:
            [
                (Document, score),
                ...
            ]

        Lower score = better match.
        """

        return self.vector_store.similarity_search_with_score(
            query=query,
            k=k,
            filter=filter,
        )

    def search_with_threshold(
        self,
        query: str,
        threshold: float = settings.default_score_threshold,
        k: int = settings.default_top_k,
        filter: Optional[dict] = None,
    ) -> list[Document]:
        """
        Filters out weak matches using similarity score.
        """

        results = self.search_with_scores(
            query=query,
            k=k,
            filter=filter,
        )

        return [
            doc
            for doc, score in results
            if score <= threshold
        ]

    def search_python(
        self,
        query: str,
        k: int = settings.default_top_k,
    ) -> list[Document]:
        """
        Convenience method for searching only Python files.
        """

        return self.search(
            query=query,
            k=k,
            filter={"extension": ".py"},
        )

    def search_java(
        self,
        query: str,
        k: int = settings.default_top_k,
    ) -> list[Document]:
        """
        Convenience method for searching only Java files.
        """

        return self.search(
            query=query,
            k=k,
            filter={"extension": ".java"},
        )

    def as_retriever(
        self,
        search_type: str = "mmr",
        k: int = settings.default_top_k,
        fetch_k: int = settings.default_fetch_k,
    ):
        """
        Returns a LangChain Retriever.

        Useful for:
        - LangGraph
        - RetrievalQA
        - Agents
        """

        kwargs = {"k": k}

        if search_type == "mmr":
            kwargs["fetch_k"] = fetch_k

        return self.vector_store.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=kwargs,
        )