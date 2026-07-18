from typing import Literal

from pydantic import BaseModel, Field


class RelevantFile(BaseModel):

    path: str

    reason: str

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence that this file is relevant."
    )


class ReaderResult(BaseModel):

    repository_summary: str

    analysis: str

    relevant_files: list[RelevantFile]

    next_agent: Literal["writer"] = "writer"