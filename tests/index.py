import logging

from rag.indexer import RepositoryIndexer

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

REPO_URL = "https://github.com/ankit3890/ML-Movie-Recommendation"
COLLECTION = "ML-Movie-Recommendation"


def main():

    indexer = RepositoryIndexer(
        repo_url=REPO_URL,
        collection_name=COLLECTION,
    )

    indexer.index()

    print("\nRepository is ready.")


if __name__ == "__main__":
    main()