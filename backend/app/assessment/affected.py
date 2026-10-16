"""Which skills can a set of changed files affect? Only those are re-assessed; the rest carry over."""
import re

from app.analysis.excerpts import _keywords
from app.analysis.rules import hints_of, path_matches


def affected_skills(
    skills: list,
    changed: list[dict],
    prev_evidence_paths: dict[str, set[str]],
    new_contents: dict[str, str],
) -> set[str]:
    """
    skills: skill rows of interest.
    changed: [{path, status, previous_path}] from the compare API.
    prev_evidence_paths: skill key -> files its previous evidence cited (missing key = not assessed before).
    new_contents: path -> text of changed files at the new commit (removed files absent).
    """
    changed_paths = {c["path"] for c in changed} | {c["previous_path"] for c in changed if c["previous_path"]}
    result = set()
    for skill in skills:
        key = skill["key"]
        if key not in prev_evidence_paths or key == "version_control":  # new skill, or commit count changed
            result.add(key)
            continue
        if prev_evidence_paths[key] & changed_paths:  # its evidence was edited, moved or deleted
            result.add(key)
            continue

        hints = hints_of(skill) or {}
        if any(path_matches(p, pattern) for p in changed_paths for pattern in hints.get("paths", [])):
            result.add(key)
            continue

        words = _keywords(skill, hints)
        word_re = re.compile(r"(?<![a-z0-9])(" + "|".join(map(re.escape, words)) + r")(?![a-z0-9])", re.I) if words else None
        code_res = [re.compile(p, re.I | re.M) for p in hints.get("code_patterns", [])]
        # Paths are matched only by precise rule globs above; loose keywords (e.g. "api" in
        # "test_api.py") are checked against file contents only.
        for path in changed_paths:
            text = new_contents.get(path, "")
            if (word_re and word_re.search(text)) or any(r.search(text) for r in code_res):
                result.add(key)
                break
    return result
