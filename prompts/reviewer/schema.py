from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    computed_field,
    model_validator,
)


Severity = Literal[
    "critical",
    "major",
    "minor",
    "suggestion",
]


class ReviewIssue(BaseModel):
    """
    A single issue found during review.
    """

    severity: Severity = Field(
        description="Severity of the issue."
    )

    file: str | None = Field(
        default=None,
        description="Repository file containing the issue."
    )

    message: str = Field(
        description="Description of the issue."
    )

    recommendation: str = Field(
        description="Suggested fix."
    )

    @model_validator(mode="after")
    def validate_issue(self):

        if (
            self.severity in {"critical", "major"}
            and (self.file is None or not self.file.strip())
        ):
            raise ValueError(
                f"{self.severity} issues must specify a file."
            )

        return self


class ReviewChecklist(BaseModel):
    """
    High-level verification of the implementation.
    """

    user_request_satisfied: bool = Field(
        description="The implementation satisfies the user's request."
    )

    execution_plan_satisfied: bool = Field(
        description="The implementation satisfies the execution plan."
    )

    implementation_complete: bool = Field(
        description="All required functionality has been implemented."
    )

    summary_matches_patch: bool = Field(
        description="The Writer summary accurately describes the patch."
    )

    no_security_regressions: bool = Field(
        description="No new security problems were introduced."
    )


class ReviewState(BaseModel):
    """
    Reviewer state persisted across review cycles.
    """

    cycle: int = Field(
        default=0,
        description="Current review cycle."
    )

    unresolved_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Blocking issues from previous reviews."
    )


# ==========================================================
# LLM OUTPUT
# ==========================================================

class ReviewLLMOutput(BaseModel):
    """
    Raw structured output returned by the LLM.
    """

    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence score."
    )

    summary: str = Field(
        min_length=1,
        description="Overall review summary."
    )

    checklist: ReviewChecklist = Field(
        description="Implementation verification checklist."
    )

    issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="Issues found during review."
    )


# ==========================================================
# FINAL REVIEW
# ==========================================================

class ReviewResult(ReviewLLMOutput):
    """
    Final review used by the application.

    approved and next_agent are computed automatically.
    """

    @computed_field
    @property
    def approved(self) -> bool:

        blocking = {"critical", "major"}

        return not any(
            issue.severity in blocking
            for issue in self.issues
        )

    @computed_field
    @property
    def next_agent(self) -> Literal["writer", "patch"]:

        return (
            "patch"
            if self.approved
            else "writer"
        )

    @model_validator(mode="after")
    def validate_review(self):

        self.summary = self.summary.strip()

        if not self.summary:
            raise ValueError(
                "Summary cannot be empty."
            )

        #
        # Score sanity
        #

        if self.approved and self.score < 0.50:
            raise ValueError(
                "Approved reviews should not have score < 0.50."
            )

        if not self.approved and self.score >= 0.80:
            raise ValueError(
                "Rejected reviews should not have score >= 0.80."
            )

        #
        # Checklist consistency
        #

        has_blocking = any(
            issue.severity in {"critical", "major"}
            for issue in self.issues
        )

        if has_blocking:

            if self.checklist.user_request_satisfied:
                raise ValueError(
                    "Blocking issues exist but checklist says user request is satisfied."
                )

            if self.checklist.implementation_complete:
                raise ValueError(
                    "Blocking issues exist but checklist says implementation is complete."
                )

        #
        # Summary consistency
        #

        if (
            not self.checklist.summary_matches_patch
            and not has_blocking
        ):
            raise ValueError(
                "Summary mismatch should produce a blocking issue."
            )

        #
        # Security consistency
        #

        if (
            not self.checklist.no_security_regressions
            and not any(
                issue.severity in {"critical", "major"}
                for issue in self.issues
            )
        ):
            raise ValueError(
                "Security regressions must produce a blocking issue."
            )

        return self