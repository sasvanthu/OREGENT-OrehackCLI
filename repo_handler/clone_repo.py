import subprocess
import tempfile
import shutil
import os


def clone_repository(repo_url: str) -> str:
    """
    Clones a Git repository into a temporary directory.

    Returns the path of the cloned repository.
    """

    temp_dir = tempfile.mkdtemp(prefix="repo_eval_")

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, temp_dir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return temp_dir

    except subprocess.CalledProcessError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Git clone failed: {e.stderr.decode()}")