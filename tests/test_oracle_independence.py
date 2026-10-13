"""Mechanically checks, by parsing the AST rather than trusting a docstring,
that src/tasks/oracle.py never imports the orchestrators, the MCP servers,
or the ADK agents it is grading. This is the same check
agent-task-environment-state-benchmark uses for its reference simulator."""

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = ("src.orchestrator", "src.mcp_servers", "src.adk_app")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            prefix = "." * node.level
            modules.add(prefix + node.module)
    return modules


def test_oracle_does_not_import_orchestrators_or_servers():
    oracle_path = Path(__file__).resolve().parents[1] / "src" / "tasks" / "oracle.py"
    modules = _imported_modules(oracle_path)
    for mod in modules:
        for forbidden in FORBIDDEN_PREFIXES:
            assert forbidden not in mod, f"oracle.py imports {mod}, which touches {forbidden}"
