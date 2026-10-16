import json

from app.assessment.affected import affected_skills


def skill(key, synonyms=(), hints=None):
    return {"key": key, "synonyms": json.dumps(list(synonyms)), "rule_hints": json.dumps(hints) if hints else None}


SKILLS = [
    skill("testing", ["pytest", "unit tests"], {"paths": ["tests/**", "**/test_*.py"], "code_patterns": [r"def test_\w+\("]}),
    skill("docker", ["containers"], {"paths": ["Dockerfile"]}),
    skill("kv_store", ["redis"], {"dependencies": ["redis"]}),
    skill("rest_api", ["api"], {"code_patterns": [r"@app\.(get|post)\("]}),
    skill("version_control", ["git"], {"paths": [".gitignore"]}),
]
PREV = {"testing": set(), "docker": set(), "kv_store": set(), "rest_api": {"app/main.py"}, "version_control": set()}


def changed(*paths, status="added"):
    return [{"path": p, "status": status, "previous_path": None} for p in paths]


def test_new_test_file_affects_only_testing():
    result = affected_skills(SKILLS, changed("tests/test_api.py"), PREV, {"tests/test_api.py": "def test_x():\n    pass"})
    assert result == {"testing", "version_control"}


def test_editing_cited_file_reassesses_that_skill():
    result = affected_skills(SKILLS, changed("app/main.py", status="modified"), PREV, {"app/main.py": "print('hi')"})
    assert "rest_api" in result and "docker" not in result


def test_keyword_in_changed_content():
    result = affected_skills(SKILLS, changed("app/cache.py"), PREV, {"app/cache.py": "import redis\n"})
    assert "kv_store" in result and "testing" not in result


def test_removed_file_still_counts():
    result = affected_skills(SKILLS, changed("Dockerfile", status="removed"), PREV, {})
    assert "docker" in result


def test_skill_not_assessed_before_is_always_affected():
    prev = {k: v for k, v in PREV.items() if k != "docker"}
    assert "docker" in affected_skills(SKILLS, changed("README.md"), prev, {"README.md": "hello"})
