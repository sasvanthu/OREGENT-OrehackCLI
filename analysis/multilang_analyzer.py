"""
multilang_analyzer.py  —  analysis/multilang_analyzer.py
─────────────────────────────────────────────────────────
Extracts AST-level metrics from any source file using:
  1. Tree-sitter  (if installed — highest accuracy)
  2. Regex        (always available — good accuracy for all listed languages)

Supports: JS, JSX, TS, TSX, Java, Go, Rust, C, C++, PHP, Dart, Ruby, C#
Returns: { functions, classes, loops, conditionals, imports, function_lengths }
Returns None only for completely unsupported file extensions.
"""

import os
import re

# ── Tree-sitter (optional) ────────────────────────────────────────────────────
try:
    from tree_sitter_languages import get_parser as _ts_get_parser
    _TS_OK = True
except ImportError:
    _TS_OK = False

_TS_CACHE = {}

_TS_LANGS = {
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".go": "go",
    ".cpp": "cpp", ".c": "c",
    ".rs": "rust", ".php": "php", ".dart": "dart",
}

_TS_FUNC  = {"function_declaration","function_definition","method_definition",
             "method_declaration","arrow_function","function_expression",
             "func_declaration","func_literal","constructor_declaration"}
_TS_CLASS = {"class_declaration","class_definition","struct_type","struct_item"}
_TS_LOOP  = {"for_statement","for_in_statement","for_of_statement","while_statement",
             "do_statement","enhanced_for_statement","for_expression","loop_expression"}
_TS_COND  = {"if_statement","switch_statement","switch_expression","conditional_expression"}
_TS_IMP   = {"import_statement","import_declaration","use_declaration"}


def _ts_parse(ext, code):
    if not _TS_OK or ext not in _TS_LANGS:
        return None
    lang = _TS_LANGS[ext]
    if lang not in _TS_CACHE:
        try:
            _TS_CACHE[lang] = _ts_get_parser(lang)
        except Exception:
            _TS_CACHE[lang] = None
    parser = _TS_CACHE[lang]
    if parser is None:
        return None
    try:
        tree = parser.parse(bytes(code, "utf8"))
    except Exception:
        return None
    m = {"functions": 0, "classes": 0, "loops": 0, "conditionals": 0,
         "imports": [], "function_lengths": []}
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        t = node.type
        if t in _TS_FUNC:
            m["functions"] += 1
            m["function_lengths"].append(node.end_point[0] - node.start_point[0])
        elif t in _TS_CLASS:
            m["classes"] += 1
        elif t in _TS_LOOP:
            m["loops"] += 1
        elif t in _TS_COND:
            m["conditionals"] += 1
        elif t in _TS_IMP:
            try:
                m["imports"].append(code[node.start_byte:node.end_byte].strip()[:100])
            except Exception:
                pass
        stack.extend(node.children)
    return m


# ── Regex helpers ─────────────────────────────────────────────────────────────
def _c(patterns, code, flags=0):
    return sum(len(re.findall(p, code, flags)) for p in patterns)

def _f(patterns, code, flags=0):
    out = []
    for p in patterns:
        out.extend(re.findall(p, code, flags))
    return out


# ── Language regex definitions ────────────────────────────────────────────────

def _js(code):
    funcs = _c([
        r'\bfunction\s+\w+\s*\(',
        r'\basync\s+function\s+\w+\s*\(',
        r'\bconst\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        r'\bconst\s+\w+\s*=\s*(?:async\s*)?\w+\s*=>',
        r'\blet\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        r'\bvar\s+\w+\s*=\s*function\s*\(',
        r'^\s*(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?\w+\s*\([^)]*\)\s*\{',
        r'\b(?:public|private|protected|static|abstract|async|readonly)\s+\w+\s*\([^)]*\)\s*(?::\s*[\w<>\[\]| ]+)?\s*\{',
    ], code, re.MULTILINE)
    n = max(funcs, 1)
    avg = code.count("\n") // n
    return {
        "functions": funcs,
        "classes": _c([r'\bclass\s+\w+'], code),
        "loops": _c([r'\bfor\s*\(', r'\bwhile\s*\(', r'\bfor\s+\w+\s+of\b',
                     r'\bfor\s+\w+\s+in\b', r'\.forEach\s*\('], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\(', r'\?\s*\w'], code),
        "imports": _f([r'^import\b.+from\s+[\'"].+[\'"]',
                       r'\brequire\s*\(\s*[\'"].+[\'"]\s*\)'], code, re.MULTILINE)[:30],
        "function_lengths": [avg] * funcs,
    }

def _java(code):
    return {
        "functions": _c([r'(?:public|private|protected|static|final|synchronized|\s)+[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\{'], code, re.MULTILINE),
        "classes": _c([r'\b(?:class|interface|enum|record)\s+\w+'], code),
        "loops": _c([r'\bfor\s*\(', r'\bwhile\s*\(', r'\bdo\s*\{'], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\('], code),
        "imports": _f([r'^import\s+[\w.*]+;'], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }

def _go(code):
    return {
        "functions": _c([r'\bfunc\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s+)?\w+\s*\('], code),
        "classes": _c([r'\btype\s+\w+\s+struct\b', r'\btype\s+\w+\s+interface\b'], code),
        "loops": _c([r'\bfor\s+'], code),
        "conditionals": _c([r'\bif\s+', r'\bswitch\s+', r'\bselect\s*\{'], code),
        "imports": _f([r'"[\w./]+"'], code)[:30],
        "function_lengths": [],
    }

def _rust(code):
    return {
        "functions": _c([r'\bfn\s+\w+\s*(?:<[^>]*>)?\s*\('], code),
        "classes": _c([r'\bstruct\s+\w+', r'\benum\s+\w+', r'\btrait\s+\w+', r'\bimpl\s+\w+'], code),
        "loops": _c([r'\bfor\s+\w', r'\bwhile\s+', r'\bloop\s*\{'], code),
        "conditionals": _c([r'\bif\s+', r'\bmatch\s+'], code),
        "imports": _f([r'^use\s+[\w::{},\s*]+;'], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }

def _c_cpp(code):
    return {
        "functions": _c([r'^\w[\w\s*<>:]+\s+\w+\s*\([^;{]*\)\s*\{'], code, re.MULTILINE),
        "classes": _c([r'\bclass\s+\w+', r'\bstruct\s+\w+\s*\{', r'\benum\s+\w+\s*\{'], code),
        "loops": _c([r'\bfor\s*\(', r'\bwhile\s*\(', r'\bdo\s*\{'], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\('], code),
        "imports": _f([r'^#include\s*[<"].+[>"]'], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }

def _php(code):
    return {
        "functions": _c([r'\bfunction\s+\w+\s*\(',
                          r'\b(?:public|private|protected|static)\s+function\s+\w+\s*\('], code),
        "classes": _c([r'\b(?:class|interface|trait)\s+\w+'], code),
        "loops": _c([r'\bfor\s*\(', r'\bforeach\s*\(', r'\bwhile\s*\('], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\('], code),
        "imports": _f([r'\b(?:require|include|require_once|include_once)\s*[\'"(]'], code)[:30],
        "function_lengths": [],
    }

def _dart(code):
    return {
        "functions": _c([
            r'\b(?:void|Future|Stream|dynamic|int|String|bool|List|Map|Widget|[\w<>]+)\s+\w+\s*\([^)]*\)\s*(?:async\s*)?\{',
            r'\b\w+\s*\([^)]*\)\s*=>\s*',
        ], code, re.MULTILINE),
        "classes": _c([r'\bclass\s+\w+', r'\bmixin\s+\w+'], code),
        "loops": _c([r'\bfor\s*\(', r'\bfor\s+\w', r'\bwhile\s*\('], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\('], code),
        "imports": _f([r"^import\s+'[^']+'"], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }

def _ruby(code):
    return {
        "functions": _c([r'^\s*def\s+\w+'], code, re.MULTILINE),
        "classes": _c([r'^\s*class\s+\w+', r'^\s*module\s+\w+'], code, re.MULTILINE),
        "loops": _c([r'\b(?:each|map|times|upto|downto|loop)\b', r'\bwhile\b', r'\bfor\b'], code),
        "conditionals": _c([r'\bif\b', r'\bcase\b', r'\bunless\b'], code),
        "imports": _f([r"^require\s+['\"]", r"^require_relative\s+['\"]"], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }

def _cs(code):
    return {
        "functions": _c([r'(?:public|private|protected|internal|static|virtual|override|async|\s)+[\w<>\[\]?]+\s+\w+\s*\([^)]*\)\s*(?:where\s+[\w:,\s]+)?\{'], code, re.MULTILINE),
        "classes": _c([r'\b(?:class|interface|struct|enum|record)\s+\w+'], code),
        "loops": _c([r'\bfor\s*\(', r'\bforeach\s*\(', r'\bwhile\s*\(', r'\bdo\s*\{'], code),
        "conditionals": _c([r'\bif\s*\(', r'\bswitch\s*\('], code),
        "imports": _f([r'^using\s+[\w.]+;'], code, re.MULTILINE)[:30],
        "function_lengths": [],
    }


_REGEX_MAP = {
    ".js": _js, ".jsx": _js, ".ts": _js, ".tsx": _js,
    ".java": _java,
    ".go": _go,
    ".rs": _rust,
    ".c": _c_cpp, ".cpp": _c_cpp, ".h": _c_cpp, ".hpp": _c_cpp,
    ".php": _php,
    ".dart": _dart,
    ".rb": _ruby,
    ".cs": _cs,
}


def analyze_file(file_path):
    """
    Main entry point. Returns metrics dict or None for unsupported extensions.
    Tries Tree-sitter first, falls back to regex.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _REGEX_MAP and ext not in _TS_LANGS:
        return None

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    except Exception:
        return None

    if not code.strip():
        return {"functions": 0, "classes": 0, "loops": 0,
                "conditionals": 0, "imports": [], "function_lengths": []}

    # Try Tree-sitter first
    if _TS_OK and ext in _TS_LANGS:
        result = _ts_parse(ext, code)
        if result is not None:
            return result

    # Regex fallback
    fn = _REGEX_MAP.get(ext)
    if fn:
        try:
            return fn(code)
        except Exception:
            return None

    return None
