from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

#---------------------------------------------------------------------------
    # LLM Configuration

    # Default chat model used by all agents.
    model_name: str = "mistral-small-latest"
    model_provider: str = "mistralai"

#---------------------------------------------------------------------------
    # Embedding Configuration
    # Model used to generate vector embeddings for repository code.
    embedding_model_name: str = "mistral-embed"

#---------------------------------------------------------------------------
    # Code Chunking

    # Maximum characters per chunk before splitting.
    chunk_size: int = 1000

    # Number of overlapping characters between adjacent chunks.
    chunk_overlap: int = 200

#---------------------------------------------------------------------------
    # Vector Database
    # Directory where Chroma stores its database.
    persist_directory: str = "vector_db"

    # Local directory where cloned repositories are stored.
    repos_dir: str = "repos"

    # Number of documents inserted into Chroma per batch.
    default_batch_size: int = 100

#---------------------------------------------------------------------------
    # Repository Loader
    # Ignore files larger than this size (2 MB).
    max_file_size_bytes: int = 2 * 1024 * 1024

#---------------------------------------------------------------------------
    # Retrieval
    # Number of documents returned by a standard similarity search.
    default_top_k: int = 5

    # Number of candidates fetched before applying MMR.
    default_fetch_k: int = 20

    # Minimum similarity score required for a result to be returned.
    default_score_threshold: float = 0.5

#---------------------------------------------------------------------------
    # Redeader Agent
    max_context_chars: int = 30000
    max_compliance_retries: int = 1

#---------------------------------------------------------------------------
    # Writer Agent
    max_writer_retries: int = 1

#---------------------------------------------------------------------------
    # Reviewer Agent
    max_review_cycles: int = 4 
    max_reviewer_retries: int = 1

#---------------------------------------------------------------------------
    # Pydantic Settings
    model_config = SettingsConfigDict(
        # Load configuration from the project's .env file.
        env_file=".env",

        # Ignore environment variables that are not defined
        # in this Settings class.
        extra="ignore",
    )


#---------------------------------------------------------------------------
# Shared application settings instance.
settings = Settings()