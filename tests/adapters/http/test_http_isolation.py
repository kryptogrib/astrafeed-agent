"""HTTP handlers stay on the published snapshot: no cycle, no LLM import."""

import ast
from pathlib import Path

_HTTP = Path(__file__).resolve().parents[3] / "src" / "astrafeed" / "adapters" / "http"
_FORBIDDEN = ("astrafeed.adapters.llm", "astrafeed.application.agenda_cycle")


def test_http_adapters_do_not_import_llm_or_the_cycle():
    for path in _HTTP.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(name) for name in _FORBIDDEN), path
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name.startswith(name) for name in _FORBIDDEN), path
