"""Asks the LLM whether code excerpts demonstrate one skill, then keeps only verifiable citations."""
from dataclasses import dataclass, field

from app.analysis.excerpts import build_excerpt, candidate_files
from app.analysis.rules import Evidence, RuleResult
from app.analysis.verify import verify_citation
from app.llm.client import chat_json

PROMPT_VERSION = "evidence-v1"

SYSTEM_PROMPT = """You review code excerpts from a student's GitHub repository and judge whether they
demonstrate ONE named skill.

Statuses:
- "demonstrated": the code meaningfully implements or uses the skill.
- "partially_demonstrated": present but minimal, trivial or boilerplate (e.g. only a dependency,
  a single superficial use).
- "not_demonstrated": no meaningful evidence in these excerpts.
Judge only the code shown. Absence means "not shown in this repository", never "the student
lacks the skill".

Citations (1 to 3, only for demonstrated/partially_demonstrated; empty list otherwise):
- path: exactly as shown after "=== FILE:".
- start_line / end_line: the line numbers shown at the left of the excerpt.
- snippet: 1 to 3 key lines copied EXACTLY from those lines, without the line-number prefix.

rationale: 1-2 sentences on WHAT the code does with the skill and HOW WELL (depth, practices
such as validation, error handling, structure). Do not mention the student.
confidence: how sure you are, given the excerpts."""

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["demonstrated", "partially_demonstrated", "not_demonstrated"]},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                    "snippet": {"type": "string"},
                },
                "required": ["path", "start_line", "end_line", "snippet"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "confidence", "rationale", "citations"],
    "additionalProperties": False,
}


@dataclass
class LLMResult:
    status: str
    confidence: str
    rationale: str
    evidence: list[Evidence] = field(default_factory=list)
    dropped: int = 0


def has_signal(skill_row, hints, files: list[dict], rule: RuleResult) -> bool:
    """Skip the LLM when nothing in the repo relates to the skill (saves tokens)."""
    return bool(rule.evidence) or bool(candidate_files(skill_row, hints, files, []))


def assess(skill_row, hints, files: list[dict], rule: RuleResult) -> LLMResult:
    candidates = candidate_files(skill_row, hints, files, rule.evidence)
    excerpt = build_excerpt(candidates)
    user = (
        f"Skill: {skill_row['label']} (key: {skill_row['key']})\n"
        f"Rule-based finding: {rule.rationale}\n\n"
        f"Code excerpts:\n{excerpt}"
    )
    result = chat_json(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
        schema=SCHEMA,
        schema_name="skill_evidence",
        prompt_version=PROMPT_VERSION,
        cache_parts=(skill_row["key"], skill_row["label"], rule.rationale, excerpt),
        max_tokens=1500,
    )

    files_by_path = {f["path"]: f["content"] for f in files}
    evidence, dropped = [], 0
    for c in result["citations"][:3]:
        ev = verify_citation(c, files_by_path)
        if ev:
            evidence.append(ev)
        else:
            dropped += 1
    return LLMResult(result["status"], result["confidence"], result["rationale"].strip(), evidence, dropped)
