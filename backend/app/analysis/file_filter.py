"""Decides which repository files are worth analyzing, most useful first."""
from pathlib import PurePosixPath

from app import config

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", ".next", "out",
    "target", "vendor", ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache", "site-packages",
}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
    "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock",
}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".pdf", ".zip", ".gz", ".tar",
    ".7z", ".rar", ".jar", ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".class", ".o", ".a",
    ".db", ".sqlite", ".sqlite3", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".wav",
    ".pkl", ".h5", ".pt", ".onnx", ".parquet", ".csv", ".xlsx", ".ipynb",
}
MANIFESTS = {
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "package.json", "go.mod",
    "CMakeLists.txt", "pom.xml", "build.gradle", "Cargo.toml", "Dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yaml", ".gitignore", "Makefile", "Chart.yaml", "pytest.ini", "conftest.py",
}
SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".cpp", ".cc", ".cxx", ".hpp", ".h",
    ".c", ".rs", ".rb", ".php", ".cs", ".swift", ".scala", ".sql",
}
CONFIG_EXTS = {".yml", ".yaml", ".toml", ".tf", ".tfvars", ".sh", ".ini", ".cfg", ".json"}
TEST_MARKERS = ("test_", "_test.", ".test.", ".spec.")


def _skip_reason(path: str, size: int) -> str | None:
    p = PurePosixPath(path)
    if any(part in SKIP_DIRS for part in p.parts[:-1]):
        return "dependency/build folder"
    if p.name in LOCKFILES:
        return "lockfile"
    if p.suffix.lower() in BINARY_EXTS:
        return "binary/data file"
    if size > config.MAX_FILE_BYTES:
        return "too large"
    return None


def _priority(path: str) -> int:
    p = PurePosixPath(path)
    name, suffix = p.name, p.suffix.lower()
    if name in MANIFESTS or path.startswith(".github/workflows/"):
        return 0
    if suffix in SOURCE_EXTS and (any(m in name for m in TEST_MARKERS) or "tests" in p.parts or "test" in p.parts):
        return 1
    if suffix in SOURCE_EXTS:
        return 2
    if suffix in CONFIG_EXTS or name.endswith(".md"):
        return 3
    return 4


def select_files(tree: list[dict]) -> list[dict]:
    """Adds `included` and `skip_reason` to each tree entry; keeps at most MAX_FILES_PER_SNAPSHOT."""
    candidates, result = [], []
    for entry in tree:
        reason = _skip_reason(entry["path"], entry["size"])
        if reason:
            result.append({**entry, "included": False, "skip_reason": reason})
        else:
            candidates.append(entry)

    candidates.sort(key=lambda e: (_priority(e["path"]), e["path"].count("/"), e["path"]))
    for i, entry in enumerate(candidates):
        included = i < config.MAX_FILES_PER_SNAPSHOT
        result.append({**entry, "included": included, "skip_reason": None if included else "over file limit"})
    return result
