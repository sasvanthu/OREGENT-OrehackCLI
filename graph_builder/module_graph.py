"""
module_graph.py  —  graph_builder/module_graph.py

Builds a module dependency graph for ALL languages:
  Python  : ast.Import / ast.ImportFrom  (precise)
  JS/TS   : import ... from / require()  (regex)
  Java    : import statement             (regex)
  Go      : import block                 (regex)
  Rust    : use statement                (regex)
  C/C++   : #include                     (regex)
  C#      : using statement              (regex)
  PHP     : require/include/use          (regex)
  Dart    : import statement             (regex)
  Ruby    : require/require_relative     (regex)
  Kotlin  : import statement             (regex)
  Swift   : import statement             (regex)

Returns: (graph, summary)
  graph   : {module_name: [dep1, dep2, ...]}
  summary : {total_files, total_edges, most_imported}
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


# ── Per-language import extractors ────────────────────────────────────────────

def _imports_python(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        deps = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.append(node.module.split(".")[0])
        return deps
    except Exception:
        return []


def _imports_js(src):
    """JS/TS: import X from 'Y'  |  import 'Y'  |  require('Y')"""
    deps = []
    # ES6 import
    for m in re.finditer(r'''import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]''', src):
        dep = m.group(1)
        # Normalize: strip relative path to just the module name
        dep = dep.lstrip('./').lstrip('../').split('/')[0]
        if dep and not dep.startswith('.'):
            deps.append(dep)
        elif dep:
            deps.append(dep.split('/')[-1] or dep)
    # CommonJS require
    for m in re.finditer(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''', src):
        dep = m.group(1).lstrip('./').lstrip('../').split('/')[0]
        deps.append(dep)
    return deps


def _imports_java(src):
    """Java: import com.example.Thing;"""
    deps = []
    for m in re.finditer(r'^import\s+([\w.]+)\s*;', src, re.MULTILINE):
        parts = m.group(1).split('.')
        # Top-level package
        deps.append(parts[0] if len(parts) == 1 else '.'.join(parts[:2]))
    return deps


def _imports_go(src):
    """Go: import "pkg"  |  import ( "pkg1" "pkg2" )"""
    deps = []
    # Single import
    for m in re.finditer(r'^import\s+"([^"]+)"', src, re.MULTILINE):
        deps.append(m.group(1).split('/')[-1])
    # Import block
    block = re.search(r'import\s*\(([^)]+)\)', src, re.DOTALL)
    if block:
        for m in re.finditer(r'"([^"]+)"', block.group(1)):
            deps.append(m.group(1).split('/')[-1])
    return deps


def _imports_rust(src):
    """Rust: use std::collections::HashMap;  |  extern crate name;"""
    deps = []
    for m in re.finditer(r'^use\s+([\w:]+)', src, re.MULTILINE):
        deps.append(m.group(1).split('::')[0])
    for m in re.finditer(r'^extern\s+crate\s+(\w+)', src, re.MULTILINE):
        deps.append(m.group(1))
    return deps


def _imports_c(src):
    """C/C++: #include <stdio.h>  |  #include "myfile.h" """
    deps = []
    for m in re.finditer(r'#include\s+[<"]([^>"]+)[>"]', src):
        dep = m.group(1).split('/')[-1].replace('.h', '')
        deps.append(dep)
    return deps


def _imports_csharp(src):
    """C#: using System.Collections;"""
    deps = []
    for m in re.finditer(r'^using\s+([\w.]+)\s*;', src, re.MULTILINE):
        parts = m.group(1).split('.')
        deps.append(parts[0])
    return deps


def _imports_php(src):
    """PHP: require/include 'file.php'  |  use Namespace\\Class;"""
    deps = []
    for m in re.finditer(r'''(?:require|include)(?:_once)?\s*[('"]([^'"()]+)['")]''', src):
        dep = os.path.basename(m.group(1)).replace('.php', '')
        deps.append(dep)
    for m in re.finditer(r'^use\s+([\w\\]+)', src, re.MULTILINE):
        parts = m.group(1).replace('\\', '/').split('/')
        deps.append(parts[0])
    return deps


def _imports_dart(src):
    """Dart: import 'package:flutter/material.dart';"""
    deps = []
    for m in re.finditer(r'''import\s+['"]([^'"]+)['"]''', src):
        dep = m.group(1)
        if dep.startswith('package:'):
            deps.append(dep.split('/')[0].replace('package:', ''))
        else:
            deps.append(os.path.basename(dep).replace('.dart', ''))
    return deps


def _imports_ruby(src):
    """Ruby: require 'json'  |  require_relative 'my_file'"""
    deps = []
    for m in re.finditer(r'''require(?:_relative)?\s+['"]([^'"]+)['"]''', src):
        deps.append(m.group(1).split('/')[-1].replace('.rb', ''))
    return deps


def _imports_kotlin(src):
    """Kotlin: import com.example.Thing"""
    deps = []
    for m in re.finditer(r'^import\s+([\w.]+)', src, re.MULTILINE):
        parts = m.group(1).split('.')
        deps.append(parts[0] if len(parts) == 1 else '.'.join(parts[:2]))
    return deps


def _imports_swift(src):
    """Swift: import UIKit"""
    deps = []
    for m in re.finditer(r'^import\s+(\w+)', src, re.MULTILINE):
        deps.append(m.group(1))
    return deps


def _extract_imports(path, lang):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except Exception:
        return []

    if lang == "python":
        return _imports_python(path)
    elif lang in ("javascript", "typescript"):
        return _imports_js(src)
    elif lang == "java":
        return _imports_java(src)
    elif lang == "go":
        return _imports_go(src)
    elif lang == "rust":
        return _imports_rust(src)
    elif lang in ("c", "cpp"):
        return _imports_c(src)
    elif lang == "csharp":
        return _imports_csharp(src)
    elif lang == "php":
        return _imports_php(src)
    elif lang == "dart":
        return _imports_dart(src)
    elif lang == "ruby":
        return _imports_ruby(src)
    elif lang == "kotlin":
        return _imports_kotlin(src)
    elif lang == "swift":
        return _imports_swift(src)
    return []


# ── Main builder ──────────────────────────────────────────────────────────────

def build_module_dependency_graph(source_files):
    """
    Build module dependency graph for all languages.

    Returns
    -------
    (graph, summary)
      graph   : {filename: [import1, import2, ...]}
      summary : {total_files, total_edges, most_imported}
    """
    graph = {}
    all_deps = []

    for path in source_files:
        lang = _get_lang(path)
        if lang is None:
            continue

        module_name = os.path.basename(path)
        deps = _extract_imports(path, lang)
        # Deduplicate per file
        deps = list(dict.fromkeys(deps))
        graph[module_name] = deps
        all_deps.extend(deps)

    # Build summary
    counter = Counter(all_deps)
    total_edges = sum(len(v) for v in graph.values())
    most_imported = [dep for dep, _ in counter.most_common(10)]

    summary = {
        "total_files":    len(graph),
        "total_edges":    total_edges,
        "most_imported":  most_imported,
    }

    return graph, summary