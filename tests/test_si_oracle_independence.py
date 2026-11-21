"""Mechanically checks, by parsing the AST rather than trusting a
docstring, that src/si_signoff/oracle.py never imports
src/si_signoff/physics.py or src/mcp_servers/si_physics_server.py, the
modules it is grading. Mirrors tests/test_oracle_independence.py."""

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = ("src.si_signoff.physics", "src.mcp_servers.si_physics_server",
                       "src.si_signoff.taskmaster", "src.si_signoff.free_form_orchestrator")


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


def test_si_oracle_does_not_import_physics_or_server():
    oracle_path = Path(__file__).resolve().parents[1] / "src" / "si_signoff" / "oracle.py"
    modules = _imported_modules(oracle_path)
    for mod in modules:
        for forbidden in FORBIDDEN_PREFIXES:
            assert forbidden not in mod, f"oracle.py imports {mod}, which touches {forbidden}"
