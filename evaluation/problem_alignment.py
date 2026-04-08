import re

from llm.ollama_client import call_ollama
from utils.kv_parser import parse_kv, get_str


def build_alignment_prompt(context, problem_statement):
    """
    Compact alignment prompt.
    Asks for matched/missing as SHORT comma-separated items, not full sentences,
    to prevent the model from echoing the entire problem statement.
    Output needed: ~40 tokens. At 3 tok/s = 13 seconds.
    """
    tech    = list(context.get("detected_tech_stack", {}).keys())
    readme  = context.get("project_description", "")[:200]
    metrics = context.get("code_metrics", {})
    snips   = context.get("code_snippets", [])
    funcs   = [s.get("function_name", "") for s in snips if s.get("function_name")]
    total   = metrics.get("files_analyzed", 0) + metrics.get("files_fallback", 0)

    return f"""Score how well this project matches the problem. Reply as name=value lines only.

PROBLEM: {problem_statement}

PROJECT SIGNALS:
  files={total}, tech={tech}
  key_functions={funcs[:6]}
  readme={readme}

Score 0-10 where:
  0-3 = unrelated or barely matches
  4-6 = partially matches, some features present
  7-9 = strongly matches, most requirements covered
  10  = perfect match

alignment_score=
reasoning= (one sentence why)
matched= (comma-separated short requirement names that ARE present)
missing= (comma-separated short requirement names that are ABSENT)"""


def run_problem_alignment(context, problem_statement):

    files_a = context.get("code_metrics", {}).get("files_analyzed", 0)
    files_f = context.get("code_metrics", {}).get("files_fallback", 0)

    if files_a == 0 and files_f == 0:
        return {
            "alignment_score":      0,
            "alignment_reasoning":  "No files found.",
            "matched_requirements": [],
            "missing_requirements": [],
        }

    raw    = call_ollama(build_alignment_prompt(context, problem_statement))
    tech   = list(context.get("detected_tech_stack", {}).keys())
    total  = files_a + files_f
    fb     = {"alignment_score": 3 if (tech and total > 0) else 0}

    parsed = parse_kv(raw, ["alignment_score"], fb)

    score = float(parsed.get("alignment_score", fb["alignment_score"]))
    score = min(max(round(score, 1), 0), 10)

    reasoning = get_str(parsed, 'reasoning',
                        default="Alignment assessed from tech stack and function names.")

    # Parse matched/missing — comma-separated short items
    matched = []
    missing = []
    if raw:
        for line in raw.splitlines():
            line = line.strip()
            if not line or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip().lower()
            val = val.strip().strip('"\'')
            if key == 'matched' and val:
                # Only keep items that are short (not the entire problem statement echoed)
                items = [v.strip() for v in re.split(r'[,;]', val) if v.strip()]
                matched = [i for i in items if len(i) < 80]
            elif key == 'missing' and val:
                items = [v.strip() for v in re.split(r'[,;]', val) if v.strip()]
                missing = [i for i in items if len(i) < 80]

    # Remove known placeholder strings
    bad = {
        "requirement 1", "requirement 2", "requirement 3",
        "matched requirement", "missing requirement",
    }
    matched = [r for r in matched if r.lower() not in bad and r.lower() != 'none']
    missing = [r for r in missing if r.lower() not in bad and r.lower() != 'none']

    return {
        "alignment_score":      score,
        "alignment_reasoning":  reasoning,
        "matched_requirements": matched,
        "missing_requirements": missing,
    }