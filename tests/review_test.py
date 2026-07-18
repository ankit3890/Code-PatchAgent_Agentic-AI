import json
import logging
from pathlib import Path

from agents.planner import PlannerAgent
from agents.reader import ReaderAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from config import settings
from rag.indexer import RepositoryIndexer
from rag.retriever import CodeRetriever
from prompts.reviewer.schema import ReviewState

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

REPO_URL = "https://github.com/ankit3890/ML-Movie-Recommendation"
COLLECTION_NAME = "ML-Movie-Recommendation"


def main():

    # ------------------------------------------------------------------
    # Index Repository
    # ------------------------------------------------------------------

    RepositoryIndexer(
        repo_url=REPO_URL,
        collection_name=COLLECTION_NAME,
    ).index()

    repo_root = Path("repos") / COLLECTION_NAME

    retriever = CodeRetriever(
        collection_name=COLLECTION_NAME,
    )

    planner = PlannerAgent()
    reader = ReaderAgent(retriever)
    writer = WriterAgent()
    reviewer = ReviewerAgent(repo_root=repo_root)

    request = "Add JWT authentication to the Flask backend."

    print("=" * 100)
    print("USER REQUEST")
    print("=" * 100)
    print(request)

    # ------------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------------

    plan = planner.plan(request)

    # ------------------------------------------------------------------
    # Reader
    # ------------------------------------------------------------------

    reader_result, repository_context = reader.read(plan)

    # ------------------------------------------------------------------
    # Initial Writer
    # ------------------------------------------------------------------

    writer_result = writer.write(
        plan=plan,
        reader_result=reader_result,
        repository_context=repository_context,
    )

    # ------------------------------------------------------------------
    # Review State
    # ------------------------------------------------------------------

    review_state = ReviewState()
    
    # ------------------------------------------------------------------
    # Review Loop
    # ------------------------------------------------------------------

    for cycle in range(1, settings.max_review_cycles + 1):

        review_result = reviewer.review(
            plan=plan,
            reader_result=reader_result,
            writer_result=writer_result,
            review_state=review_state,
        )

        print("\n")
        print("=" * 100)
        print(f"REVIEW (cycle {cycle})")
        print("=" * 100)
        print(json.dumps(review_result.model_dump(), indent=4))

        if review_result.approved:
            logging.info(
                "Review approved after %d cycle(s).",
                cycle,
            )
            break

        if cycle == settings.max_review_cycles:
            logging.warning(
                "Max review cycles (%d) reached without approval.",
                settings.max_review_cycles,
            )
            break

        logging.info(
            "Review rejected (cycle %d). Revising patch...",
            cycle,
        )

        writer_result = writer.revise(
            plan=plan,
            reader_result=reader_result,
            repository_context=repository_context,
            previous_result=writer_result,
            review_feedback=review_result,
        )

        review_state.cycle = cycle
        review_state.unresolved_issues = review_result.issues

    # ------------------------------------------------------------------
    # Final Result
    # ------------------------------------------------------------------

    print("\n")
    print("=" * 100)
    print("FINAL WRITER OUTPUT")
    print("=" * 100)
    print(json.dumps(writer_result.model_dump(), indent=4))


if __name__ == "__main__":
    main()