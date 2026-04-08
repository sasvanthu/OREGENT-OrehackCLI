import re

from llm.ollama_client import call_ollama
from llm.prompt_builder import build_project_understanding_prompt


def _parse_understanding(text):
    result = {
        "project_type":         "web app",
        "problem_summary":      "",
        "solution_summary":     "",
        "technologies_used":    [],
        "architecture_summary": "",
    }
    if not text:
        return result

    for line in text.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip().lower()
        val = val.strip()
        if not val:
            continue
        if key == 'project_type':
            result['project_type'] = val
        elif key == 'problem_summary':
            result['problem_summary'] = val
        elif key == 'solution_summary':
            result['solution_summary'] = val
        elif key in ('technologies', 'technologies_used'):
            result['technologies_used'] = [t.strip() for t in re.split(r'[,;]', val) if t.strip()]
        elif key == 'architecture':
            result['architecture_summary'] = val

    return result


def run_project_understanding(context):
    if context.get("code_metrics", {}).get("files_analyzed", 0) == 0:
        return {
            "project_type": "unknown",
            "problem_summary": "No files analyzed.",
            "solution_summary": "",
            "technologies_used": [],
            "architecture_summary": ""
        }

    prompt = build_project_understanding_prompt(context)
    raw    = call_ollama(prompt)
    result = _parse_understanding(raw)

    # Use tech stack as fallback if LLM gave nothing useful
    if not result["problem_summary"] or len(result["problem_summary"]) < 10:
        tech = list(context.get("detected_tech_stack", {}).keys())
        funcs = context.get("code_metrics", {}).get("total_functions", 0)
        files = context.get("code_metrics", {}).get("files_analyzed", 0)
        result["problem_summary"]  = f"Project with {files} files and {funcs} functions using {tech} stack."
        result["technologies_used"] = tech

    return result