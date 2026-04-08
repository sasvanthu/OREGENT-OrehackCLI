import shutil
import os

from repo_handler.clone_repo import clone_repository
from repo_handler.repo_scanner import scan_repository
from repo_handler.file_classifier import classify_repository

from static_analysis.metrics_extractor import extract_repository_metrics

from graph_builder.module_graph import build_module_dependency_graph
from graph_builder.call_graph import build_function_call_graph

from context_engine.context_extractor import build_evaluation_context

from evaluation.project_understanding import run_project_understanding
from evaluation.technical_evaluation import run_technical_evaluation
from evaluation.problem_alignment import run_problem_alignment
from evaluation.final_evaluator import run_final_evaluation


def print_section(title):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


def run_pipeline(repo_url, problem_statement):

    repo_path = None

    try:
        print_section("1/8  Cloning repository")
        repo_path = clone_repository(repo_url)
        print(f"  Cloned to: {repo_path}")

        print_section("2/8  Scanning repository")
        scan_result = scan_repository(repo_path)
        print(f"  Total files found: {scan_result['total_files']}")

        print_section("3/8  Classifying files")
        classified = classify_repository(scan_result["files"])
        for category, files in classified.items():
            if files:
                print(f"  {category:<20} {len(files)} files")

        print_section("4/8  Static analysis")
        all_code_files = (
            classified["backend"]
            + classified["frontend"]
            + classified["source_code"]
        )
        metrics = extract_repository_metrics(all_code_files)
        has_real_analysis = metrics["files_analyzed"] > 0

        print(f"  Files analyzed (AST):      {metrics['files_analyzed']}")
        print(f"  Files analyzed (fallback): {metrics['files_fallback']}")
        print(f"  Files failed:              {metrics['files_failed']}")
        print(f"  Total functions:           {metrics['total_functions']}")
        print(f"  Total classes:             {metrics['total_classes']}")
        print(f"  Total loops:               {metrics['total_loops']}")
        print(f"  Total conditionals:        {metrics['total_conditionals']}")
        print(f"  Avg function length:       {metrics['avg_function_length']} lines")
        print(f"  Dependencies found:        {len(metrics['dependencies'])}")

        if not has_real_analysis:
            print(f"\n  [!] No AST analysis succeeded — only line counts available.")

        if metrics["files_analyzed"] == 0 and metrics["files_fallback"] == 0:
            print("\n  [!] Nothing to analyze. Evaluation aborted.")
            return None

        print_section("5/8  Building graphs")
        # Both graph builders return (graph, summary) tuples
        module_graph, module_summary = build_module_dependency_graph(all_code_files)
        call_graph,   call_summary   = build_function_call_graph(all_code_files)

        print(f"  Module graph  — files: {module_summary['total_files']}, "
              f"edges: {module_summary['total_edges']}")
        if module_summary['most_imported']:
            print(f"  Most imported: {module_summary['most_imported'][:5]}")
        print(f"  Call graph    — functions: {call_summary['total_functions']}, "
              f"calls: {call_summary['total_calls']}")
        if call_summary['most_called']:
            print(f"  Most called:   {call_summary['most_called'][:5]}")

        print_section("6/8  Building evaluation context")
        context = build_evaluation_context(
            repo_path,
            classified,
            metrics,
            module_graph,
            module_summary,
            call_graph,
            call_summary,
        )

        tech_stack = context.get("detected_tech_stack", {})
        print(f"  Tech stack detected: {list(tech_stack.keys())}")
        security = context.get("security_analysis", {})
        print(f"  Security issues:")
        print(f"    Dangerous calls:            {len(security.get('dangerous_calls', []))}")
        print(f"    Unsafe deserialization:     {len(security.get('unsafe_deserialization', []))}")
        print(f"    Hardcoded secrets:          {len(security.get('hardcoded_secrets', []))}")
        print(f"    Missing exception handlers: {security.get('missing_exception_handling', 0)}")

        # Show folder structure info
        fs = context.get("folder_structure", {})
        if fs:
            print(f"  Folder structure: {fs.get('unique_dirs', 0)} dirs, "
                  f"bonus={fs.get('folder_bonus', 0)}, "
                  f"layers={fs.get('named_layers', [])}")

        print_section("7/8  LLM evaluation")

        if has_real_analysis:
            print("  → Project understanding...")
            understanding = run_project_understanding(context)
            print(f"    Project type:     {understanding.get('project_type', 'N/A')}")
            print(f"    Problem summary:  {understanding.get('problem_summary', 'N/A')}")
            print(f"    Solution summary: {understanding.get('solution_summary', 'N/A')}")
            print(f"    Architecture:     {understanding.get('architecture_summary', 'N/A')}")
        else:
            print("  [!] Skipping project understanding — no AST analysis.")
            understanding = {
                "project_type": "unknown",
                "problem_summary": "No AST analysis available.",
                "solution_summary": "",
                "technologies_used": [],
                "architecture_summary": ""
            }

        print("\n  → Technical evaluation...")
        technical_result = run_technical_evaluation(context)
        print(f"    Code quality:     {technical_result.get('code_quality_score', 0)}/10")
        print(f"    Eng complexity:   {technical_result.get('engineering_complexity_score', 0)}/10")
        print(f"    Architecture:     {technical_result.get('architecture_quality_score', 0)}/10")
        print(f"    Reasoning:        {technical_result.get('reasoning', '')}")

        print("\n  → Problem alignment...")
        alignment_result = run_problem_alignment(context, problem_statement)
        print(f"    Alignment score:  {alignment_result.get('alignment_score', 0)}/10")
        print(f"    Reasoning:        {alignment_result.get('alignment_reasoning', '')}")
        matched = alignment_result.get("matched_requirements", [])
        missing = alignment_result.get("missing_requirements", [])
        if matched:
            print(f"    Matched:          {', '.join(str(r) for r in matched)}")
        if missing:
            print(f"    Missing:          {', '.join(str(r) for r in missing)}")

        print_section("8/8  Final evaluation (2-pass)")

        # Pass alignment_score so problem_alignment field is anchored correctly
        final_result = run_final_evaluation(
            context,
            problem_statement,
            alignment_score=alignment_result.get("alignment_score")
        )

        if "error" in final_result and final_result.get("final_score", 0) == 0:
            print(f"\n  [!] {final_result['error']}")
        else:
            te  = final_result.get("technical_evaluation",    {})
            ie  = final_result.get("innovation_evaluation",   {})
            ce  = final_result.get("completeness_evaluation", {})
            rsn = final_result.get("reasoning", {})
            anc = final_result.get("anchors_used", {})
            rev = final_result.get("review_notes", "")

            print("\n  Technical Scores (65 pts):")
            print(f"    Functionality:           {te.get('functionality', 0)}/10")
            print(f"    Tech stack efficiency:   {te.get('tech_stack_efficiency', 0)}/8")
            print(f"    Code quality/modularity: {te.get('code_quality_modularity', 0)}/15")
            print(f"    Code readability:        {te.get('code_readability', 0)}/10")
            print(f"    Error handling:          {te.get('error_handling', 0)}/7")
            print(f"    Documentation:           {te.get('documentation', 0)}/10")
            print(f"    Security:                {te.get('security', 0)}/5")

            print("\n  Innovation Scores (25 pts):")
            print(f"    Feasibility:             {ie.get('feasibility', 0)}/8")
            print(f"    Novelty:                 {ie.get('novelty', 0)}/6")
            print(f"    Problem alignment:       {ie.get('problem_alignment', 0)}/6")
            print(f"    Scalability:             {ie.get('scalability', 0)}/3")
            print(f"    Product features:        {ie.get('product_features', 0)}/2")

            print("\n  Completeness Scores (10 pts):")
            print(f"    Feature completeness:    {ce.get('feature_completeness', 0)}/5")
            print(f"    Project polish:          {ce.get('project_polish', 0)}/3")
            print(f"    Deployment readiness:    {ce.get('deployment_readiness', 0)}/2")

            if rsn:
                print(f"\n  Strengths:  {rsn.get('strengths', '')}")
                print(f"  Weaknesses: {rsn.get('weaknesses', '')}")
                print(f"  Summary:    {rsn.get('overall_summary', '')}")

            if rev:
                print(f"\n  Reviewer notes: {rev}")

            if anc:
                sd = anc.get("security_deductions", {})
                mod_bk = anc.get("computed_modularity_breakdown", {})
                print(f"\n  Anchor scores:")
                print(f"    Security:       {anc.get('computed_security_score', 'N/A')}/5")
                print(f"    Error handling: {anc.get('computed_error_handling_score', 'N/A')}/7")
                print(f"    Has real AST:   {anc.get('has_real_analysis', False)}")
                print(f"    Is sec tool:    {anc.get('is_security_tool', False)}")
                print(f"    Modularity:     {mod_bk.get('func_count_base',0)} func "
                      f"+ {mod_bk.get('folder_bonus',0)} folder "
                      f"+ {mod_bk.get('connectivity_bonus',0)} connectivity "
                      f"= {mod_bk.get('total',0)}/15")
                print(f"    ({sd.get('hardcoded_secrets', 0)} secrets, "
                      f"{sd.get('dangerous_calls', 0)} dangerous calls, "
                      f"{sd.get('missing_exception_handlers', 0)} missing handlers)")

        print(f"\n{'═' * 50}")
        print(f"  FINAL SCORE:    {final_result.get('final_score', 0)} / {final_result.get('max_total', 100)}")
        print(f"  Technical:      {final_result.get('technical_total', 0)} / {final_result.get('max_technical', 65)}")
        print(f"  Innovation:     {final_result.get('innovation_total', 0)} / {final_result.get('max_innovation', 25)}")
        print(f"  Completeness:   {final_result.get('completeness_total', 0)} / {final_result.get('max_completeness', 10)}")
        print(f"{'═' * 50}")

        return {
            "understanding": understanding,
            "technical":     technical_result,
            "alignment":     alignment_result,
            "final":         final_result,
            "context":       context,
        }

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        raise

    finally:
        if repo_path and os.path.exists(repo_path):
            print("\nCleaning up temporary repository...")
            shutil.rmtree(repo_path, ignore_errors=True)


if __name__ == "__main__":
    repo_url          = input("Enter GitHub repository URL: ").strip()
    problem_statement = input("Enter problem statement: ").strip()
    run_pipeline(repo_url, problem_statement)