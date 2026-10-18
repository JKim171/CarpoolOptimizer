import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SHIPPED = [ROOT / "packages/domain/src", ROOT / "apps/api/src"]


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module


@pytest.mark.parametrize("source", SHIPPED, ids=lambda p: str(p.relative_to(ROOT)))
def test_shipped_code_never_imports_the_benchmark_dependencies(source):
    # The production image installs only the runtime lock, so one of these imports would pass
    # every test here and fail on the first request in production (docs/design.md 8.3).
    offending = [
        f"{path.relative_to(ROOT)}: {name}"
        for path in sorted(source.rglob("*.py"))
        for name in _imports(path)
        if name.split(".")[0] in {"ortools", "carpool_bench"}
    ]
    assert offending == []
