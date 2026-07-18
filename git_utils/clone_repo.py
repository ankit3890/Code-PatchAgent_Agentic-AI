import logging
from pathlib import Path
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from config import settings

logger = logging.getLogger(__name__)


class RepoManager:
    """
    Handles cloning and updating Git repositories.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.repos_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def clone_or_update(self, repo_url: str) -> Path:
        """
        Clone a repository if it doesn't exist.
        Otherwise, pull the latest changes.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Local path to the repository.

        Raises:
            RuntimeError: If cloning fails, or if an existing local
                directory is not a valid git repository.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        repo_path = self.base_dir / repo_name

        if repo_path.exists():
            logger.info("Repository already exists at %s. Pulling latest changes...", repo_path)
            try:
                repo = Repo(repo_path)
                repo.remotes.origin.pull()
            except (InvalidGitRepositoryError, NoSuchPathError) as e:
                raise RuntimeError(
                    f"{repo_path} exists but is not a valid git repository: {e}"
                )
            except GitCommandError as e:
                logger.warning("Git pull failed, local copy may be stale:\n%s", e)

        else:
            logger.info("Cloning repository from %s...", repo_url)
            try:
                Repo.clone_from(repo_url, repo_path)
            except GitCommandError as e:
                raise RuntimeError(f"Clone failed:\n{e}")

        return repo_path