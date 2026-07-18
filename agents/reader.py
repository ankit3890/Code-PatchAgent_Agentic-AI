import logging

from langchain.chat_models import init_chat_model
from langchain_core.documents import Document

from config import settings
from prompts.planner.schema import Plan
from prompts.reader.compliance import COMPLIANCE_CHECK_PROMPT, ComplianceCheck
from prompts.reader.prompt import READER_PROMPT
from prompts.reader.schema import ReaderResult
from rag.retriever import CodeRetriever

logger = logging.getLogger(__name__)


class ReaderAgent:
    """
    Reader Agent.

    Responsibilities:
    - Retrieve relevant repository context
    - Analyze the retrieved code
    - Produce structured repository understanding

    Does NOT:
    - Write code
    - Modify files
    - Suggest implementations
    """

    def __init__(
        self,
        retriever: CodeRetriever,
        model: str = settings.model_name,
        model_provider: str = settings.model_provider,
    ):
        self.retriever = retriever

        self.llm = init_chat_model(
            model,
            model_provider=model_provider,
        ).with_structured_output(ReaderResult)

        self.compliance_llm = init_chat_model(
            model,
            model_provider=model_provider,
        ).with_structured_output(ComplianceCheck)

    def read(
        self,
        plan: Plan,
    ) -> tuple[ReaderResult, str]:

        documents = self._retrieve_documents(plan)

        if not documents:
            logger.warning("No relevant documents found.")

            return (
                ReaderResult(
                    repository_summary="No relevant repository context found.",
                    analysis="The retriever could not find code related to the requested task.",
                    relevant_files=[],
                ),
                "",
            )

        context = self._build_context(documents)

        return self._analyze_repository(plan, context), context

    def _retrieve_documents(
        self,
        plan: Plan,
    ) -> list[Document]:

        query = f"""
Goal:
{plan.goal}

Repository concepts:
{", ".join(plan.required_context)}
"""

        logger.info("Searching repository...")

        try:

            documents = self.retriever.search_mmr(
                query=query,
                k=settings.default_top_k,
                fetch_k=settings.default_fetch_k,
            )

        except Exception:
            logger.exception("Repository retrieval failed.")
            raise

        documents = self._unique_documents(documents)

        logger.info(
            "Retrieved %d unique chunks.",
            len(documents),
        )

        return documents

    def _analyze_repository(
        self,
        plan: Plan,
        context: str,
    ) -> ReaderResult:

        messages = [
            ("system", READER_PROMPT),
            (
                "user",
                f"""
User Goal:
{plan.goal}

Task Type:
{plan.task_type}

Repository Context:

{context}
""",
            ),
        ]

        try:
            result = self.llm.invoke(messages)
        except Exception:
            logger.exception("Reader analysis failed.")
            raise

        result = self._enforce_compliance(messages, result)

        return result

    def _enforce_compliance(
        self,
        messages: list[tuple[str, str]],
        result: ReaderResult,
    ) -> ReaderResult:

        for attempt in range(settings.max_compliance_retries + 1):

            check = self._check_compliance(result)

            if check.compliant:
                if attempt > 0:
                    logger.info(
                        "Reader output became compliant after %d retry(ies).",
                        attempt,
                    )
                return result

            logger.warning(
                "Reader output failed compliance check (attempt %d): %s",
                attempt + 1,
                check.violations,
            )

            if attempt >= settings.max_compliance_retries:
                logger.warning(
                    "Reader output still non-compliant after %d retry(ies). "
                    "Returning as-is: %s",
                    settings.max_compliance_retries,
                    check.violations,
                )
                return result

            retry_messages = messages + [
                (
                    "user",
                    "Your previous response contained implementation "
                    "suggestions or recommended changes, which are not "
                    "allowed. The following phrases were flagged:\n"
                    + "\n".join(f"- {v}" for v in check.violations)
                    + "\n\nRewrite your full response. Describe only the "
                    "current state of the repository. Do not suggest what "
                    "should be added, changed, or installed anywhere in "
                    "your output.",
                )
            ]

            try:
                result = self.llm.invoke(retry_messages)
            except Exception:
                logger.exception("Reader analysis retry failed.")
                raise

        return result

    def _check_compliance(
        self,
        result: ReaderResult,
    ) -> ComplianceCheck:

        messages = [
            ("system", COMPLIANCE_CHECK_PROMPT),
            ("user", result.model_dump_json(indent=2)),
        ]

        try:
            return self.compliance_llm.invoke(messages)
        except Exception:
            logger.exception("Compliance check failed; assuming compliant.")
            return ComplianceCheck(compliant=True, violations=[])

    @staticmethod
    def _unique_documents(
        documents: list[Document],
    ) -> list[Document]:

        seen = set()
        unique = []

        for doc in documents:

            key = (
                doc.metadata.get("path"),
                doc.metadata.get("chunk_index"),
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(doc)

        return unique

    @staticmethod
    def _build_context(
        documents: list[Document],
    ) -> str:

        selected: list[tuple[Document, str]] = []
        current_size = 0

        for doc in documents:

            path = doc.metadata.get("path", "Unknown")
            extension = doc.metadata.get("extension", "")
            chunk = doc.metadata.get("chunk_index", 0)

            section = f"""
==================================================
FILE: {path}
EXTENSION: {extension}
CHUNK: {chunk}
==================================================

{doc.page_content}

"""

            if current_size + len(section) > settings.max_context_chars:
                logger.info(
                    "Context truncated: kept %d/%d chunks (%d/%d characters).",
                    len(selected),
                    len(documents),
                    current_size,
                    settings.max_context_chars,
                )
                break

            selected.append((doc, section))
            current_size += len(section)

        else:
            logger.info(
                "Context built with %d chunks (%d characters).",
                len(selected),
                current_size,
            )

        selected.sort(
            key=lambda ds: (
                ds[0].metadata.get("path", ""),
                ds[0].metadata.get("chunk_index", 0),
            )
        )

        return "\n".join(section for _, section in selected)