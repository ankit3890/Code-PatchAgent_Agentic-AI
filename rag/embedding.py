import logging

from langchain_mistralai import MistralAIEmbeddings

from config import settings

logger = logging.getLogger(__name__)


class EmbeddingModel:
    """
    Wraps the Mistral embedding model for use in the RAG pipeline.
    """

    def __init__(
        self,
        model: str = settings.embedding_model_name,
    ):

        logger.info(
            "Loading Mistral embedding model '%s'",
            model,
        )

        self.embedding = MistralAIEmbeddings(
            model=model,
        )

    def get_embedding_model(self):
        return self.embedding