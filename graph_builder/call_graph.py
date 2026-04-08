"""
call_graph.py  —  graph_builder/call_graph.py

Builds a function call graph for ALL languages:
  Python  : ast.Call  (precise — catches method calls, chained calls)
  JS/TS   : regex on function bodies  (catches calls, arrow functions, hooks)
  Java    : regex on method bodies
  Go      : regex on function bodies
  Rust    : regex on function bodies
  C/C++   : regex on function bodies
  C#      : regex on method bodies
  PHP     : regex on function bodies
  Dart    : regex on function/method bodies
  Ruby    : regex on method bodies
  Kotlin  : regex on function bodies
  Swift   : regex on function bodies

Returns: (graph, summary)
  graph   : {func_name: [called_func1, called_func2, ...]}
  summary : {total_functions, total_calls, most_called}
"""

import ast
import os
import re
from collections import Counter


# ── Language dispatch ─────────────────────────────────────────────────────────

EXT_MAP = {
    ".py":    "python",
    ".js":    "javascript",  ".jsx":  "javascript",
    ".ts":    "typescript",  ".tsx":  "typescript",
    ".java":  "java",
    ".go":    "go",
    ".rs":    "rust",
    ".c":     "c",           ".h":    "c",
    ".cpp":   "cpp",         ".cc":   "cpp",  ".cxx": "cpp",
    ".cs":    "csharp",
    ".php":   "php",
    ".dart":  "dart",
    ".rb":    "ruby",
    ".kt":    "kotlin",      ".kts":  "kotlin",
    ".swift": "swift",
}


def _get_lang(path):
    return EXT_MAP.get(os.path.splitext(path)[1].lower())


# ── Python (precise AST) ──────────────────────────────────────────────────────

class _PythonCallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.current = None
        self.graph   = {}

    def visit_FunctionDef(self, node):
        prev = self.current
        self.current = node.name
        self.graph.setdefault(self.current, [])
        self.generic_visit(node)
        self.current = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        if self.current is None:
            self.generic_visit(node)
            return
        # Direct call: func()
        if isinstance(node.func, ast.Name):
            self.graph[self.current].append(node.func.id)
        # Method call: obj.method()
        elif isinstance(node.func, ast.Attribute):
            self.graph[self.current].append(node.func.attr)
        self.generic_visit(node)


def _call_graph_python(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        visitor = _PythonCallVisitor()
        visitor.visit(tree)
        return visitor.graph
    except Exception:
        return {}


# ── Regex-based extractor (all other languages) ───────────────────────────────

# Patterns per language to find function/method definitions
FUNC_PATTERNS = {
    "javascript": [
        r'(?:function\s+(\w+)\s*\([^)]*\)\s*\{)',               # function foo() {
        r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{',  # const foo = () => {
        r'(?:const|let|var)\s+(\w+)\s*=\s*function\s*\(',       # const foo = function(
        r'(\w+)\s*:\s*(?:async\s*)?function\s*\(',              # key: function(
    ],
    "java": [
        r'(?:public|private|protected|static|void|[\w<>\[\]]+)\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+\s*)?\{',
    ],
    "go": [
        r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(',
    ],
    "rust": [
        r'fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(',
    ],
    "c": [
        r'(?:^|\s)(\w+)\s*\([^;{)]*\)\s*\{',
    ],
    "csharp": [
        r'(?:public|private|protected|internal|static|override|virtual|async|void|[\w<>\[\]]+)\s+(\w+)\s*\([^)]*\)\s*\{',
    ],
    "php": [
        r'function\s+(\w+)\s*\(',
    ],
    "dart": [
        r'(?:void|Future|Stream|[\w<>?]+)\s+(\w+)\s*\([^)]*\)\s*(?:async\s*)?\{',
    ],
    "ruby": [
        r'def\s+(\w+)',
    ],
    "kotlin": [
        r'fun\s+(\w+)\s*\(',
    ],
    "swift": [
        r'func\s+(\w+)\s*\(',
    ],
}

# Shared: calls look like identifier( in most C-family languages
CALL_PATTERN = re.compile(r'\b([a-zA-Z_]\w*)\s*\(')

# Names to exclude from call detection (language keywords, common builtins)
EXCLUDE_CALLS = {
    # JS/TS
    "if","for","while","switch","catch","function","class","return","typeof","instanceof",
    "new","delete","void","throw","case","import","export","from","async","await",
    "console","Math","Object","Array","Promise","JSON","setTimeout","setInterval",
    "require","module","process","Buffer","parseInt","parseFloat","isNaN","Boolean",
    "String","Number","Symbol","Map","Set","WeakMap","WeakSet","Error","Date",
    # Java
    "for","if","while","switch","catch","class","interface","new","throw","return",
    "System","String","Integer","Long","Boolean","List","Map","ArrayList","HashMap",
    # Python builtins (for fallback)
    "print","len","range","int","str","float","list","dict","set","tuple","type",
    "isinstance","hasattr","getattr","setattr","open","super","next","iter",
    # Go
    "fmt","make","len","cap","append","copy","close","panic","recover","new","delete",
    # Generic
    "this","self","null","nil","true","false","undefined","None","True","False",
}


def _call_graph_regex(path, lang):
    """
    Extract function definitions and their calls using regex.
    Strategy:
      1. Find all function definitions → these are graph nodes
      2. For each function, extract the body (rough heuristic: next N lines)
      3. Find all identifier() patterns in the body
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        src = "".join(lines)
    except Exception:
        return {}

    patterns = FUNC_PATTERNS.get(lang, FUNC_PATTERNS.get("javascript", []))
    graph = {}
    func_positions = []  # (line_index, func_name)

    for pattern in patterns:
        for m in re.finditer(pattern, src, re.MULTILINE):
            name = m.group(1)
            if name and name not in EXCLUDE_CALLS and not name[0].isdigit():
                # Find line number of this match
                line_no = src[:m.start()].count('\n')
                func_positions.append((line_no, name))

    # Deduplicate, keep order
    seen = set()
    unique_positions = []
    for pos, name in sorted(func_positions):
        if name not in seen:
            seen.add(name)
            unique_positions.append((pos, name))
            graph[name] = []

    # For each function, scan lines until next function starts
    for i, (line_no, func_name) in enumerate(unique_positions):
        end_line = unique_positions[i+1][0] if i+1 < len(unique_positions) else len(lines)
        # Look at function body (up to 100 lines to avoid over-scanning)
        body_lines = lines[line_no+1 : min(line_no+1+100, end_line)]
        body = "".join(body_lines)

        calls = []
        for m in CALL_PATTERN.finditer(body):
            call_name = m.group(1)
            if (call_name not in EXCLUDE_CALLS
                    and not call_name[0].isdigit()
                    and call_name != func_name):
                calls.append(call_name)

        graph[func_name] = list(dict.fromkeys(calls))  # deduplicate, preserve order

    return graph


# ── Main builder ──────────────────────────────────────────────────────────────

def build_function_call_graph(source_files):
    """
    Build function call graph for all languages.

    Returns
    -------
    (graph, summary)
      graph   : {func_name: [called_func1, ...]}
      summary : {total_functions, total_calls, most_called}
    """
    graph = {}
    all_calls = []

    for path in source_files:
        lang = _get_lang(path)
        if lang is None:
            continue

        if lang == "python":
            file_graph = _call_graph_python(path)
        else:
            file_graph = _call_graph_regex(path, lang)

        # Prefix function names with filename to avoid cross-file collisions
        # Only if the name already exists in graph
        basename = os.path.splitext(os.path.basename(path))[0]
        for func, calls in file_graph.items():
            key = func if func not in graph else f"{func}@{basename}"
            graph[key] = calls
            all_calls.extend(calls)

    # Build summary
    counter = Counter(all_calls)
    total_calls = sum(len(v) for v in graph.values())
    most_called = [fn for fn, _ in counter.most_common(10)]

    summary = {
        "total_functions": len(graph),
        "total_calls":     total_calls,
        "most_called":     most_called,
    }

    return graph, summary