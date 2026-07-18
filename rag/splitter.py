from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_core.documents import Document
from config import settings


EXTENSION_LANGUAGE_MAP = {
    ".py": Language.PYTHON,
    ".java": Language.JAVA,
    ".js": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".jsx": Language.JS,
    ".cpp": Language.CPP,
    ".c": Language.C,
    ".h": Language.C,
    ".hpp": Language.CPP,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".kt": Language.KOTLIN,
    ".swift": Language.SWIFT,
    ".php": Language.PHP,
    ".rb": Language.RUBY,
    ".cs": Language.CSHARP,
    ".html": Language.HTML,
    ".md": Language.MARKDOWN,
}


class CodeSplitter:
    def __init__(self, chunk_size: int = settings.chunk_size, overlap: int = settings.chunk_overlap):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._splitters = {}
        self._default_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    def _get_splitter(self, extension: str) -> RecursiveCharacterTextSplitter:
        extension = extension.lower()

        if extension in self._splitters:
            return self._splitters[extension]

        language = EXTENSION_LANGUAGE_MAP.get(extension)

        if language:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language,
                chunk_size=self.chunk_size,
                chunk_overlap=self.overlap,
            )
        else:
            splitter = self._default_splitter

        self._splitters[extension] = splitter
        return splitter

    def split_document(self, document: Document) -> list[Document]:
        """
        Splits a code Document into smaller chunk Documents, using
        language-aware separators when the file extension (from
        document.metadata["extension"]) is recognized. Falls back
        to generic text splitting if unrecognized or missing.

        Args:
            document: A LangChain Document whose page_content is the
                code/text to split, and whose metadata should include
                an "extension" key (e.g. ".py").

        Returns:
            List of chunked Documents, each carrying a copy of the
            original metadata plus chunk_index/chunk_count.
        """
        extension = document.metadata.get("extension", "")
        splitter = self._get_splitter(extension)

        chunks = splitter.split_text(document.page_content)

        return [
            Document(
                page_content=chunk,
                metadata={
                    **document.metadata,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                },
            )
            for i, chunk in enumerate(chunks)
        ]