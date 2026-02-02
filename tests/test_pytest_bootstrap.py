import configparser
from pathlib import Path


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (
            (candidate / "pytest.ini").exists()
            and (candidate / "requirements-dev.txt").exists()
            and (candidate / "tests").is_dir()
        ):
            return candidate

    raise AssertionError(
        "Unable to locate repo root containing pytest.ini, requirements-dev.txt, and tests/"
    )


def _iter_non_comment_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith(";"):
            continue
        lines.append(stripped)
    return lines


def test_pytest_ini_has_required_settings():
    pytest_ini = _repo_root() / "pytest.ini"
    assert pytest_ini.exists(), "Expected pytest.ini at repo root"

    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.read(pytest_ini)

    assert parser.has_section("pytest"), "pytest.ini missing [pytest] section header"
    assert parser.has_option("pytest", "testpaths"), (
        "pytest.ini missing testpaths setting in [pytest]"
    )

    testpaths_raw = parser.get("pytest", "testpaths")
    testpaths = testpaths_raw.replace(",", " ").split()
    assert "tests" in testpaths, "pytest.ini testpaths must include tests"


def test_requirements_dev_has_pytest_min_version():
    req_dev = _repo_root() / "requirements-dev.txt"
    assert req_dev.exists(), "Expected requirements-dev.txt at repo root"

    normalized_lines = []
    for line in _iter_non_comment_lines(req_dev):
        without_comment = line.split("#", 1)[0].split(";", 1)[0]
        normalized = "".join(without_comment.split())
        if normalized:
            normalized_lines.append(normalized)

    has_min_constraint = any(
        "pytest>=9.0.0" in entry for entry in normalized_lines
    )
    assert has_min_constraint, (
        "requirements-dev.txt missing pytest>=9.0.0 constraint"
    )


def test_tests_package_init_exists():
    init_file = _repo_root() / "tests" / "__init__.py"
    assert init_file.exists(), "Expected tests/__init__.py to exist"
