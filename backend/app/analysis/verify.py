"""Checks that an LLM citation really exists in the file at (about) the cited lines."""
import re

from app.analysis.rules import Evidence

DRIFT = 3  # allowed line-number error either side
MAX_SNIPPET_LINES = 15
_LINE_PREFIX = re.compile(r"^\s*\d+\s*\|\s?")  # in case the model copied our "  12 | " prefix


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", _LINE_PREFIX.sub("", line)).strip()


def verify_citation(citation: dict, files_by_path: dict[str, str]) -> Evidence | None:
    """Returns verified evidence (line numbers corrected to where the snippet really is), or None."""
    content = files_by_path.get(citation["path"])
    if content is None:
        return None
    lines = content.splitlines()
    start, end = citation["start_line"], citation["end_line"]
    if not (1 <= start <= len(lines)) or end < start:
        return None

    wanted = [_norm(s) for s in citation["snippet"].splitlines() if _norm(s)]
    if not wanted or len(wanted) > MAX_SNIPPET_LINES:
        return None

    lo, hi = max(1, start - DRIFT), min(len(lines), end + DRIFT)
    window = [(n, _norm(lines[n - 1])) for n in range(lo, hi + 1)]
    found: list[int] = []
    pos = 0
    for w in wanted:  # each snippet line must appear, in order, within the window
        for idx in range(pos, len(window)):
            n, text = window[idx]
            if text and w in text:
                found.append(n)
                pos = idx + 1
                break
        else:
            return None

    real_start, real_end = found[0], found[-1]
    snippet = "\n".join(lines[real_start - 1 : real_end])
    return Evidence(citation["path"], real_start, real_end, snippet, "llm", source="llm")
