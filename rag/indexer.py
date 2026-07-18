import logging
from pathlib import Path

from git_utils.clone_repo import RepoManager
from rag.loader import RepositoryLoader
from rag.manifest import diff_manifest, hash_content, load_manifest, save_manifest
from rag.splitter import CodeSplitter
from rag.vector_store import CodeVectorStore

from config import settings


logger = logging.getLogger(__name__)


class RepositoryIndexer:

    def __init__(
        self,
        repo_url: str,
        collection_name: str,
        persist_directory: str = settings.persist_directory,
    ):
        self.repo_url = repo_url
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.manifest_path = (
            Path(persist_directory) / f"{collection_name}_manifest.json"
        )

    def index(self, force: bool = False) -> CodeVectorStore:
        repo = RepoManager()
        repo_path = repo.clone_or_update(self.repo_url)

        vector_store = CodeVectorStore(
            persist_directory=self.persist_directory,
            collection_name=self.collection_name,
        )

        if force:
            logger.info("Force reindex requested: clearing collection and manifest.")
            vector_store.delete_collection()
            manifest = {}
        else:
            manifest = load_manifest(self.manifest_path)

        logger.info("Loading repository...")
        loader = RepositoryLoader(repo_path)
        documents = loader.load()
        logger.info("Loaded %d files", len(documents))

        current_hashes = {
            doc.metadata["path"]: hash_content(doc.page_content) for doc in documents
        }
        changed_or_new, deleted, unchanged_count = diff_manifest(
            manifest, current_hashes
        )

        logger.info(
            "%d new/changed, %d deleted, %d unchanged",
            len(changed_or_new),
            len(deleted),
            unchanged_count,
        )

        if not changed_or_new and not deleted:
            logger.info("Collection '%s' already up to date.", self.collection_name)
            return vector_store

        for path in deleted:
            vector_store.delete_by_path(path)

        splitter = CodeSplitter()
        changed_docs = [
            doc for doc in documents if doc.metadata["path"] in changed_or_new
        ]

        chunks = []
        for document in changed_docs:
            # Clear old chunks for this path first so a shrinking file
            # doesn't leave stale leftover chunks behind.
            vector_store.delete_by_path(document.metadata["path"])
            chunks.extend(splitter.split_document(document))

        logger.info("Created %d chunks", len(chunks))

        if chunks:
            vector_store.add_documents(chunks)

        save_manifest(self.manifest_path, current_hashes)

        logger.info(
            "Repository indexed. %d chunks total.",
            vector_store.get_collection_count(),
        )

        return vector_store