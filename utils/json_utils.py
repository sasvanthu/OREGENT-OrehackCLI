import json
import re


def _normalize(text):
    text = re.sub(r"```(?:json|python|JSON)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r'\bTrue\b',  'true',  text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b',  'null',  text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text.strip()


def _brace_extract(text):
    depth, start, in_str, esc = 0, None, False, False
    for i, ch in enumerate(text):
        if esc:          esc = False; continue
        if ch == '\\' and in_str: esc = True; continue
        if ch == '"':    in_str = not in_str; continue
        if in_str:       continue
        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i + 1]
    return None


def extract_json(text):
    if not text or not text.strip():
        return None
    try:
        r = json.loads(text.strip())
        if isinstance(r, dict): return r
    except Exception: pass
    norm = _normalize(text)
    try:
        r = json.loads(norm)
        if isinstance(r, dict): return r
    except Exception: pass
    block = _brace_extract(norm)
    if block:
        try:
            r = json.loads(block)
            if isinstance(r, dict): return r
        except Exception: pass
    block2 = _brace_extract(text)
    if block2:
        try:
            r = json.loads(_normalize(block2))
            if isinstance(r, dict): return r
        except Exception: pass
    m = re.search(r'\{.*\}', norm, re.DOTALL)
    if m:
        try:
            r = json.loads(m.group())
            if isinstance(r, dict): return r
        except Exception: pass
    return None