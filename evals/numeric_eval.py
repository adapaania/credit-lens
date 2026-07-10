"""Numeric exact-match scoring: unit/scale normalization, 0.5% tolerance.

All figures in this project's golden dataset are expressed in millions of
dollars, matching the "(Dollars in millions)" convention used throughout
the SEC filings themselves. A candidate number extracted from an answer is
normalized to that same unit before comparison.
"""

import re

TOLERANCE = 0.005  # 0.5%, per the build spec

_NUMBER_RE = re.compile(
    r"(?P<neg>-|\()?\s*\$?\s?"
    r"(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<close>\))?\s*(?P<scale>million|billion|thousand)?",
    re.IGNORECASE,
)


def extract_candidate_values(text: str) -> list[float]:
    """Find every numeric value in text, normalized to millions of dollars."""
    values: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        raw_number = match.group("number")
        if not raw_number:
            continue
        try:
            value = float(raw_number.replace(",", ""))
        except ValueError:
            continue

        if match.group("neg"):
            value = -value

        scale = (match.group("scale") or "").lower()
        if scale == "billion":
            value *= 1000
        elif scale == "thousand":
            value /= 1000
        # No scale word, or "million": already expressed in millions.

        values.append(value)
    return values


def numeric_match(answer_text: str, truth_value_millions: float, tolerance: float = TOLERANCE) -> bool:
    """True if any number in answer_text matches truth_value_millions within tolerance.

    Compares magnitudes rather than signed values: financial answers commonly
    state a loss as a plain positive number with contextual wording ("a net
    loss of $11,817 million") rather than an explicit minus sign or
    parentheses. Penalizing that phrasing would be testing prose style, not
    numeric accuracy.
    """
    truth_magnitude = abs(truth_value_millions)
    for candidate in extract_candidate_values(answer_text):
        if truth_magnitude == 0:
            if abs(candidate) < 1e-9:
                return True
            continue
        relative_error = abs(abs(candidate) - truth_magnitude) / truth_magnitude
        if relative_error <= tolerance:
            return True
    return False
