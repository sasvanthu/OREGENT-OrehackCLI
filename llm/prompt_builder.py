def build_project_understanding_prompt(context):
    """
    Ultra-compact project understanding prompt.
    Uses key=value format so LLM just continues lines — reliable even on slow CPU.
    Hint examples after each field force deepseek to fill them (not echo the key name).
    """
    readme    = context.get("project_description", "")[:200]
    tech      = list(context.get("detected_tech_stack", {}).keys())
    metrics   = context.get("code_metrics", {})
    snippets  = context.get("code_snippets", [])
    funcs     = metrics.get("total_functions", 0)
    # include fallback-analyzed files in the count so deepseek isn't misled
    files     = metrics.get("files_analyzed", 0) + metrics.get("files_fallback", 0)

    snip = ""
    if snippets:
        lines = snippets[0].get("snippet", "").splitlines()[:4]
        snip  = "\n".join(lines)

    return f"""Describe this project. Reply as name=value lines only, nothing else.

tech={tech} files={files} functions={funcs}
readme={readme[:150]}
code={snip[:150]}

project_type= (e.g. web app, CLI tool, ML model, game, desktop app)
problem_summary= (one sentence: what problem does it solve)
solution_summary= (one sentence: how does it solve it)
technologies= (comma separated: main libs/frameworks used)
architecture= (one sentence: how the parts connect)"""