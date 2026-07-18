from typing import Literal

from pydantic import BaseModel, Field

TaskType = Literal["bug", "feature", "refactor", "docs", "test", "other"]

# Valid downstream agents this plan can route to. Extend as new agents
# are added to the graph.
NextAgent = Literal["reader"]


class Plan(BaseModel):
    goal: str = Field(description="Main objective")

    task_type: TaskType = Field(
        description="One of: bug, feature, refactor, docs, test, other"
    )

    subtasks: list[str] = Field(
        description="Ordered list of steps",
        min_length=1,
    )

    required_context: list[str] = Field(
        description=(
            "Concise search terms the Reader Agent should use to "
            "retrieve relevant code from the repository."
        ),
        min_length=1,
    )

    next_agent: NextAgent = Field(
        default="reader",
        description="The next agent that should act on this plan.",
    )