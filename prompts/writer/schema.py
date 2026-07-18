from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SearchReplaceEdit(BaseModel):
    """
    A targeted search/replace edit for an existing file.
    """

    old_code: str = Field(
        description=(
            "Exact existing code copied verbatim from the repository "
            "context. Whitespace and indentation must match exactly."
        )
    )

    new_code: str = Field(
        description=(
            "Replacement code that will replace old_code."
        )
    )

    @model_validator(mode="after")
    def validate_edit(self):
        if not self.old_code.strip():
            raise ValueError("old_code cannot be empty.")

        if not self.new_code.strip():
            raise ValueError("new_code cannot be empty.")

        if self.old_code == self.new_code:
            raise ValueError(
                "old_code and new_code must differ."
            )

        return self


class FileChange(BaseModel):
    """
    A change to a single repository file.
    """

    path: str = Field(
        description="Repository-relative file path."
    )

    action: Literal[
        "create",
        "modify",
        "delete",
    ] = Field(
        description="Type of file operation."
    )

    explanation: str = Field(
        description=(
            "Short explanation describing the purpose of the change."
        )
    )

    code: str | None = Field(
        default=None,
        description=(
            "Complete contents of a newly created file. "
            "Only valid for create actions."
        ),
    )

    edits: list[SearchReplaceEdit] = Field(
        default_factory=list,
        description=(
            "Search/replace edits. "
            "Required for modify actions."
        ),
    )

    @model_validator(mode="after")
    def validate_action(self):

        if not self.explanation.strip():
            raise ValueError(
                "Explanation cannot be empty."
            )

        if self.action == "create":

            if not self.code or not self.code.strip():
                raise ValueError(
                    f"{self.path}: create requires non-empty code."
                )

            if self.edits:
                raise ValueError(
                    f"{self.path}: create cannot contain edits."
                )

        elif self.action == "modify":

            if self.code is not None:
                raise ValueError(
                    f"{self.path}: modify cannot contain full file code."
                )

            if not self.edits:
                raise ValueError(
                    f"{self.path}: modify requires at least one edit."
                )

        elif self.action == "delete":

            if self.code is not None:
                raise ValueError(
                    f"{self.path}: delete cannot contain code."
                )

            if self.edits:
                raise ValueError(
                    f"{self.path}: delete cannot contain edits."
                )

        return self


class WriterResult(BaseModel):
    """
    Output of the Writer Agent.
    """

    summary: str = Field(
        description=(
            "High-level summary of all proposed repository changes."
        )
    )

    changes: list[FileChange] = Field(
        description="List of file changes."
    )

    next_agent: Literal["reviewer"] = Field(
        default="reviewer",
        description="Next agent in the workflow."
    )

    @model_validator(mode="after")
    def validate_result(self):

        if not self.summary.strip():
            raise ValueError(
                "Summary cannot be empty."
            )

        if not self.changes:
            raise ValueError(
                "At least one file change is required."
            )

        seen_paths = set()

        for change in self.changes:

            if change.path in seen_paths:
                raise ValueError(
                    f"Duplicate file path: {change.path}"
                )

            seen_paths.add(change.path)

        return self