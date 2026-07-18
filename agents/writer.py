import logging

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from config import settings
from prompts.planner.schema import Plan
from prompts.reader.schema import ReaderResult
from prompts.reviewer.schema import ReviewResult
from prompts.writer.prompt import WRITER_PROMPT
from prompts.writer.schema import WriterResult

logger = logging.getLogger(__name__)


class WriterAgent:
    """
    Writer Agent.

    Responsibilities
    ----------------
    - Generate the initial implementation.
    - Revise an existing implementation.
    - Preserve previous valid edits.
    - Produce deterministic structured output.
    """

    def __init__(
        self,
        model: str = settings.model_name,
        model_provider: str = settings.model_provider,
    ):
        self.llm = (
            init_chat_model(
                model,
                model_provider=model_provider,
            )
            .with_structured_output(
                WriterResult
            )
        )

    def write(
        self,
        plan: Plan,
        reader_result: ReaderResult,
        repository_context: str,
    ) -> WriterResult:
        """
        Generate the first implementation.
        """

        messages = [
            (
                "system",
                WRITER_PROMPT,
            ),
            (
                "user",
                f"""
User Goal

{plan.goal}

Task Type

{plan.task_type}

Execution Plan

{plan.model_dump_json(indent=2)}

Repository Analysis

{reader_result.model_dump_json(indent=2)}

Repository Context

{repository_context}

Instructions

Generate the COMPLETE implementation.

Requirements

- Modify only files that actually need changes.
- Every repository file appears at most once.
- Do not invent repository files.
- Do not omit required edits.
- Produce the complete patch.
- Summary must accurately describe the implementation.
""",
            ),
        ]

        return self._invoke_with_retry(messages)
    
    def revise(
        self,
        plan: Plan,
        reader_result: ReaderResult,
        repository_context: str,
        previous_result: WriterResult,
        review_feedback: ReviewResult,
    ) -> WriterResult:  
        """
        Revise an existing implementation.

        Unlike write(), this method starts from the previous patch
        instead of regenerating everything.
        """

        previous_patch = self._format_previous_patch(
            previous_result
        )

        reviewer_feedback = self._format_review_feedback(
            review_feedback
        )

        messages = [
            (
                "system",
                WRITER_PROMPT,
            ),
            (
                "user",
                f"""
User Goal

{plan.goal}

Task Type

{plan.task_type}

Execution Plan

{plan.model_dump_json(indent=2)}

Repository Analysis

{reader_result.model_dump_json(indent=2)}

Repository Context

{repository_context}

=========================================================
CURRENT PATCH
=========================================================

{previous_patch}

=========================================================
REVIEWER FEEDBACK
=========================================================

{reviewer_feedback}

=========================================================
REVISION RULES
=========================================================

The patch above is your CURRENT working draft.

It already contains many correct edits.

Do NOT regenerate the implementation.

Instead:

1. Preserve every edit that was NOT rejected.

2. Modify ONLY the edits required to fix reviewer feedback.

3. Do not remove correct work.

4. Do not introduce unrelated changes.

5. Return the COMPLETE revised patch.

6. Every repository file must appear exactly once.

7. Keep the same intent unless reviewer feedback requires
changing it.

8. Summary MUST accurately describe the revised patch.

9. Never claim functionality that is not implemented.

10. If multiple edits modify the same file,
later edits must use old_code matching the file
AFTER previous edits have been applied.

=========================================================
OUTPUT
=========================================================

Return a COMPLETE WriterResult.
""",
            ),
        ]

        return self._invoke_with_retry(messages)
    

    def _invoke_with_retry(
        self,
        messages: list[tuple[str, str]],
    ) -> WriterResult:
        """
        Invoke the Writer LLM.

        Retries on both:
        - Pydantic schema validation errors
        - Semantic validation errors
        """

        last_error: str | None = None

        max_attempts = settings.max_writer_retries + 1

        for attempt in range(max_attempts):

            retry_messages = list(messages)

            if last_error is not None:

                retry_messages.append(
                    (
                        "user",
                        f"""
Your previous response failed validation.

Validation errors

{last_error}

Revise your previous response.

Do NOT regenerate unrelated files.

Preserve every valid edit.

Only modify edits necessary to satisfy the validation errors.

Requirements

- Every repository file appears exactly once.
- Modify actions contain one or more edits.
- Create actions contain complete file contents.
- Delete actions contain neither code nor edits.
- old_code must match the file after previous edits
  in the SAME patch.
- old_code and new_code must differ.
- Summary must accurately describe the patch.

Return ONLY valid WriterResult.
""",
                    )
                )

            try:

                result: WriterResult = self.llm.invoke(
                    retry_messages
                )

            except ValidationError as e:

                #
                # Structured output invalid
                #

                last_error = str(e)

                logger.warning(
                    "Writer schema validation failed "
                    "(attempt %d/%d)\n%s",
                    attempt + 1,
                    max_attempts,
                    e,
                )

                continue

            except Exception:

                logger.exception(
                    "Writer invocation failed."
                )

                raise

            #
            # Semantic validation
            #

            semantic_errors = self._validate_result(
                result
            )

            if semantic_errors:

                last_error = "\n".join(
                    f"- {err}"
                    for err in semantic_errors
                )

                logger.warning(
                    "Writer semantic validation failed "
                    "(attempt %d/%d)\n%s",
                    attempt + 1,
                    max_attempts,
                    last_error,
                )

                continue

            logger.info(
                "Writer succeeded on attempt %d "
                "with %d file(s).",
                attempt + 1,
                len(result.changes),
            )

            return result

        logger.error(
            "Writer failed after %d attempts.",
            max_attempts,
        )

        raise RuntimeError(
            f"""
Writer failed after {max_attempts} attempts.

Last validation errors

{last_error}
"""
        )
    

    @staticmethod
    def _format_previous_patch(
        result: WriterResult,
    ) -> str:
        """
        Format the previous WriterResult into readable text
        for the LLM.
        """

        sections: list[str] = []

        for change in result.changes:

            lines = [
                f"File: {change.path}",
                f"Action: {change.action}",
            ]

            if hasattr(change, "explanation") and change.explanation:
                lines.append(
                    f"Explanation: {change.explanation}"
                )

            code = (change.code or "").strip()

            if code:
                lines.extend(
                    [
                        "",
                        "FILE CONTENT",
                        code,
                    ]
                )

            for i, edit in enumerate(change.edits, start=1):

                lines.extend(
                    [
                        "",
                        f"Edit #{i}",
                        "",
                        "OLD CODE",
                        edit.old_code,
                        "",
                        "NEW CODE",
                        edit.new_code,
                    ]
                )

            sections.append("\n".join(lines))

        return "\n\n".join(sections)


    @staticmethod
    def _format_review_feedback(
        review: ReviewResult,
    ) -> str:
        """
        Format blocking reviewer issues for the Writer.
        """

        lines = [
            f"Summary: {review.summary}",
            "",
            "Blocking Issues",
            "----------------",
        ]

        blocking = [
            issue
            for issue in review.issues
            if issue.severity in {"critical", "major"}
        ]

        if not blocking:
            lines.append("None")
            return "\n".join(lines)

        for issue in blocking:

            lines.extend(
                [
                    "",
                    f"[{issue.severity.upper()}]",
                    f"File: {issue.file}",
                    "",
                    "Problem:",
                    issue.message,
                    "",
                    "Recommendation:",
                    issue.recommendation,
                ]
            )

        return "\n".join(lines)
    @staticmethod
    def _validate_result(
        result: WriterResult,
    ) -> list[str]:
        """
        Perform semantic validation that cannot be enforced
        by Pydantic alone.
        """

        errors: list[str] = []

        seen_paths: set[str] = set()

        for change in result.changes:

            path = change.path

            #
            # Duplicate file entries
            #

            if path in seen_paths:
                errors.append(
                    f"Duplicate file path: {path}"
                )

            seen_paths.add(path)

            code = (change.code or "").strip()

            #
            # Delete
            #

            if change.action == "delete":

                if code:
                    errors.append(
                        f"{path}: delete action must not contain code."
                    )

                if change.edits:
                    errors.append(
                        f"{path}: delete action must not contain edits."
                    )

                continue

            #
            # Create
            #

            if change.action == "create":

                if not code:
                    errors.append(
                        f"{path}: create action requires complete file contents."
                    )

                if change.edits:
                    errors.append(
                        f"{path}: create action must not contain edits."
                    )

                continue

            #
            # Modify
            #

            if change.action == "modify":

                if code:
                    errors.append(
                        f"{path}: modify action must not contain full file contents."
                    )

                if not change.edits:
                    errors.append(
                        f"{path}: modify action requires at least one edit."
                    )
                    continue

                for i, edit in enumerate(change.edits, start=1):

                    old_code = (edit.old_code or "").strip()
                    new_code = (edit.new_code or "").strip()

                    if not old_code:
                        errors.append(
                            f"{path}: edit #{i} has empty old_code."
                        )

                    if not new_code:
                        errors.append(
                            f"{path}: edit #{i} has empty new_code."
                        )

                    if old_code and new_code and old_code == new_code:
                        errors.append(
                            f"{path}: edit #{i} old_code and new_code are identical."
                        )

            #
            # Unknown action
            #

            else:
                errors.append(
                    f"{path}: unknown action '{change.action}'."
                )

        #
        # Response-level validation
        #

        summary = (result.summary or "").strip()

        if not summary:
            errors.append(
                "Summary cannot be empty."
            )

        if not result.changes:
            errors.append(
                "Writer produced no file changes."
            )

        return errors