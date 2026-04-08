import os
import ast
import re


# ── Python-specific dangerous patterns ───────────────────────────────────────
DANGEROUS_FUNCTIONS_PY = {
    "eval", "exec", "os.system",
    "subprocess.Popen", "subprocess.call"
}

UNSAFE_DESERIALIZATION_PY = {
    "pickle.loads", "yaml.load"
}

# ── Cross-language secret patterns (regex, case-insensitive) ─────────────────
SECRET_PATTERNS = [
    r'api[_\-]?key\s*[=:]\s*[\'"].{6,}[\'"]',
    r'token\s*[=:]\s*[\'"].{6,}[\'"]',
    r'password\s*[=:]\s*[\'"].{4,}[\'"]',
    r'secret\s*[=:]\s*[\'"].{6,}[\'"]',
    r'auth[_\-]?key\s*[=:]\s*[\'"].{6,}[\'"]',
    r'access[_\-]?key\s*[=:]\s*[\'"].{6,}[\'"]',
]

# ── JS/TS dangerous patterns ──────────────────────────────────────────────────
DANGEROUS_JS_PATTERNS = [
    r'\beval\s*\(',
    r'\bnew\s+Function\s*\(',
    r'\bdocument\.write\s*\(',
    r'\binnerHTML\s*=',
    r'\bexec\s*\(',                     # child_process.exec
    r'\bexecSync\s*\(',
    r'\bspawnSync\s*\(',
]

# ── Java dangerous patterns ───────────────────────────────────────────────────
DANGEROUS_JAVA_PATTERNS = [
    r'Runtime\.getRuntime\(\)\.exec\s*\(',
    r'ProcessBuilder\s*\(',
    r'\.executeQuery\s*\(.+\+',         # raw SQL concat
]


def _scan_secrets(code):
    """Returns list of matched secret patterns in code (case-insensitive)."""
    found = []
    lower = code.lower()
    for pattern in SECRET_PATTERNS:
        matches = re.findall(pattern, lower)
        found.extend(matches)
    return found


def _analyze_python_file(path, issues):
    """Deep Python analysis using AST."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
        tree = ast.parse(code)
    except Exception:
        return

    issues["hardcoded_secrets"].extend(_scan_secrets(code))

    for node in ast.walk(tree):

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in DANGEROUS_FUNCTIONS_PY:
                    issues["dangerous_calls"].append(node.func.id)
            if isinstance(node.func, ast.Attribute):
                func_name = f"{getattr(node.func.value, 'id', '')}.{node.func.attr}"
                if func_name in DANGEROUS_FUNCTIONS_PY:
                    issues["dangerous_calls"].append(func_name)
                if func_name in UNSAFE_DESERIALIZATION_PY:
                    issues["unsafe_deserialization"].append(func_name)

        if isinstance(node, ast.FunctionDef):
            has_try = any(isinstance(child, ast.Try) for child in ast.walk(node))
            if not has_try:
                issues["missing_exception_handling"] += 1


def _analyze_js_file(path, issues):
    """Regex-based JS/TS security scan."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    except Exception:
        return

    issues["hardcoded_secrets"].extend(_scan_secrets(code))

    for pattern in DANGEROUS_JS_PATTERNS:
        matches = re.findall(pattern, code)
        if matches:
            issues["dangerous_calls"].extend([pattern.split(r'\b')[-1].split(r'\s')[0]] * len(matches))

    # Count functions missing try/catch
    func_matches = re.findall(
        r'(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        code, re.DOTALL
    )
    for body in func_matches:
        if "try" not in body and "catch" not in body:
            issues["missing_exception_handling"] += 1


def _analyze_java_file(path, issues):
    """Regex-based Java security scan."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    except Exception:
        return

    issues["hardcoded_secrets"].extend(_scan_secrets(code))

    for pattern in DANGEROUS_JAVA_PATTERNS:
        matches = re.findall(pattern, code)
        if matches:
            issues["dangerous_calls"].extend(["java_dangerous"] * len(matches))

    # Count methods missing try/catch (simplified)
    method_blocks = re.findall(
        r'(?:public|private|protected)\s+[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}',
        code, re.DOTALL
    )
    for body in method_blocks:
        if "try" not in body and "catch" not in body:
            issues["missing_exception_handling"] += 1


def _analyze_generic_file(path, issues):
    """Generic secret scanning for any other language."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    except Exception:
        return
    issues["hardcoded_secrets"].extend(_scan_secrets(code))


# File extension → analyzer function
_ANALYZERS = {
    ".py":   _analyze_python_file,
    ".js":   _analyze_js_file,
    ".jsx":  _analyze_js_file,
    ".ts":   _analyze_js_file,
    ".tsx":  _analyze_js_file,
    ".java": _analyze_java_file,
    # Generic secret scan for everything else
    ".go":   _analyze_generic_file,
    ".rs":   _analyze_generic_file,
    ".php":  _analyze_generic_file,
    ".rb":   _analyze_generic_file,
    ".cs":   _analyze_generic_file,
    ".cpp":  _analyze_generic_file,
    ".c":    _analyze_generic_file,
}


def analyze_security(repo_path):
    """
    Walk the repo and run security analysis on all recognized source files.
    Returns issues dict.
    """
    issues = {
        "dangerous_calls": [],
        "unsafe_deserialization": [],
        "hardcoded_secrets": [],
        "missing_exception_handling": 0
    }

    IGNORED_DIRS = {".git", "node_modules", "venv", "__pycache__", "dist", "build"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            analyzer = _ANALYZERS.get(ext)
            if analyzer is None:
                continue
            path = os.path.join(root, file)
            analyzer(path, issues)

    # Deduplicate secrets (same pattern found in multiple files)
    issues["hardcoded_secrets"] = list(set(issues["hardcoded_secrets"]))

    return issues
