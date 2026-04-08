import re

from llm.ollama_client import call_ollama
from utils.kv_parser import parse_kv, get_str


def build_technical_prompt(context):
    m        = context.get("code_metrics", {})
    tech     = list(context.get("detected_tech_stack", {}).keys())
    snippets = context.get("code_snippets", [])
    sec      = context.get("security_analysis", {})
    funcs    = m.get("total_functions",     0)
    classes  = m.get("total_classes",       0)
    avg      = m.get("avg_function_length", 0)
    total    = m.get("files_analyzed", 0) + m.get("files_fallback", 0)
    loops    = m.get("total_loops", 0)
    conds    = m.get("total_conditionals", 0)

    secrets   = len(sec.get("hardcoded_secrets", []))
    dangerous = len(sec.get("dangerous_calls", []))
    missing_h = sec.get("missing_exception_handling", 0)
    sec_note  = f"{secrets} hardcoded secrets, {dangerous} dangerous calls, {missing_h} missing error handlers"

    snip = ""
    for s in snippets[:2]:
        lines = s.get("snippet", "").splitlines()[:5]
        snip += f"[{s.get('file','')}]\n" + "\n".join(lines) + "\n"

    cg = context.get("call_graph_summary", {})
    calls_per_f = round(cg.get("total_calls", 0) / funcs, 1) if funcs > 0 else 0

    return f"""Rate this project's code quality. Reply as name=number lines only.

EVIDENCE:
files={total} functions={funcs} classes={classes} loops={loops} conditionals={conds}
avg_fn_length={avg} calls_per_function={calls_per_f} tech={tech}
security_issues={sec_note}

CODE SAMPLES:
{snip}

code_quality_score= (0-10: clean code, naming, structure visible in samples)
engineering_complexity_score= (0-10: algorithm difficulty, calls_per_function={calls_per_f} indicates complexity)
architecture_quality_score= (0-10: separation of concerns, layers in code)
reasoning= (one specific sentence about this code, not generic)"""


def _is_uniform_fail(result):
    """LLM returned same value for all three — it didn't read the evidence."""
    vals = [
        result.get("code_quality_score", 0),
        result.get("engineering_complexity_score", 0),
        result.get("architecture_quality_score", 0),
    ]
    return len(set(vals)) == 1 and 0 < vals[0] <= 5


def run_technical_evaluation(context):
    files_a = context.get("code_metrics", {}).get("files_analyzed", 0)
    files_f = context.get("code_metrics", {}).get("files_fallback", 0)

    if files_a == 0 and files_f == 0:
        return {"code_quality_score": 0, "engineering_complexity_score": 0,
                "architecture_quality_score": 0, "reasoning": "No files found."}

    m        = context.get("code_metrics", {})
    tech     = list(context.get("detected_tech_stack", {}).keys())
    funcs    = m.get("total_functions", 0)
    classes  = m.get("total_classes",  0)
    avg      = m.get("avg_function_length", 0)
    total    = files_a + files_f
    conds    = m.get("total_conditionals", 0)
    cg       = context.get("call_graph_summary", {})
    calls    = cg.get("total_calls", 0)

    raw    = call_ollama(build_technical_prompt(context))
    fields = ["code_quality_score", "engineering_complexity_score", "architecture_quality_score"]

    # Smart fallbacks based on actual metrics
    conds_per_f  = conds / funcs if funcs > 0 else 0
    calls_per_f  = calls / funcs if funcs > 0 else 0

    # code_quality: avg function length — shorter = cleaner
    if avg < 15 and classes >= 2:   cq_fb = 7
    elif avg < 25:                  cq_fb = 6
    elif avg < 40:                  cq_fb = 5
    else:                           cq_fb = 4

    # engineering_complexity: calls per function is the real signal
    if calls_per_f > 6:             ec_fb = 7
    elif calls_per_f > 3:           ec_fb = 6
    elif conds_per_f > 3:           ec_fb = 6
    elif conds_per_f > 1.5:         ec_fb = 5
    elif len(tech) >= 3:            ec_fb = 5
    else:                           ec_fb = 4

    # architecture: class count + tech breadth
    if classes >= 5 and len(tech) >= 3: aq_fb = 7
    elif classes >= 2 or len(tech) >= 3: aq_fb = 6
    else:                                aq_fb = 5

    fb = {"code_quality_score": cq_fb,
          "engineering_complexity_score": ec_fb,
          "architecture_quality_score": aq_fb}

    parsed = parse_kv(raw, fields, fb)
    result = {}
    for key in fields:
        val = parsed.get(key, fb.get(key, 3))
        result[key] = round(min(max(float(val), 0), 10), 1)

    # Detect uniform fail (LLM returned same value for all three)
    if _is_uniform_fail(result):
        result["code_quality_score"]           = float(cq_fb)
        result["engineering_complexity_score"] = float(ec_fb)
        result["architecture_quality_score"]   = float(aq_fb)

    reasoning = get_str(parsed, 'reasoning', default="")
    if not reasoning or "hard to provide" in reasoning.lower() or len(reasoning) < 15:
        reasoning = (f"{total} files, {funcs} functions, avg {avg} lines/fn, "
                     f"{calls_per_f:.1f} calls/function, {len(tech)} tech categories.")
    result["reasoning"] = reasoning

    return result