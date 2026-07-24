from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
CODE_ROOTS = ("litestar_granian", "docs", "tools")


def test_non_test_code_does_not_postpone_annotations() -> None:
    future_import = "from __future__ import annotations"
    offending_files = [
        path.relative_to(PROJECT_ROOT)
        for root_name in CODE_ROOTS
        for path in (PROJECT_ROOT / root_name).rglob("*.py")
        if future_import in path.read_text(encoding="utf-8")
    ]

    assert offending_files == []
