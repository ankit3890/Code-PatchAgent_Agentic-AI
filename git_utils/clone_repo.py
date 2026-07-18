import logging
import uuid
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)


class RepoManager:
    """
    Handles cloning and updating Git repositories with a serverless-friendly ZIP fallback.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.repos_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def clone_or_update(self, repo_url: str) -> Path:
        """
        Clone a repository if it doesn't exist.
        Otherwise, pull the latest changes. Falls back to ZIP archive download
        if Git is not available.

        Args:
            repo_url: GitHub repository URL

        Returns:
            Local path to the repository.
        """
        repo_name = repo_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        repo_path = self.base_dir / repo_name

        # Check if git command-line tool and GitPython are available
        git_available = False
        try:
            from git import Repo
            # Verify git command binary is present by calling a command
            Repo()
            git_available = True
        except (ImportError, Exception):
            git_available = False

        if git_available:
            from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
            if repo_path.exists():
                logger.info("Repository already exists at %s. Pulling latest changes...", repo_path)
                try:
                    repo = Repo(repo_path)
                    repo.remotes.origin.pull()
                except (InvalidGitRepositoryError, NoSuchPathError) as e:
                    logger.warning("%s exists but is not a valid git repository, downloading ZIP fallback: %s", repo_path, e)
                    self._download_zip_fallback(repo_url, repo_path)
                except GitCommandError as e:
                    logger.warning("Git pull failed, local copy may be stale: %s", e)
            else:
                logger.info("Cloning repository from %s...", repo_url)
                try:
                    Repo.clone_from(repo_url, repo_path)
                except GitCommandError as e:
                    logger.warning("Clone failed, trying ZIP download fallback: %s", e)
                    self._download_zip_fallback(repo_url, repo_path)
        else:
            logger.info("Git command not available. Using ZIP download fallback...")
            self._download_zip_fallback(repo_url, repo_path)

        return repo_path

    def _download_zip_fallback(self, repo_url: str, dest_dir: Path):
        """
        Downloads the repository as a ZIP archive from GitHub and extracts it to dest_dir.
        """
        import zipfile
        import io
        import requests
        import shutil

        # Parse username and repo name from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise RuntimeError(f"Invalid GitHub repository URL: {repo_url}")
            
        username = parts[-2]
        repo_name = parts[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        # Try downloading main branch first
        zip_url = f"https://github.com/{username}/{repo_name}/archive/refs/heads/main.zip"
        logger.info("Attempting to download ZIP from %s", zip_url)
        try:
            res = requests.get(zip_url, timeout=30)
            if res.status_code == 404:
                # Try master branch
                zip_url = f"https://github.com/{username}/{repo_name}/archive/refs/heads/master.zip"
                logger.info("Attempting master branch fallback ZIP from %s", zip_url)
                res = requests.get(zip_url, timeout=30)
        except Exception as e:
            raise RuntimeError(f"Connection failed when downloading ZIP fallback: {e}")

        if res.status_code != 200:
            raise RuntimeError(f"Failed to download repository ZIP from GitHub (status: {res.status_code})")

        # Extract the ZIP contents
        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                namelist = z.namelist()
                if not namelist:
                    raise RuntimeError("Downloaded ZIP file is empty")
                
                # Get the root folder name inside the zip archive (typically '{repo_name}-{branch_name}')
                root_dir_name = namelist[0].split('/')[0]

                # Create temp folder inside dest_dir's parent directory
                temp_dir = dest_dir.parent / f"_temp_{repo_name}_{str(uuid.uuid4())[:8]}"
                temp_dir.mkdir(parents=True, exist_ok=True)

                z.extractall(path=temp_dir)

                src_folder = temp_dir / root_dir_name

                # Clear destination directory if it exists
                if dest_dir.exists():
                    shutil.rmtree(dest_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)

                for item in src_folder.iterdir():
                    shutil.move(str(item), str(dest_dir / item.name))

                # Clean up temp folder
                shutil.rmtree(temp_dir)
                logger.info("ZIP extract and sync completed successfully for %s", dest_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to extract repository ZIP archive: {e}")