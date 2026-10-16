"""Rule-based evidence from file paths, code patterns and dependency manifests (no LLM)."""
import json
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "package.json", "go.mod", "pom.xml", "build.gradle", "Cargo.toml"}
MAX_EVIDENCE = 4
MAX_CODE_HITS_PER_FILE = 2
CONTEXT_LINES = 4  # lines shown after a code match


@dataclass
class Evidence:
    path: str
    start_line: int | None
    end_line: int | None
    snippet: str
    kind: str  # code | path | dependency | history | llm
    source: str = "rule"  # rule | llm


@dataclass
class RuleResult:
    status: str
    confidence: str | None
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)


def path_matches(path: str, pattern: str) -> bool:
    # fnmatch's "*" also matches "/", so "**/x" only needs a fallback for files at the repo root.
    return fnmatchcase(path, pattern) or (pattern.startswith("**/") and fnmatchcase(path, pattern[3:]))


def _block(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _head_evidence(path: str, content: str) -> Evidence:
    lines = content.splitlines()
    end = min(len(lines), 8)
    return Evidence(path, 1, end, _block(lines, 1, end), "path")


def _dependency_regex(name: str) -> re.Pattern:
    return re.compile(rf"(^|[\s\"'/]){re.escape(name)}($|[\s\"'=<>~!\[;:,@])", re.IGNORECASE)


def evaluate(skill_label: str, rule_hints: dict | None, files: list[dict]) -> RuleResult:
    """files: [{path, content}] with text content only."""
    if not rule_hints:
        return RuleResult("not_demonstrated", None, "No rule-based check exists for this skill.")

    code_hits, path_hits, dep_hits = [], [], []

    for pattern in rule_hints.get("code_patterns", []):
        regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        for f in files:
            if PurePosixPath(f["path"]).name in MANIFEST_NAMES:
                continue
            lines = f["content"].splitlines()
            hits_in_file = 0
            for i, line in enumerate(lines, start=1):
                if hits_in_file >= MAX_CODE_HITS_PER_FILE:
                    break
                if regex.search(line) and not any(h.path == f["path"] and h.start_line <= i <= h.end_line for h in code_hits):
                    end = min(len(lines), i + CONTEXT_LINES)
                    code_hits.append(Evidence(f["path"], i, end, _block(lines, i, end), "code"))
                    hits_in_file += 1

    path_patterns = rule_hints.get("paths", [])
    matching = [f for f in files if any(path_matches(f["path"], p) for p in path_patterns)]
    # Prefer substantial files; empty files (e.g. __init__.py) prove nothing.
    for f in sorted(matching, key=lambda f: -len(f["content"])):
        if f["content"].strip():
            path_hits.append(_head_evidence(f["path"], f["content"]))

    for name in rule_hints.get("dependencies", []):
        regex = _dependency_regex(name)
        for f in files:
            if PurePosixPath(f["path"]).name not in MANIFEST_NAMES:
                continue
            for i, line in enumerate(f["content"].splitlines(), start=1):
                if regex.search(line):
                    dep_hits.append(Evidence(f["path"], i, i, line.strip(), "dependency"))
                    break

    evidence = (code_hits + path_hits + dep_hits)[:MAX_EVIDENCE]
    parts = []
    if code_hits:
        parts.append(f"{len(code_hits)} matching code location(s) in {', '.join(sorted({h.path for h in code_hits}))}")
    if path_hits:
        parts.append(f"{len(path_hits)} relevant file(s) such as {path_hits[0].path}")
    if dep_hits:
        parts.append(f"dependency listed: {', '.join(sorted({h.snippet for h in dep_hits}))}")

    if code_hits or path_hits:
        confidence = "high" if (code_hits and (path_hits or dep_hits)) or len(code_hits) > 1 else "medium"
        return RuleResult("demonstrated", confidence, f"Rule-based: {'; '.join(parts)}.", evidence)
    if dep_hits:
        return RuleResult(
            "partially_demonstrated", "low",
            f"Rule-based: {'; '.join(parts)}, but no code using it was found.", evidence,
        )
    return RuleResult("not_demonstrated", None, f"No evidence of {skill_label} found in the analyzed files.")


def evaluate_version_control(commit_count: int, branch: str, has_gitignore: bool) -> RuleResult:
    evidence = [Evidence("(commit history)", None, None, f"{commit_count} commits on {branch}", "history")]
    if commit_count >= 3:
        extra = " and a .gitignore" if has_gitignore else ""
        return RuleResult("demonstrated", "high" if has_gitignore else "medium",
                          f"Rule-based: {commit_count} commits on {branch}{extra}.", evidence)
    return RuleResult("partially_demonstrated", "low", f"Rule-based: only {commit_count} commit(s) on {branch}.", evidence)


def hints_of(skill_row) -> dict | None:
    return json.loads(skill_row["rule_hints"]) if skill_row["rule_hints"] else None
