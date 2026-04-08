"""
kv_parser.py  —  utils/kv_parser.py
Parses key=value LLM responses.
Fields in INTEGER_FIELDS are rounded to nearest integer (no decimals like 1.5).
"""

import re

STRING_FIELDS = {
    'strengths', 'strength',
    'weaknesses', 'weakness',
    'summary', 'overall_summary',
    'reasoning', 'notes', 'review_notes',
    'matched', 'missing',
    'architecture', 'architecture_summary',
    'project_type', 'problem_summary',
    'solution_summary', 'technologies', 'technologies_used',
}

# Score fields that must be whole numbers (not 1.5, 6.5, etc.)
INTEGER_FIELDS = {
    'functionality', 'tech_stack_efficiency', 'code_quality_modularity',
    'code_readability', 'error_handling', 'documentation', 'security',
    'feasibility', 'novelty', 'problem_alignment', 'scalability',
    'product_features', 'feature_completeness', 'project_polish',
    'deployment_readiness', 'code_quality_score',
    'engineering_complexity_score', 'architecture_quality_score',
    'alignment_score',
}


def parse_kv(text, numeric_fields, fallbacks=None):
    """
    Extract key=value pairs from LLM text.

    Args:
        text           : raw LLM response
        numeric_fields : list of numeric field names to extract
        fallbacks      : {field: default} for missing fields

    Returns dict with string fields as str and numeric fields as float.
    Integer fields (scores) are rounded to nearest whole number.
    """
    if fallbacks is None:
        fallbacks = {}

    result = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or ('=' not in line and ':' not in line):
            continue

        sep = '=' if '=' in line else ':'
        key, _, val = line.partition(sep)
        key = key.strip().lower().replace('-', '_').replace(' ', '_')
        val = val.strip().strip('"\'')

        if not key or not val:
            continue

        # String field — store as-is
        if key in STRING_FIELDS:
            result[key] = val
            continue

        # Try numeric
        m = re.match(r'^(\d+(?:\.\d+)?)\s*$', val)
        if m:
            num = float(m.group(1))
            # Round score fields to integers (no 1.5, 6.5, etc.)
            result[key] = round(num) if key in INTEGER_FIELDS else num
            continue

        # Value starts with digit but has trailing text
        m2 = re.match(r'^(\d+(?:\.\d+)?)\s', val)
        if m2:
            num = float(m2.group(1))
            result[key] = round(num) if key in INTEGER_FIELDS else num
            continue

        # Unknown key with string value
        if len(val) > 10 or ' ' in val:
            result[key] = val

    # Apply fallbacks for missing numeric fields
    for field in numeric_fields:
        if field not in result:
            default = float(fallbacks.get(field, 3))
            result[field] = round(default) if field in INTEGER_FIELDS else default

    return result


def get_str(parsed, *keys, default=""):
    """Get a string value trying multiple key variants."""
    for key in keys:
        val = parsed.get(key)
        if val and isinstance(val, str):
            return val
    return default