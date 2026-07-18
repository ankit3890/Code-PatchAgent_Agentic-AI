import json
import logging

from agents.planner import PlannerAgent
from agents.reader import ReaderAgent
from agents.writer import WriterAgent
from rag.indexer import RepositoryIndexer
from rag.retriever import CodeRetriever

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

REPO_URL = "https://github.com/ankit3890/ML-Movie-Recommendation"
COLLECTION_NAME = "ML-Movie-Recommendation"


def main():

    # ------------------------------------------------------------------
    # Ensure repository is indexed
    # ------------------------------------------------------------------
    RepositoryIndexer(
        repo_url=REPO_URL,
        collection_name=COLLECTION_NAME,
    ).index()

    retriever = CodeRetriever(
        collection_name=COLLECTION_NAME,
    )

    planner = PlannerAgent()
    reader = ReaderAgent(retriever)
    writer = WriterAgent()

    request = "Add JWT authentication to the Flask backend."

    print("=" * 100)
    print("USER REQUEST")
    print("=" * 100)
    print(request)

    # ------------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------------
    plan = planner.plan(request)

    print("\n")
    print("=" * 100)
    print("PLAN")
    print("=" * 100)
    print(json.dumps(plan.model_dump(), indent=4))

    # ------------------------------------------------------------------
    # Reader
    # ------------------------------------------------------------------
    reader_result, repository_context = reader.read(plan)

    print("\n")
    print("=" * 100)
    print("READER")
    print("=" * 100)
    print(json.dumps(reader_result.model_dump(), indent=4))

    # ------------------------------------------------------------------
    # Writer
    # ------------------------------------------------------------------
    writer_result = writer.write(
        plan=plan,
        reader_result=reader_result,
        repository_context=repository_context,
    )

    print("\n")
    print("=" * 100)
    print("WRITER")
    print("=" * 100)
    print(json.dumps(writer_result.model_dump(), indent=4))


if __name__ == "__main__":
    main()