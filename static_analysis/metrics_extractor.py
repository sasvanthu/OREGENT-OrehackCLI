from static_analysis.ast_parser import analyze_python_file
from analysis.multilang_analyzer import analyze_file


def _count_lines(file_path):
    """Fallback: count lines when AST parsing fails."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def extract_repository_metrics(source_files):
    """
    Extracts aggregated code metrics from all source files.
    Python → native ast_parser.
    All others → Tree-sitter multilang_analyzer.
    Falls back to line count if both fail.
    """

    total_functions = 0
    total_classes = 0
    total_loops = 0
    total_conditionals = 0
    total_lines = 0

    all_imports = set()
    function_lengths = []
    analyzed_files = 0
    fallback_files = 0
    failed_files = 0

    for file_path in source_files:

        if file_path.endswith(".py"):
            result = analyze_python_file(file_path)
        else:
            result = analyze_file(file_path)

        if result is not None:
            analyzed_files += 1
            total_functions += result.get("functions", 0)
            total_classes += result.get("classes", 0)
            total_loops += result.get("loops", 0)
            total_conditionals += result.get("conditionals", 0)

            imports = result.get("imports", [])
            if isinstance(imports, list):
                all_imports.update(imports)

            function_lengths.extend(result.get("function_lengths", []))

        else:
            lines = _count_lines(file_path)
            if lines > 0:
                total_lines += lines
                fallback_files += 1
            else:
                failed_files += 1

    avg_function_length = (
        round(sum(function_lengths) / len(function_lengths), 2)
        if function_lengths
        else 0
    )

    return {
        "files_analyzed": analyzed_files,
        "files_fallback": fallback_files,
        "files_failed": failed_files,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "total_loops": total_loops,
        "total_conditionals": total_conditionals,
        "avg_function_length": avg_function_length,
        "total_lines_counted": total_lines,
        "dependencies": list(all_imports),
    }
