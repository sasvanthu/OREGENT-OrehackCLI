"""
final_evaluator.py  -  evaluation/final_evaluator.py
Scoring: 100pts = Technical(65) + Innovation(25) + Completeness(10)

Changes in this version:
  - product_features cap: funcs>=40 (was >=50) — fairer for complete small tools
  - novelty hint: boosted for database+complex projects
  - strengths/weaknesses moved BEFORE scores in prompt — LLM always generates them
  - Reviewer only touches technical scores
  - alignment_score forced as anchor
"""
import re
from llm.ollama_client import call_json, call_reviewer
from utils.kv_parser import parse_kv, get_str

SCORE_LIMITS = {
    "technical_evaluation": {
        "functionality": 10, "tech_stack_efficiency": 8,
        "code_quality_modularity": 15, "code_readability": 10,
        "error_handling": 7, "documentation": 10, "security": 5,
    },
    "innovation_evaluation": {
        "feasibility": 8, "novelty": 6, "problem_alignment": 6,
        "scalability": 3, "product_features": 2,
    },
    "completeness_evaluation": {
        "feature_completeness": 5, "project_polish": 3, "deployment_readiness": 2,
    },
}
MAX_TECHNICAL = 65; MAX_INNOVATION = 25; MAX_COMPLETENESS = 10; MAX_TOTAL = 100

TOOL_IMPORTS = {"subprocess","os","shutil","tempfile","nmap","semgrep","bandit",
                "scapy","paramiko","socket","ssl"}
SCANNER_KEYWORDS = {"scan","vuln","security","pentest","exploit","audit",
                    "sast","dast","injection","payload","cve"}


def _is_security_tool(context, tech_keys, tech_detail):
    for cat in tech_keys:
        if any(kw in cat.lower() for kw in SCANNER_KEYWORDS): return True
    for libs in tech_detail.values():
        if isinstance(libs, list):
            for lib in libs:
                if any(kw in lib.lower() for kw in SCANNER_KEYWORDS): return True
    mg = context.get("module_graph_summary", {})
    if sum(1 for i in mg.get("most_imported", []) if i in TOOL_IMPORTS) >= 3:
        return True
    for fn in context.get("call_graph_summary", {}).get("most_called", []):
        if any(kw in fn.lower() for kw in SCANNER_KEYWORDS): return True
    if sum(1 for kw in SCANNER_KEYWORDS
           if kw in context.get("project_description","").lower()) >= 2:
        return True
    return False


def _fix_truncation(text):
    if not text: return text
    text = text.strip()
    if text and text[-1] not in '.!?,;:' and (text[-1].isalnum() or text[-1] in ')"\''):
        text += "..."
    return text


def _build_anchors(context, has_real, has_fallback, alignment_score=None):
    m   = context.get("code_metrics", {})
    sec = context.get("security_analysis", {})
    mg  = context.get("module_graph_summary", {})
    cg  = context.get("call_graph_summary", {})
    fs  = context.get("folder_structure", {})

    funcs      = m.get("total_functions", 0)
    classes    = m.get("total_classes", 0)
    avg_len    = m.get("avg_function_length", 0)
    f_analyzed = m.get("files_analyzed", 0)
    f_fallback = m.get("files_fallback", 0)
    total_f    = f_analyzed + f_fallback
    loops      = m.get("total_loops", 0)
    conds      = m.get("total_conditionals", 0)

    dangerous = len(sec.get("dangerous_calls", []))
    unsafe    = len(sec.get("unsafe_deserialization", []))
    secrets   = len(sec.get("hardcoded_secrets", []))
    missing_h = sec.get("missing_exception_handling", 0)

    has_readme = bool(context.get("project_description", "").strip())
    has_snips  = len(context.get("code_snippets", [])) > 0
    tech       = context.get("detected_tech_stack", {})
    tech_keys  = list(tech.keys())
    is_sec     = _is_security_tool(context, tech_keys, tech)

    # Security anchor
    if has_real:
        dp    = dangerous * 0.2 if is_sec else dangerous * 0.5
        up    = unsafe    * 0.2 if is_sec else unsafe    * 0.5
        sec_s = round(max(0.0, min(5.0, 5.0 - secrets*1.0 - dp - up)), 1)
    elif has_fallback:
        sec_s = round(max(0.0, min(2.5, 2.5 - secrets*1.0)), 1)
    else:
        sec_s = 0.0

    # Error handling anchor
    if has_real and funcs > 0:
        err_s = round(max(0.0, min(7.0, 7.0*(1.0 - missing_h/funcs))), 1)
    elif has_real and funcs == 0:
        err_s = 5.0
    elif has_fallback:
        err_s = 3.5
    else:
        err_s = 0.0

    # Modularity = function base + folder bonus + connectivity bonus
    folder_bonus = fs.get("folder_bonus", 0)
    if   funcs >= 200: func_mod = 14
    elif funcs >= 100: func_mod = 13
    elif funcs >= 50:  func_mod = 12
    elif funcs >= 20:  func_mod = 11
    elif funcs >= 10 and classes >= 2: func_mod = 10
    elif funcs >= 10:  func_mod = 9
    elif funcs >= 5:   func_mod = 8
    elif funcs >= 2:   func_mod = 6
    elif has_fallback and total_f >= 30: func_mod = 6
    elif has_fallback and total_f >= 10: func_mod = 5
    elif has_fallback: func_mod = 4
    else:              func_mod = 3 if has_real else 0
    n_edges = mg.get("total_edges", 0)
    n_files = mg.get("total_files", 1)
    connectivity = n_edges / n_files if n_files > 0 else 0
    conn_bonus = 1 if 1.0 <= connectivity <= 4.0 else 0
    mod = min(15, func_mod + folder_bonus + conn_bonus)

    # Documentation base
    if has_real:
        doc = min(10, (5 if has_readme else 1) + (3 if has_snips else 0))
    elif has_fallback:
        doc = min(8,  (5 if has_readme else 2) + (2 if has_snips else 0))
    else:
        doc = 2 if has_readme else 0

    # Completeness anchors
    if   funcs >= 100 or total_f >= 80: feat_c = 5
    elif funcs >= 40  or total_f >= 40: feat_c = 4
    elif funcs >= 15  or total_f >= 20: feat_c = 3
    elif funcs >= 5   or total_f >= 10: feat_c = 2
    else:                               feat_c = 1
    polish = min(3, (2 if has_readme else 0) + (1 if has_snips else 0))
    deploy = 1

    # Alignment anchor
    if alignment_score is not None:
        align_anchored = round(max(1.0, min(6.0, alignment_score*6/10)), 1)
    else:
        align_anchored = None

    tech_floor = min(8, len(tech_keys)*2)

    # FIX 1: product_features cap — funcs>=40 (not >=50)
    # A complete 49-function tool deserves product_features=2
    scale_cap = 3 if funcs >= 100 else 2
    prod_cap  = 2 if funcs >= 40  else 1

    # Complexity score
    total_calls = cg.get("total_calls", 0)
    calls_per_f = total_calls / funcs if funcs > 0 else 0
    conds_per_f = conds       / funcs if funcs > 0 else 0
    complexity  = round(calls_per_f + conds_per_f, 1)

    n_tech = len(tech_keys)
    has_db = "database" in tech_keys

    func_h = ("8-9" if funcs>=150 else "7-8" if funcs>=80 else "6-7" if funcs>=40
              else "5-6" if funcs>=15 else "4-5" if funcs>=5 else "2-4")
    tech_h = ("6-7" if n_tech>=4 else "5-6" if n_tech==3 else
              "4-5" if n_tech==2 else "3-4" if n_tech==1 else "2-3")

    if total_f >= 80 or funcs >= 100:     fh = "6-7"
    elif complexity >= 8 and n_tech >= 2: fh = "5-6"
    elif complexity >= 5 and n_tech >= 2: fh = "4-5"
    elif n_tech >= 2 and total_f >= 15:   fh = "4-5"
    else:                                 fh = "3-4"

    # FIX 2: novelty hint — boost for database projects and complex tools
    # A hackathon evaluator with DB or a scanner with AI integration is more novel
    if complexity >= 8 and n_tech >= 3:                       nh = "4-5"
    elif (complexity >= 5 or n_tech >= 3) and has_db:         nh = "4-5"
    elif complexity >= 5 or n_tech >= 3:                      nh = "3-4"
    else:                                                     nh = "3-4"

    if align_anchored is not None:
        av = int(align_anchored)
        ah = f"{max(1,av-1)}-{min(6,av+1)}"
    elif n_tech >= 2 and total_f >= 30: ah = "4-5"
    elif n_tech >= 1 and total_f >= 10: ah = "3-4"
    else:                               ah = "2-3"

    sh = "2-3" if (n_tech >= 3 and complexity >= 5) else "1-2"
    ph = f"1-2" if n_tech >= 2 else "1"

    return {
        "computed_security_score":       sec_s,
        "computed_error_handling_score": err_s,
        "computed_modularity_base":      mod,
        "computed_modularity_breakdown": {"func_count_base": func_mod,
                                          "folder_bonus": folder_bonus,
                                          "connectivity_bonus": conn_bonus,
                                          "total": mod},
        "computed_doc_base":      doc,
        "computed_feat_complete": feat_c,
        "computed_polish":        polish,
        "computed_deploy":        deploy,
        "computed_align_anchored": align_anchored,
        "computed_tech_floor":    tech_floor,
        "computed_scale_cap":     scale_cap,
        "computed_prod_cap":      prod_cap,
        "has_real_analysis":      has_real,
        "has_fallback_only":      has_fallback,
        "is_security_tool":       is_sec,
        "complexity_score":       complexity,
        "hints": {
            "functionality": func_h, "tech_stack_efficiency": tech_h,
            "feasibility": fh, "novelty": nh, "problem_alignment": ah,
            "scalability": sh, "product_features": ph,
        },
        "security_deductions": {
            "hardcoded_secrets": secrets, "dangerous_calls": dangerous,
            "unsafe_deserialization": unsafe,
            "missing_exception_handlers": missing_h,
            "total_functions": funcs, "is_security_tool": is_sec,
        },
        "code_signals": {
            "total_functions": funcs, "total_classes": classes,
            "avg_function_length": avg_len, "total_loops": loops,
            "total_conditionals": conds, "files_analyzed": f_analyzed,
            "files_fallback": f_fallback, "total_files": total_f,
            "has_readme": has_readme, "has_snippets": has_snips,
            "tech_stack_categories": tech_keys, "tech_stack_detail": tech,
            "module_graph": mg, "call_graph": cg,
            "complexity_score": complexity, "folder_structure": fs,
        }
    }


def _build_pass1_prompt(context, problem_statement, anchors):
    c   = anchors["code_signals"]
    h   = anchors["hints"]
    fs  = c.get("folder_structure", {})
    sec = anchors["security_deductions"]
    mod_bk = anchors.get("computed_modularity_breakdown", {})

    readme = context.get("project_description", "")[:100]
    snips  = context.get("code_snippets", [])
    snip   = ""
    if snips:
        lines = snips[0].get("snippet", "").splitlines()[:3]
        snip  = snips[0].get("file", "") + ": " + " | ".join(lines)

    sec_note = " (security tool)" if anchors.get("is_security_tool") else ""
    sec_findings = []
    if sec["hardcoded_secrets"] > 0:
        sec_findings.append(f"{sec['hardcoded_secrets']} hardcoded secrets")
    if sec["missing_exception_handlers"] > 0:
        sec_findings.append(f"{sec['missing_exception_handlers']} missing error handlers")
    findings_str = ", ".join(sec_findings) if sec_findings else "none"

    # FIX 3: strengths/weaknesses BEFORE scores so LLM always generates them
    # LLM generates top-to-bottom — if reasoning is at bottom it gets cut off
    return f"""Hackathon judge. Reply ONLY as name=number or name=text lines.

PROJECT: files={c['total_files']} functions={c['total_functions']} classes={c['total_classes']}
complexity={c['complexity_score']} tech={c['tech_stack_categories']}{sec_note}
folder_dirs={fs.get('unique_dirs',0)} named_layers={fs.get('named_layers',[])}
imports_top={c['module_graph'].get('most_imported',[])[:4]}
calls_top={c['call_graph'].get('most_called',[])[:4]}
known_issues={findings_str}
problem="{problem_statement}"
readme="{readme}"
sample="{snip}"

Write reasoning FIRST (always required):
strengths= (one sentence: specific tech/metrics strengths)
weaknesses= (one sentence: reference known_issues above)
summary= (one sentence: overall verdict different from weaknesses)

Then write scores as name=integer from range:
functionality= ({h['functionality']}/10)
tech_stack_efficiency= ({h['tech_stack_efficiency']}/8)
code_quality_modularity= ({mod_bk.get('total', anchors['computed_modularity_base'])}/15 base)
code_readability= (5-7/10)
deployment_readiness= (1-2/2)
feasibility= ({h['feasibility']}/8)
novelty= ({h['novelty']}/6)
problem_alignment= ({h['problem_alignment']}/6)
scalability= ({h['scalability']}/3)
product_features= ({h['product_features']}/2)"""


def _build_pass2_prompt(first_scores, anchors, problem_statement):
    c      = anchors["code_signals"]
    te     = first_scores.get("technical_evaluation", {})
    funcs  = c["total_functions"]
    tf     = c["total_files"]
    n_tech = len(c["tech_stack_categories"])
    cpx    = c.get("complexity_score", 0)

    func_cap = 9 if funcs>=150 else 8 if funcs>=80 else 7 if funcs>=30 else 6
    tech_cap = min(8, n_tech*2+1)
    mod_cap  = min(15, anchors["computed_modularity_base"]+1)

    return f"""Senior judge reviewing TECHNICAL scores only. Reply as name=integer lines.
Project: {tf} files, {funcs} funcs, complexity={cpx}, tech={c['tech_stack_categories']}

Scores to review:
functionality={te.get('functionality',0)}/10  tech_stack_efficiency={te.get('tech_stack_efficiency',0)}/8
code_quality_modularity={te.get('code_quality_modularity',0)}/15  code_readability={te.get('code_readability',0)}/10
documentation={te.get('documentation',0)}/10

Caps: func<={func_cap} tech<={tech_cap} mod<={mod_cap}
Rules: raise any score below 3. Change by max +/-2. No perfect scores.

strengths= (one sentence, specific tech)
weaknesses= (one sentence, real issues)
summary= (one sentence verdict)
functionality=
tech_stack_efficiency=
code_quality_modularity=
code_readability=
documentation= (3-9/10)
"""


def _parse_kv_to_scores(raw, anchors):
    h   = anchors["hints"]
    mod = anchors["computed_modularity_base"]
    doc = anchors["computed_doc_base"]

    def mid(s):
        try: return int(s.replace(" ","").split("-")[0])
        except: return 3

    defaults = {
        "functionality": mid(h["functionality"]), "tech_stack_efficiency": mid(h["tech_stack_efficiency"]),
        "code_readability": 5, "deployment_readiness": 1,
        "feasibility": mid(h["feasibility"]), "novelty": mid(h["novelty"]),
        "problem_alignment": mid(h["problem_alignment"]), "scalability": mid(h["scalability"]),
        "product_features": mid(h["product_features"]),
        "code_quality_modularity": mod, "documentation": doc,
    }

    parsed     = parse_kv(raw, list(defaults.keys()), defaults)
    strengths  = _fix_truncation(get_str(parsed, 'strengths',  'strength',        default=""))
    weaknesses = _fix_truncation(get_str(parsed, 'weaknesses', 'weakness',        default=""))
    summary    = _fix_truncation(get_str(parsed, 'summary',    'overall_summary', default=""))

    return {
        "technical_evaluation": {
            "functionality":           float(parsed.get("functionality",           defaults["functionality"])),
            "tech_stack_efficiency":   float(parsed.get("tech_stack_efficiency",   defaults["tech_stack_efficiency"])),
            "code_quality_modularity": float(parsed.get("code_quality_modularity", mod)),
            "code_readability":        float(parsed.get("code_readability",        defaults["code_readability"])),
            "error_handling":          anchors["computed_error_handling_score"],
            "documentation":           float(parsed.get("documentation",           doc)),
            "security":                anchors["computed_security_score"],
        },
        "innovation_evaluation": {
            "feasibility":       float(parsed.get("feasibility",       defaults["feasibility"])),
            "novelty":           float(parsed.get("novelty",           defaults["novelty"])),
            "problem_alignment": float(parsed.get("problem_alignment", defaults["problem_alignment"])),
            "scalability":       float(parsed.get("scalability",       defaults["scalability"])),
            "product_features":  float(parsed.get("product_features",  defaults["product_features"])),
        },
        "completeness_evaluation": {
            "feature_completeness": anchors["computed_feat_complete"],
            "project_polish":       anchors["computed_polish"],
            "deployment_readiness": float(parsed.get("deployment_readiness", 1)),
        },
        "reasoning": {"strengths": strengths, "weaknesses": weaknesses, "overall_summary": summary}
    }


def _parse_p2_technical_only(raw, p1_scores, anchors):
    """Pass 2 only updates technical fields. Innovation/completeness stay from Pass 1."""
    mod = anchors["computed_modularity_base"]
    doc = anchors["computed_doc_base"]
    p1_te = p1_scores.get("technical_evaluation", {})
    defaults = {
        "functionality":           p1_te.get("functionality",           5),
        "tech_stack_efficiency":   p1_te.get("tech_stack_efficiency",   4),
        "code_quality_modularity": p1_te.get("code_quality_modularity", mod),
        "code_readability":        p1_te.get("code_readability",        5),
        "documentation":           p1_te.get("documentation",           doc),
    }
    parsed     = parse_kv(raw, list(defaults.keys()), defaults)
    strengths  = _fix_truncation(get_str(parsed, 'strengths',  'strength',        default=""))
    weaknesses = _fix_truncation(get_str(parsed, 'weaknesses', 'weakness',        default=""))
    summary    = _fix_truncation(get_str(parsed, 'summary',    'overall_summary', default=""))
    return {
        "technical_evaluation": {
            "functionality":           float(parsed.get("functionality",           defaults["functionality"])),
            "tech_stack_efficiency":   float(parsed.get("tech_stack_efficiency",   defaults["tech_stack_efficiency"])),
            "code_quality_modularity": float(parsed.get("code_quality_modularity", defaults["code_quality_modularity"])),
            "code_readability":        float(parsed.get("code_readability",        defaults["code_readability"])),
            "error_handling":          anchors["computed_error_handling_score"],
            "documentation":           float(parsed.get("documentation",           defaults["documentation"])),
            "security":                anchors["computed_security_score"],
        },
        "innovation_evaluation":   p1_scores.get("innovation_evaluation", {}),
        "completeness_evaluation": p1_scores.get("completeness_evaluation", {}),
        "reasoning": {"strengths": strengths, "weaknesses": weaknesses, "overall_summary": summary}
    }


def _llm_responded(raw):
    return bool(raw and re.search(r'\w+\s*=\s*\d', raw))


def _clamp_scores(scores):
    for section, limits in SCORE_LIMITS.items():
        if section not in scores: scores[section] = {}
        for key, max_val in limits.items():
            val = scores[section].get(key)
            if isinstance(val, (int, float)):
                scores[section][key] = round(min(max(val, 0), max_val), 1)
    return scores


def _apply_anchors(scores, anchors):
    scores["technical_evaluation"]["security"]       = anchors["computed_security_score"]
    scores["technical_evaluation"]["error_handling"] = anchors["computed_error_handling_score"]
    scores["completeness_evaluation"]["feature_completeness"] = anchors["computed_feat_complete"]
    scores["completeness_evaluation"]["project_polish"]       = anchors["computed_polish"]
    if anchors.get("computed_align_anchored") is not None:
        scores["innovation_evaluation"]["problem_alignment"] = anchors["computed_align_anchored"]
    tf = anchors.get("computed_tech_floor", 0)
    if scores["technical_evaluation"].get("tech_stack_efficiency", 0) < tf:
        scores["technical_evaluation"]["tech_stack_efficiency"] = float(tf)
    mf = max(0, anchors.get("computed_modularity_base", 0) - 2)
    if scores["technical_evaluation"].get("code_quality_modularity", 0) < mf:
        scores["technical_evaluation"]["code_quality_modularity"] = float(mf)
    sc = anchors.get("computed_scale_cap", 3)
    pc = anchors.get("computed_prod_cap",  2)
    if scores["innovation_evaluation"].get("scalability", 0) > sc:
        scores["innovation_evaluation"]["scalability"] = float(sc)
    if scores["innovation_evaluation"].get("product_features", 0) > pc:
        scores["innovation_evaluation"]["product_features"] = float(pc)
    return scores


def _raise_zeros(scores, anchors):
    c = anchors["code_signals"]
    if c["total_files"] == 0: return scores
    mod = anchors["computed_modularity_base"]
    doc = anchors["computed_doc_base"]
    for k, v in {"functionality":3,"tech_stack_efficiency":3,"code_quality_modularity":max(3,mod-3),
                 "code_readability":3,"documentation":max(2,doc-2)}.items():
        if scores["technical_evaluation"].get(k, 0) == 0: scores["technical_evaluation"][k] = v
    for k, v in {"feasibility":2,"novelty":2,"problem_alignment":2,"scalability":1,"product_features":1}.items():
        if scores["innovation_evaluation"].get(k, 0) == 0: scores["innovation_evaluation"][k] = v
    for k, v in {"feature_completeness":2,"project_polish":1,"deployment_readiness":1}.items():
        if scores["completeness_evaluation"].get(k, 0) == 0: scores["completeness_evaluation"][k] = v
    return scores


def _mid(s):
    try: return int(s.replace(" ","").split("-")[0])
    except: return 3


def _static_fallback(anchors):
    c = anchors["code_signals"]; h = anchors["hints"]
    funcs = c["total_functions"]; tf = c["total_files"]
    tech  = c["tech_stack_categories"]; fs = c.get("folder_structure", {})
    return {
        "technical_evaluation": {
            "functionality": _mid(h["functionality"]), "tech_stack_efficiency": _mid(h["tech_stack_efficiency"]),
            "code_quality_modularity": anchors["computed_modularity_base"],
            "code_readability": min(6, 3 + funcs//60),
            "error_handling": anchors["computed_error_handling_score"],
            "documentation": anchors["computed_doc_base"],
            "security": anchors["computed_security_score"],
        },
        "innovation_evaluation": {
            "feasibility": _mid(h["feasibility"]), "novelty": _mid(h["novelty"]),
            "problem_alignment": anchors.get("computed_align_anchored") or _mid(h["problem_alignment"]),
            "scalability": min(anchors.get("computed_scale_cap",2), _mid(h["scalability"])),
            "product_features": min(anchors.get("computed_prod_cap",1), _mid(h["product_features"])),
        },
        "completeness_evaluation": {
            "feature_completeness": anchors["computed_feat_complete"],
            "project_polish": anchors["computed_polish"],
            "deployment_readiness": anchors["computed_deploy"],
        },
        "reasoning": {
            "strengths": f"{tf} files across {fs.get('unique_dirs',0)} dirs, {funcs} functions, tech: {tech}.",
            "weaknesses": "Static analysis only — LLM unavailable.",
            "overall_summary": f"Project: {tf} files, {funcs} functions, stack: {tech}."
        }
    }


def _compute_totals(scores):
    tt = round(sum(scores["technical_evaluation"].values()), 1)
    it = round(sum(scores["innovation_evaluation"].values()), 1)
    ct = round(sum(scores["completeness_evaluation"].values()), 1)
    scores.update({"technical_total": tt, "innovation_total": it,
                   "completeness_total": ct, "final_score": round(tt+it+ct, 1),
                   "max_technical": MAX_TECHNICAL, "max_innovation": MAX_INNOVATION,
                   "max_completeness": MAX_COMPLETENESS, "max_total": MAX_TOTAL})
    return scores


def run_final_evaluation(context, problem_statement, alignment_score=None):
    files_analyzed = context.get("code_metrics", {}).get("files_analyzed", 0)
    files_fallback = context.get("code_metrics", {}).get("files_fallback", 0)
    has_real     = files_analyzed > 0
    has_fallback = (files_analyzed == 0) and (files_fallback > 0)

    if files_analyzed == 0 and files_fallback == 0:
        ea = _build_anchors(context, False, False)
        e  = _static_fallback(ea)
        for s in SCORE_LIMITS:
            for k in SCORE_LIMITS[s]: e[s][k] = 0
        return _compute_totals(e) | {"error": "No files analyzed."}

    anchors = _build_anchors(context, has_real, has_fallback, alignment_score)

    print("      [Pass 1] Primary evaluation...")
    p1_raw    = call_json(_build_pass1_prompt(context, problem_statement, anchors))
    p1_llm_ok = _llm_responded(p1_raw)

    if p1_llm_ok:
        p1 = _parse_kv_to_scores(p1_raw, anchors)
    else:
        print("      [Pass 1] LLM failed - using static fallback.")
        p1 = _static_fallback(anchors)

    p1 = _clamp_scores(p1); p1 = _apply_anchors(p1, anchors); p1 = _raise_zeros(p1, anchors)

    if not has_real or not p1_llm_ok:
        reason = "no AST" if not has_real else "Pass 1 failed"
        print(f"      [Pass 2] Skipped - {reason}.")
        p1["anchors_used"] = anchors
        return _compute_totals(p1)

    print("      [Pass 2] Reviewer pass (technical only)...")
    p2_raw    = call_reviewer(_build_pass2_prompt(p1, anchors, problem_statement))
    p2_llm_ok = _llm_responded(p2_raw)

    if not p2_llm_ok:
        print("      [Pass 2] Reviewer failed - keeping Pass 1.")
        final = p1
    else:
        p2 = _parse_p2_technical_only(p2_raw, p1, anchors)
        p2 = _clamp_scores(p2); p2 = _apply_anchors(p2, anchors); p2 = _raise_zeros(p2, anchors)
        p2["review_notes"] = "Pass 2 technical review applied."
        final = p2

    final["anchors_used"] = anchors
    return _compute_totals(final)