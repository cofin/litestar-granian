from __future__ import annotations

import ast
import json
import logging.config
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import litestar_granian
from litestar_granian.cli import run_command

_ROOT = Path(__file__).parents[1]
_DOCS = _ROOT / "docs"
_EXAMPLES = _DOCS / "examples"
_PACKAGE = _ROOT / "litestar_granian"
_CANONICAL_ARTIFACTS = {
    Path("__init__.py"),
    Path("app.py"),
    Path("logging.json"),
    Path("static/index.html"),
}


@pytest.fixture(scope="module")
def built_docs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("built-docs")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "sphinx",
            "-b",
            "html",
            "-W",
            "-E",
            "-a",
            "-q",
            str(_DOCS),
            str(output),
        ],
        cwd=_ROOT,
        check=True,
    )
    return output


def test_python_reference_covers_the_package_root_exports() -> None:
    reference = (_DOCS / "reference" / "plugin.rst").read_text(encoding="utf-8")

    assert litestar_granian.__all__ == ("GranianPlugin", "__project__", "__version__")
    for exported_name in litestar_granian.__all__:
        assert f"litestar_granian.{exported_name}" in reference


def test_rendered_plugin_reference_documents_constructor_but_not_hooks(built_docs: Path) -> None:
    rendered = (built_docs / "reference" / "plugin.html").read_text(encoding="utf-8")

    assert "GranianPlugin" in rendered
    assert "static" in rendered
    assert "log_style" in rendered
    assert "on_cli_init" not in rendered
    assert "on_app_init" not in rendered


def test_readme_quickstart_matches_the_canonical_app() -> None:
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    source = (_EXAMPLES / "app.py").read_text(encoding="utf-8").strip()
    match = re.search(
        r"<!-- quickstart-app:start -->\n```python\n(?P<source>.*?)\n```\n<!-- quickstart-app:end -->",
        readme,
        flags=re.DOTALL,
    )

    assert match is not None
    assert match.group("source").strip() == source
    assert 80 <= len(readme.splitlines()) <= 110


def test_every_displayed_artifact_exists_is_referenced_and_is_exercisable() -> None:
    artifacts = {
        path.relative_to(_EXAMPLES)
        for path in _EXAMPLES.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    docs_source = "\n".join(path.read_text(encoding="utf-8") for path in _DOCS.rglob("*.rst"))

    assert artifacts == _CANONICAL_ARTIFACTS
    for artifact in _CANONICAL_ARTIFACTS - {Path("__init__.py")}:
        assert f"examples/{artifact.as_posix()}" in docs_source

    config = json.loads((_EXAMPLES / "logging.json").read_text(encoding="utf-8"))
    logging.config.dictConfig(config)
    assert logging.getLogger("_granian").handlers
    assert (_EXAMPLES / "static" / "index.html").read_text(encoding="utf-8").strip() == "hello from static"


def test_documented_cli_recipes_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(_ROOT)
    commands = []
    for path in [*_DOCS.rglob("*.rst"), _ROOT / "README.md"]:
        commands.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("litestar --app ") and " run" in line
        )

    assert commands
    for command in commands:
        arguments = shlex.split(command)
        run_arguments = arguments[arguments.index("run") + 1 :]
        result = CliRunner().invoke(run_command, [*run_arguments, "--help"], terminal_width=200)
        assert result.exit_code == 0, f"{command}\n{result.output}"


def test_every_package_module_has_a_purpose_docstring() -> None:
    missing = [
        path.name
        for path in sorted(_PACKAGE.glob("*.py"))
        if ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) is None
    ]

    assert missing == []
