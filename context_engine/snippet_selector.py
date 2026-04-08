import ast
import os


def extract_python_snippets(file_path, source, max_snippets, snippets):

    try:
        tree = ast.parse(source)
    except Exception:
        return

    for node in ast.walk(tree):

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):

            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            code_lines = source.splitlines()[start - 1:end]

            snippets.append({
                "file": os.path.basename(file_path),
                "language": "python",
                "function_name": node.name,
                "snippet": "\n".join(code_lines)
            })

            if len(snippets) >= max_snippets:
                return


def extract_generic_snippet(file_path, source, language, snippets):
    """
    For non-Python files, just grab the first 40 lines as a representative snippet.
    """

    lines = source.splitlines()[:40]

    if not lines:
        return

    snippets.append({
        "file": os.path.basename(file_path),
        "language": language,
        "function_name": None,
        "snippet": "\n".join(lines)
    })


LANGUAGE_MAP = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".cpp": "cpp",
    ".c": "c",
    ".rs": "rust",
    ".php": "php",
    ".dart": "dart",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
}


def extract_code_snippets(source_files, max_snippets=5):

    snippets = []

    for file_path in source_files:

        if len(snippets) >= max_snippets:
            break

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except Exception:
            continue

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".py":
            extract_python_snippets(file_path, source, max_snippets, snippets)
        elif ext in LANGUAGE_MAP:
            extract_generic_snippet(file_path, source, LANGUAGE_MAP[ext], snippets)

    return snippets
