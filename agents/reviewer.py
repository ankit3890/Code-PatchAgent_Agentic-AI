import logging
from pathlib import Path

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from config import settings
from prompts.planner.schema import Plan
from prompts.reader.schema import ReaderResult
from prompts.reviewer.prompt import REVIEWER_PROMPT
from prompts.reviewer.schema import (
    ReviewChecklist,
    ReviewIssue,
    ReviewLLMOutput,
    ReviewResult,
    ReviewState,
)
from prompts.writer.schema import WriterResult
from reviewer.static_validator import (
    StaticValidationError,
    StaticValidator,
)

logger = logging.getLogger(__name__)


class ReviewerAgent:
    """
    Reviewer Agent.

    Responsibilities
    ----------------
    1. Run deterministic validation.
    2. Review Writer output.
    3. Approve or reject.
    """

    def __init__(
        self,
        repo_root: Path,
        model: str = settings.model_name,
        model_provider: str = settings.model_provider,
    ):
        self.validator = StaticValidator(repo_root)

        #
        # LLM returns only ReviewLLMOutput.
        #

        self.llm = (
            init_chat_model(
                model,
                model_provider=model_provider,
            )
            .with_structured_output(
                ReviewLLMOutput,
            )
        )

    def review(
        self,
        plan: Plan,
        reader_result: ReaderResult,
        writer_result: WriterResult,
        review_state: ReviewState | None = None,
    ) -> ReviewResult:

        #
        # Tier 1
        # Deterministic validation
        #

        try:
            self.validator.validate(writer_result)

        except StaticValidationError as e:

            logger.warning(
                "Static validation failed."
            )

            return ReviewResult(
                    score=0.0,
                    summary="Static validation failed.",
                    checklist=ReviewChecklist(
                        user_request_satisfied=False,
                        execution_plan_satisfied=False,
                        implementation_complete=False,
                        summary_matches_patch=True,
                        no_security_regressions=False,
                    ),
                    issues=[
                        ReviewIssue(
                            severity="critical",
                            file=issue.file,
                            message=issue.message,
                            recommendation="Fix deterministic validation errors.",
                        )
                        for issue in e.issues
                    ],
                    approved=False,
                    next_agent="writer",
                )
        #
        # Tier 2
        #

        messages = [
            (
                "system",
                REVIEWER_PROMPT,
            ),
            (
                "user",
                f"""
User Goal

{plan.goal}

Execution Plan

{plan.model_dump_json(indent=2)}

Repository Analysis

{reader_result.model_dump_json(indent=2)}

Previous Review State

{review_state.model_dump_json(indent=2) if review_state else "None"}

Writer Output

{writer_result.model_dump_json(indent=2)}
""",
            ),
        ]

        return self._invoke_with_retry(messages)
    
    def _invoke_with_retry(
        self,
        messages: list[tuple[str, str]],
    ) -> ReviewResult:
        """
        Invoke the Reviewer LLM with retries.

        Workflow

        LLM
            ↓
        ReviewLLMOutput
            ↓
        dict
            ↓
        normalize()
            ↓
        ReviewResult
        """

        last_error: Exception | None = None

        max_attempts = (
            settings.max_reviewer_retries + 1
        )

        for attempt in range(max_attempts):

            retry_messages = messages

            if last_error is not None:

                retry_messages = messages + [
                    (
                        "user",
                        f"""
    Your previous review failed validation.

    Validation errors

    {last_error}

    Revise your previous review.

    Preserve all correct analysis.

    Only fix the reported validation problems.

    Do not invent new issues.

    Do not remove valid issues.

    Do not change the summary unless necessary.

    Requirements

    - Return valid structured output.
    - Every Critical or Major issue MUST specify a file.
    - Do NOT return approved.
    - Do NOT return next_agent.
    - Ensure the checklist is internally consistent.
    """,
                    )
                ]

            try:

                #
                # LLM output
                #

                review: ReviewLLMOutput = self.llm.invoke(
                    retry_messages
                )

                #
                # Convert to dict
                #

                data = review.model_dump()

                #
                # Normalize deterministic fields
                #

                data = self._normalize_result(data)

                #
                # Runtime model
                #

                result = ReviewResult(
                    **data
                )

                logger.info(
                    "Reviewer succeeded on attempt %d.",
                    attempt + 1,
                )

                return result

            except ValidationError as e:

                last_error = e

                logger.warning(
                    "Reviewer output failed validation "
                    "(attempt %d): %s",
                    attempt + 1,
                    e,
                )

            except Exception as e:

                last_error = e

                logger.exception(
                    "Reviewer invocation failed "
                    "(attempt %d).",
                    attempt + 1,
                )

        logger.error(
            "Reviewer failed after %d attempts.",
            max_attempts,
        )

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "Reviewer failed without returning an error."
        )

    @staticmethod
    def _normalize_result(
        data: dict,
    ) -> dict:
        """
        Normalize deterministic fields before constructing
        ReviewResult.

        The LLM is responsible for:
        - score
        - summary
        - checklist
        - issues

        Python is responsible for:
        - approved
        - next_agent
        - checklist consistency
        """

        issues = data.get("issues", [])
        checklist = data.get("checklist", {})

        #
        # Any critical/major issue blocks approval.
        #

        blocking = any(
            issue.get("severity") in {"critical", "major"}
            for issue in issues
        )

        #
        # Keep checklist internally consistent.
        #

        if blocking:
            checklist["user_request_satisfied"] = False
            checklist["execution_plan_satisfied"] = False
            checklist["implementation_complete"] = False

        #
        # Compute runtime-only fields.
        #

        approved = not blocking

        data["approved"] = approved
        data["next_agent"] = (
            "done"
            if approved
            else "writer"
        )

        data["checklist"] = checklist

        return data