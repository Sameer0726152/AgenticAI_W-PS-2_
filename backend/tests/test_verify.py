from app.analysis.verify import verify_citation

MAIN = """from fastapi import FastAPI, HTTPException

app = FastAPI()


@app.get("/students/{student_id}")
def get_student(student_id: int):
    student = find(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student
"""
FILES = {"app/main.py": MAIN}


def cite(start, end, snippet, path="app/main.py"):
    return verify_citation({"path": path, "start_line": start, "end_line": end, "snippet": snippet}, FILES)


def test_exact_citation_is_verified():
    ev = cite(9, 10, 'if not student:\n    raise HTTPException(status_code=404, detail="Student not found")')
    assert ev and (ev.start_line, ev.end_line) == (9, 10)


def test_small_line_drift_is_corrected():
    ev = cite(8, 8, '@app.get("/students/{student_id}")')  # really on line 6
    assert ev and ev.start_line == 6


def test_copied_line_number_prefix_is_tolerated():
    assert cite(7, 7, "   7 | def get_student(student_id: int):")


def test_invented_code_is_rejected():
    assert cite(10, 11, "raise HTTPException(status_code=422)") is None


def test_wrong_file_is_rejected():
    assert cite(1, 1, "from fastapi import FastAPI", path="app/other.py") is None


def test_far_away_lines_are_rejected():
    assert cite(1, 1, "return student") is None  # exists, but on line 11, not near line 1


def test_out_of_range_lines_are_rejected():
    assert cite(99, 100, "return student") is None
