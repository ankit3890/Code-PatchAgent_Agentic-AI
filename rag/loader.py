import logging
from pathlib import Path

from langchain_core.documents import Document
from config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".cpp", ".c", ".h", ".hpp",
    ".go", ".rs", ".kt", ".swift", ".php", ".rb", ".cs", ".html", ".css",
    ".scss", ".json", ".yaml", ".yml", ".toml", ".md",
}

IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", "dist", "build",
    ".idea", ".vscode", ".pytest_cache", "target",
}


class RepositoryLoader:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def load(self) -> list[Document]:
        """
        Walk the repository and load supported source files into
        LangChain Documents.

        Returns:
            List of Documents, each with:
                page_content: file contents
                metadata: {"path": relative path, "extension": suffix}
        """
        documents: list[Document] = []

        for file_path in self.repo_path.rglob("*"):
            if file_path.is_dir():
                continue

            # Skip symlinks (files or dirs) to avoid duplicate content
            # or infinite loops from links pointing back into the tree.
            if file_path.is_symlink():
                logger.debug("Skipping symlink %s", file_path)
                continue

            relative_parts = file_path.relative_to(self.repo_path).parts
            if any(part in IGNORE_DIRS for part in relative_parts):
                continue

            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            try:
                if file_path.stat().st_size > settings.max_file_size_bytes:
                    logger.warning("Skipping %s: exceeds size limit", file_path)
                    continue

                content = file_path.read_text(encoding="utf-8", errors="ignore")

                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "path": str(file_path.relative_to(self.repo_path)),
                            "extension": file_path.suffix,
                        },
                    )
                )

            except OSError as e:
                logger.warning("Could not read %s: %s", file_path, e)

        return documents