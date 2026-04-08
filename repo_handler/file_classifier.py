import os


BACKEND_EXTENSIONS = {
    ".py", ".java", ".go", ".rb", ".cs", ".rs", ".php"
}

SYSTEMS_EXTENSIONS = {
    ".cpp", ".c", ".h", ".hpp"
}

JS_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx"
}

FRONTEND_EXTENSIONS = {
    ".html", ".css", ".scss", ".sass", ".less", ".svg"
}

DOC_EXTENSIONS = {
    ".md", ".txt", ".rst", ".pdf"
}

DATA_EXTENSIONS = {
    ".csv", ".xlsx", ".xls", ".parquet", ".sql"
}

CONFIG_EXTENSIONS = {
    ".yaml", ".yml", ".toml", ".ini", ".env", ".cfg",
    ".lock", ".gitignore", ".dockerignore", ".editorconfig"
}

ARCHIVE_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".rar", ".7z"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".avi",
    ".exe", ".dll", ".so", ".bin", ".pyc", ".class",
    ".ico", ".webp", ".ttf", ".woff", ".woff2"
}

FRONTEND_DIRS = {
    "components", "pages", "views", "public", "static",
    "assets", "styles", "css", "ui", "frontend", "client", "src/app"
}

BACKEND_DIRS = {
    "api", "server", "backend", "routes", "controllers",
    "models", "services", "handlers", "middleware", "core"
}

BACKEND_JS_FILENAMES = {
    "server", "app", "index", "router", "controller",
    "middleware", "db", "database", "model",
    "service", "handler", "route"
}


def _is_backend_js(file_path: str) -> bool:
    parts = file_path.replace("\\", "/").lower().split("/")
    filename = os.path.splitext(os.path.basename(file_path))[0].lower()

    for part in parts:
        if part in FRONTEND_DIRS:
            return False
        if part in BACKEND_DIRS:
            return True

    if filename in BACKEND_JS_FILENAMES:
        return True

    return False


def classify_file(file_path: str) -> str:

    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path).lower()

    if filename.startswith("readme") or filename.startswith("license"):
        return "documentation"

    if filename in {"dockerfile", "makefile", "procfile", "vagrantfile"}:
        return "configuration"

    if ext in BACKEND_EXTENSIONS:
        return "backend"

    if ext in SYSTEMS_EXTENSIONS:
        return "backend"

    if ext in JS_EXTENSIONS:
        if _is_backend_js(file_path):
            return "backend"
        return "frontend"

    if ext in FRONTEND_EXTENSIONS:
        return "frontend"

    if ext in DOC_EXTENSIONS:
        return "documentation"

    if ext in DATA_EXTENSIONS:
        return "dataset"

    if ext in CONFIG_EXTENSIONS:
        return "configuration"

    if ext in ARCHIVE_EXTENSIONS:
        return "archive"

    if ext in BINARY_EXTENSIONS:
        return "binary"

    return "unknown"


def classify_repository(files: list) -> dict:

    classified = {
        "backend": [],
        "frontend": [],
        "source_code": [],
        "documentation": [],
        "dataset": [],
        "configuration": [],
        "archive": [],
        "binary": [],
        "unknown": []
    }

    for file_path in files:
        category = classify_file(file_path)
        classified[category].append(file_path)

    return classified
