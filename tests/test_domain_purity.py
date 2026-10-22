"""Tests enforcing domain layer purity and layer isolation."""

import ast
from pathlib import Path

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


def test_domain_layer_purity_ast() -> None:
    """Enforce that app/domain imports nothing from outer layers or I/O modules."""
    domain_dir = Path("app/domain")
    assert domain_dir.exists(), "app/domain directory must exist"

    domain_files = list(domain_dir.glob("*.py"))
    assert len(domain_files) > 0, "app/domain must contain python source files"

    violations: list[str] = []

    for file_path in domain_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_IMPORTS:
                        if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                            violations.append(
                                f"{file_path}: imports forbidden module '{alias.name}'"
                            )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for forbidden in FORBIDDEN_IMPORTS:
                    if module == forbidden or module.startswith(f"{forbidden}."):
                        violations.append(f"{file_path}: imports from forbidden module '{module}'")

            # Check for direct calls to datetime.now() or datetime.utcnow()
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("now", "utcnow")
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                violations.append(
                    f"{file_path}: direct call to datetime.{node.func.attr}() forbidden; "
                    "time must be injected"
                )

    assert not violations, "Domain purity violated:\n" + "\n".join(violations)
