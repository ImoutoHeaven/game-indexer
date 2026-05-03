from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for separator in ("==", ">=", "<=", "~=", ">", "<"):
            if separator in line:
                line = line.split(separator, 1)[0]
                break
        names.add(line.lower())
    return names


def test_requirements_cover_direct_runtime_dependencies():
    requirements = _requirement_names(ROOT / "requirements.txt")

    assert {
        "flagembedding",
        "meilisearch",
        "numpy",
        "fastapi",
        "uvicorn",
        "jinja2",
        "python-multipart",
        "cryptography",
    } <= requirements


def test_requirements_dev_includes_runtime_requirements():
    req_dev = ROOT / "requirements-dev.txt"
    lines = [line.strip() for line in req_dev.read_text(encoding="utf-8").splitlines()]

    assert "-r requirements.txt" in lines
