"""Architecture guard: src/ats_scanner/core/ must stay pure."""

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "src" / "ats_scanner" / "core"

FORBIDDEN_ROOTS = {
    "fastapi",  # transport
    "pdfplumber",  # document adapter
    "docx",  # document adapter
    "requests",  # HTTP client
    "httpx",  # HTTP client
    "aiohttp",  # HTTP client
    "urllib3",  # HTTP client
    "http.client",  # stdlib HTTP client
    "urllib.request",  # stdlib HTTP client
    "socket",  # network I/O
}


def iter_imported_roots(tree: ast.Module) -> set[str]:
    """Absolute module names imported by an AST, reduced to comparable roots."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    roots = set()
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            roots.add(".".join(parts[:i]))
    return roots


def test_core_imports_no_fastapi_parsers_or_http_clients() -> None:
    offenders: list[str] = []
    for path in sorted(CORE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = iter_imported_roots(tree) & FORBIDDEN_ROOTS
        offenders.extend(f"{path.name}: {name}" for name in sorted(bad))
    assert offenders == [], f"core/ imports forbidden modules: {offenders}"
