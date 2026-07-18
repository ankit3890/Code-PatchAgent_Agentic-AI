from dataclasses import dataclass
from pathlib import Path

import re

from reviewer.syntax import SyntaxChecker
from prompts.writer.schema import FileChange, WriterResult


@dataclass
class StaticIssue:
    file: str
    message: str


class StaticValidationError(Exception):
    """Raised when deterministic validation fails."""

    def __init__(self, issues: list[StaticIssue]):
        self.issues = issues
        super().__init__(
            "\n\n".join(f"{i.file}: {i.message}" for i in issues)
        )


class StaticValidator:
    """
    Performs deterministic validation of Writer output.

    Responsibilities:
    - Validate create / modify / delete operations
    - Ensure files exist (or don't)
    - Apply edits to an in-memory copy
    - Validate resulting syntax

    Notes
    -----
    Edits are applied sequentially.

    Each edit operates on the result of all previous edits in the same file,
    matching how a real patch would be applied. This means an earlier edit may
    intentionally modify or remove code that later edits would otherwise match.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.syntax = SyntaxChecker()

    def validate(
        self,
        writer_result: WriterResult,
    ) -> None:

        issues: list[StaticIssue] = []

        for change in writer_result.changes:
            issues.extend(self._validate_change(change))

        if issues:
            raise StaticValidationError(issues)

    def _validate_change(self, change: FileChange) -> list[StaticIssue]:

        if change.action == "modify":
            return self._validate_modify(change)

        if change.action == "create":
            return self._validate_create(change)

        if change.action == "delete":
            return self._validate_delete(change)

        return []

    def _validate_modify(self, change: FileChange) -> list[StaticIssue]:

        issues: list[StaticIssue] = []

        file_path = self.repo_root / change.path

        if not file_path.exists():
            return [StaticIssue(change.path, "file does not exist.")]

        original = file_path.read_text(encoding="utf-8")
        patched = original

        seen: set[str] = set()

        for index, edit in enumerate(change.edits, start=1):

            target = edit.old_code.strip()

            if target in seen:
                issues.append(
                    StaticIssue(
                        change.path,
                        f"edit #{index}: multiple edits target the same code.",
                    )
                )
                continue

            seen.add(target)

            matches = self._find_matches(patched, edit.old_code)

            if not matches:
                issues.append(
                    StaticIssue(
                        change.path,
                        f"edit #{index}: old_code was not found after "
                        "applying previous edits.\n\n"
                        f"You expected this content:\n{edit.old_code}\n\n"
                        f"The actual current content of {change.path} is:\n"
                        f"{patched}",
                    )
                )
                continue

            if len(matches) > 1:
                issues.append(
                    StaticIssue(
                        change.path,
                        f"edit #{index}: old_code matched {len(matches)} "
                        "locations (expected exactly one).",
                    )
                )
                continue

            match = matches[0]

            patched = (
                patched[: match.start()]
                + edit.new_code
                + patched[match.end() :]
            )

        if not issues:
            for msg in self.syntax.check(change.path, patched):
                issues.append(StaticIssue(change.path, msg))

        return issues

    def _validate_create(self, change: FileChange) -> list[StaticIssue]:

        issues: list[StaticIssue] = []

        file_path = self.repo_root / change.path

        if file_path.exists():
            issues.append(
                StaticIssue(change.path, "file already exists.")
            )

        if not change.code:
            issues.append(
                StaticIssue(change.path, "create action requires code.")
            )
            return issues

        for msg in self.syntax.check(change.path, change.code):
            issues.append(StaticIssue(change.path, msg))

        return issues

    def _validate_delete(self, change: FileChange) -> list[StaticIssue]:

        file_path = self.repo_root / change.path

        if not file_path.exists():
            return [StaticIssue(change.path, "file does not exist.")]

        # Cross-file dependency validation intentionally belongs to the
        # Reviewer Agent (LLM / project-aware stage), not the static validator.
        return []

    def _find_matches(
        self,
        source: str,
        target: str,
    ) -> list[re.Match]:

        return list(
            re.finditer(
                re.escape(target),
                source,
            )
        )