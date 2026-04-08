"""
context_extractor.py  -  context_engine/context_extractor.py
Assembles the full evaluation context dict passed to all LLM modules.
Now includes folder_structure_summary for modularity scoring.
"""

import os

from context_engine.snippet_selector import extract_code_snippets
from evaluation.security.security_analyzer import analyze_security
from evaluation.techstack.tech_stack_analyzer import detect_tech_stack


def extract_readme_text(doc_files):
    for file_path in doc_files:
        filename = os.path.basename(file_path).lower()
        if "readme" in filename:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception:
                continue
    return ""


def analyze_folder_structure(all_code_files, repo_path):
    """
    Analyzes the folder/directory structure of the repository.
    Returns signals used to assess structural modularity.

    Good structure = files organized into named layers/modules, not all in root.
    """
    dirs = set()
    files_in_root = 0

    for fp in all_code_files:
        # Make path relative to repo_path
        try:
            rel = os.path.relpath(fp, repo_path)
        except ValueError:
            rel = fp

        parts = rel.replace("\\", "/").split("/")
        if len(parts) == 1:
            files_in_root += 1
        else:
            # Record directory (first-level folder)
            dirs.add(parts[0])

    n_dirs    = len(dirs)
    max_depth = 0
    for fp in all_code_files:
        try:
            rel = os.path.relpath(fp, repo_path)
        except ValueError:
            rel = fp
        depth = len(rel.replace("\\", "/").split("/")) - 1
        max_depth = max(max_depth, depth)

    total_files = len(all_code_files)
    pct_in_root = files_in_root / total_files if total_files > 0 else 1.0

    # Named layer detection — folders that indicate architectural separation
    LAYER_NAMES = {
        "api", "routes", "controllers", "handlers",
        "services", "service",
        "models", "model", "schemas",
        "utils", "util", "helpers", "lib",
        "core", "common",
        "backend", "frontend", "client", "server",
        "repo_handler", "graph_builder", "context_engine",
        "static_analysis", "evaluation", "security", "analysis",
        "components", "pages", "views", "hooks",
    }
    named_layers = [d.lower() for d in dirs if d.lower() in LAYER_NAMES]

    # Folder modularity bonus (0-3 extra points to add to modularity_base)
    if n_dirs >= 5 and max_depth >= 2 and len(named_layers) >= 3:
        folder_bonus = 3   # excellent structure (like OreHack)
    elif n_dirs >= 4 or (n_dirs >= 3 and len(named_layers) >= 2):
        folder_bonus = 2   # good structure
    elif n_dirs >= 2:
        folder_bonus = 1   # basic separation
    else:
        folder_bonus = 0   # everything in root

    return {
        "unique_dirs":     n_dirs,
        "max_depth":       max_depth,
        "files_in_root":   files_in_root,
        "pct_in_root":     round(pct_in_root, 2),
        "named_layers":    named_layers,
        "folder_bonus":    folder_bonus,
    }


def build_evaluation_context(
    repo_path,
    classified_files,
    metrics,
    module_graph,
    module_summary,
    call_graph,
    call_summary,
):
    readme_text = extract_readme_text(classified_files["documentation"])

    all_code_files = (
        classified_files["backend"]
        + classified_files["frontend"]
        + classified_files["source_code"]
    )

    snippets             = extract_code_snippets(all_code_files)
    security_analysis    = analyze_security(repo_path)
    detected_tech_stack  = detect_tech_stack(repo_path, metrics, classified_files)
    folder_structure     = analyze_folder_structure(all_code_files, repo_path)

    context = {
        "project_description":   readme_text[:2000],
        "code_metrics":          metrics,
        "module_graph_summary":  module_summary,
        "call_graph_summary":    call_summary,
        "_module_graph_full":    module_graph,
        "_call_graph_full":      call_graph,
        "code_snippets":         snippets,
        "security_analysis":     security_analysis,
        "detected_tech_stack":   detected_tech_stack,
        "folder_structure":      folder_structure,
    }

    return context