import hashlib
import json
from pathlib import Path


def hash_content(content: str) -> str:
    """
    Compute a SHA-256 hash for a file's content.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_manifest(path: Path) -> dict[str, str]:
    """
    Load the manifest from disk.

    Returns:
        {
            "src/app.py": "<hash>",
            "src/auth.py": "<hash>",
        }
    """
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path: Path, manifest: dict[str, str]) -> None:
    """
    Save the manifest to disk.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            manifest,
            f,
            indent=4,
            sort_keys=True,
        )


def diff_manifest(
    old_manifest: dict[str, str],
    new_manifest: dict[str, str],
):
    """
    Compare the previous and current manifests.

    Returns:
        (
            changed_or_new,
            deleted,
            unchanged_count,
        )
    """

    changed_or_new = []
    deleted = []

    # New or modified files
    for path, file_hash in new_manifest.items():

        if (
            path not in old_manifest
            or old_manifest[path] != file_hash
        ):
            changed_or_new.append(path)

    # Deleted files
    for path in old_manifest:

        if path not in new_manifest:
            deleted.append(path)

    unchanged_count = (
        len(new_manifest)
        - len(changed_or_new)
    )

    return (
        changed_or_new,
        deleted,
        unchanged_count,
    )