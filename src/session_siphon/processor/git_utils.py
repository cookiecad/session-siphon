"""Git repository utilities."""

import subprocess
from functools import lru_cache
from pathlib import Path

from session_siphon.logging import get_logger

logger = get_logger("git_utils")


@lru_cache(maxsize=1024)
def get_git_repo_info(project_path: str | Path) -> str | None:
    """Extract git repository information from a project path.

    Tries to determine the remote URL or repository name for a given path.
    Returns None if:
    - The path does not exist
    - The path is not a git repository
    - Git is not installed
    - The repository has no remotes and we can't determine a name

    Args:
        project_path: Path to the project directory

    Returns:
        String identifying the repo (e.g., 'owner/repo' or 'repo_name'), or None
    """
    path = Path(project_path)
    if not path.exists():
        return None

    try:
        # Get remote URL (origin)
        # git -C <path> config --get remote.origin.url
        result = subprocess.run(
            ["git", "-C", str(path), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False
        )
        
        url = result.stdout.strip()
        if url:
            # Parse URL to get owner/repo
            # Formats:
            # https://github.com/owner/repo.git
            # git@github.com:owner/repo.git
            # https://gitlab.com/owner/repo
            
            # Remove .git suffix
            if url.endswith(".git"):
                url = url[:-4]
                
            # Split by /
            parts = url.split("/")
            if len(parts) >= 2:
                # remote/repo
                return f"{parts[-2]}/{parts[-1]}"
            return parts[-1]

    except Exception as e:
        logger.debug("Failed to get git remote info for %s: %s", path, e)
        pass

    # Fallback: check if it is a git repo at all, and return folder name
    try:
        is_git = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            check=False
        ).returncode == 0
        
        if is_git:
            return path.name
            
    except Exception:
        pass

    return None
