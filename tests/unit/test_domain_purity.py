"""Tests enforcing domain layer purity and layer isolation."""

import ast
from pathlib import Path

import pytest

FORBIDDEN_IMPORTS = {
    "app.api",
    "app.application",
    "app.infrastructure",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "random",
    "os",
    "subprocess",
    "sqlalchemy",
    "alembic",
    "psycopg",
}


def find_purity_violations(source_code: str, file_label: str = "snippet") -> list[str]:
    """Parse python source and detect any illegal outer-layer or I/O imports."""
    violations: list[str] = []
    tree = ast.parse(source_code, filename=file_label)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_IMPORTS:
                    if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                        violations.append(f"{file_label}: imports forbidden module '{alias.name}'")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for forbidden in FORBIDDEN_IMPORTS:
                if module == forbidden or module.startswith(f"{forbidden}."):
                    violations.append(f"{file_label}: imports from forbidden module '{module}'")

        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("now", "utcnow")
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
        ):
            violations.append(
                f"{file_label}: direct call to datetime.{node.func.attr}() forbidden; "
                "time must be injected"
            )

    return violations


def test_domain_layer_purity_ast() -> None:
    """Enforce that app/domain imports nothing from outer layers or I/O modules."""
    domain_dir = Path("app/domain")
    assert domain_dir.exists(), "app/domain directory must exist"

    domain_files = list(domain_dir.glob("*.py"))
    assert len(domain_files) > 0, "app/domain must contain python source files"

    all_violations: list[str] = []
    for file_path in domain_files:
        content = file_path.read_text(encoding="utf-8")
        all_violations.extend(find_purity_violations(content, str(file_path)))

    assert not all_violations, "Domain purity violated:\n" + "\n".join(all_violations)


@pytest.mark.parametrize(
    "bad_snippet",
    [
        "from app.application.services import AuthorizationService",
        "from app.infrastructure.database import get_engine",
        "import app.api.routes",
        "import random\nx = random.randint(1, 10)",
        "from datetime import datetime\nnow = datetime.now()",
    ],
)
def test_domain_purity_detector_catches_violations(bad_snippet: str) -> None:
    """Verify that the purity detector correctly fails if forbidden imports or calls are made."""
    violations = find_purity_violations(bad_snippet, "synthetic_test.py")
    assert len(violations) > 0, f"Expected detector to catch violation in: {bad_snippet}"
