"""Chooses the code an LLM should read for one skill, with line numbers, within a size budget."""
import json
import re

from app.analysis.rules import Evidence

MAX_EXCERPT_CHARS = 12000  # ~3k tokens
FULL_FILE_MAX_LINES = 150
WINDOW = 12  # lines of context around a hit in large files


def _keywords(skill_row, hints: dict | None) -> list[str]:
    words = json.loads(skill_row["synonyms"]) + [skill_row["key"].replace("_", " ")]
    words += (hints or {}).get("dependencies", [])
    return sorted({w.lower() for w in words if len(w) >= 3}, key=len, reverse=True)


def candidate_files(skill_row, hints: dict | None, files: list[dict], rule_evidence: list[Evidence]) -> list[tuple[dict, set[int]]]:
    """Files worth showing the LLM, best first, with the line numbers that matter in each."""
    words = _keywords(skill_row, hints)
    regex = re.compile(r"(?<![a-z0-9])(" + "|".join(map(re.escape, words)) + r")(?![a-z0-9])", re.I) if words else None

    rule_lines: dict[str, set[int]] = {}
    for ev in rule_evidence:
        if ev.start_line:
            rule_lines.setdefault(ev.path, set()).update(range(ev.start_line, (ev.end_line or ev.start_line) + 1))

    scored = []
    for f in files:
        hits = set(rule_lines.get(f["path"], set()))
        keyword_lines = 0
        if regex:
            for i, line in enumerate(f["content"].splitlines(), start=1):
                if regex.search(line):
                    hits.add(i)
                    keyword_lines += 1
        path_hit = bool(regex and regex.search(f["path"]))
        score = 10 * (f["path"] in rule_lines) + keyword_lines + 3 * path_hit
        if score > 0 and f["content"].strip():
            scored.append((score, f, hits))
    scored.sort(key=lambda s: (-s[0], s[1]["path"]))
    return [(f, hits) for _, f, hits in scored]


def _ranges(hit_lines: set[int], total: int) -> list[tuple[int, int]]:
    if total <= FULL_FILE_MAX_LINES or not hit_lines:
        return [(1, min(total, FULL_FILE_MAX_LINES))]
    ranges: list[list[int]] = []
    for line in sorted(hit_lines):
        start, end = max(1, line - WINDOW), min(total, line + WINDOW)
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return [tuple(r) for r in ranges]


def build_excerpt(candidates: list[tuple[dict, set[int]]]) -> str:
    parts, used = [], 0
    for f, hit_lines in candidates:
        lines = f["content"].splitlines()
        chunks = []
        for start, end in _ranges(hit_lines, len(lines)):
            chunks.append("\n".join(f"{n:>4} | {lines[n - 1]}" for n in range(start, end + 1)))
        block = f"=== FILE: {f['path']} ===\n" + "\n   ...\n".join(chunks)
        if used + len(block) > MAX_EXCERPT_CHARS:
            if parts:
                break
            block = block[:MAX_EXCERPT_CHARS]
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)
