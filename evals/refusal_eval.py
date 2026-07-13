"""Heuristic check for cross-company filing-scope refusal (Fix 1 / FIXES.md).

Unlike numeric_eval.py (checks a figure is present and correct), this checks
the opposite: that the agent does NOT state a specific dollar figure for a
company other than the one covered by the selected filing_id, and that it
does redirect the user toward switching filings. This is deliberately a
heuristic, not an exact-match check - "does the answer decline and redirect"
is a behavioral property, not a number to compare against a truth value.
"""

import re

_DOLLAR_FIGURE_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s*(?:million|billion|thousand)?", re.IGNORECASE)
_REDIRECT_RE = re.compile(
    r"switch|select|does not cover|doesn't cover|not cover|cannot (provide|answer)|can't (provide|answer)",
    re.IGNORECASE,
)


def refusal_ok(answer_text: str) -> bool:
    """True if the answer avoids stating a dollar figure and signals a redirect."""
    has_dollar_figure = bool(_DOLLAR_FIGURE_RE.search(answer_text))
    has_redirect_language = bool(_REDIRECT_RE.search(answer_text))
    return (not has_dollar_figure) and has_redirect_language
