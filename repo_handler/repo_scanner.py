import os


def scan_repository(repo_path: str) -> dict:
    """
    Walk through the repository and collect all file paths
    while ignoring system directories.
    """

    all_files = []

    IGNORED_DIRS = {
        ".git",
        "node_modules",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".idea",
        ".vscode"
    }
    for root, dirs, files in os.walk(repo_path):

        # prevent os.walk from entering ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file in files:
            path = os.path.join(root, file)
            all_files.append(path)

    return {
        "total_files": len(all_files),
        "files": all_files
    }