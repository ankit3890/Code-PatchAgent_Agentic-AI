from pydantic import BaseModel, Field


class ComplianceCheck(BaseModel):

    compliant: bool = Field(
        description="True only if the output contains zero implementation "
        "suggestions, recommended changes, or named libraries/packages/"
        "frameworks anywhere in repository_summary, analysis, or any "
        "relevant_files[].reason."
    )

    violations: list[str] = Field(
        default_factory=list,
        description="Exact quoted phrases from the output that violate the "
        "rule (e.g. phrases containing 'would need to', 'should add', "
        "'requires', or naming a specific library). Empty if compliant.",
    )


COMPLIANCE_CHECK_PROMPT = """You are a strict compliance checker for the \
Reader Agent's output.

The Reader Agent must ONLY describe the repository as it currently exists. \
It must NEVER suggest implementation changes, recommend modifications, or \
name specific libraries/packages/frameworks to add.

Common violations look like:
- "would need to be modified/added/updated"
- "should include/add/use"
- "may need adjustment if..."
- "requires updates to..."
- naming any specific library or package as something to add

You will be given the Reader Agent's structured output. Check every field —
repository_summary, analysis, and every reason inside relevant_files — for
these violations.

Return compliant=True only if there are zero violations anywhere. If there
are any violations, return compliant=False and quote the exact offending
phrases in violations.
"""