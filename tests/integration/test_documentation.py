"""Integration and behavioral tests for Zensical documentation and docs tooling."""

from __future__ import annotations

import json
import logging.config
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

import litestar_granian
from litestar_granian.cli import run_command
from tools.docs.generate_cli_docs import main as generate_cli_main
from tools.docs.generate_cli_docs import render_cli_reference
from tools.docs.postbuild import build_postbuild_artifacts
from tools.docs.scan_public_docstrings import (
    main as scan_docstrings_main,
)
from tools.docs.scan_public_docstrings import (
    scan_overload_docstrings,
    scan_public_docstring_leaks,
    scan_undocumented_typeddicts,
)
from tools.docs.verify_docs_artifacts import DocsVerificationError, verify_site_artifacts

_ROOT = Path(__file__).parents[2]
_DOCS = _ROOT / "docs"
_EXAMPLES = _DOCS / "examples"
_CANONICAL_ARTIFACTS = {
    Path("__init__.py"),
    Path("app.py"),
    Path("logging.json"),
    Path("static/index.html"),
}


def test_python_reference_covers_the_package_root_exports() -> None:
    """Verify docs/reference/plugin.md documents all package root exports and suppresses internal hooks."""
    reference = (_DOCS / "reference" / "plugin.md").read_text(encoding="utf-8")

    assert litestar_granian.__all__ == ("GranianPlugin", "__project__", "__version__")
    for exported_name in litestar_granian.__all__:
        assert f"litestar_granian.{exported_name}" in reference
    assert "merge_init_into_class: true" in reference
    assert "members: false" in reference


def test_public_docstrings_and_cli_reference_are_up_to_date() -> None:
    """Verify public docstrings pass hygiene gates and docs/reference/cli.md is in sync with run_command."""
    pkg_dir = _ROOT / "litestar_granian"
    assert scan_public_docstring_leaks([pkg_dir]) == []
    assert scan_overload_docstrings([pkg_dir]) == []
    assert scan_undocumented_typeddicts([pkg_dir]) == []
    assert scan_docstrings_main(["--check-leaks", "--check-overloads", "--check-typeddicts", str(pkg_dir)]) == 0

    cli_doc = _DOCS / "reference" / "cli.md"
    assert cli_doc.read_text(encoding="utf-8") == render_cli_reference()
    assert generate_cli_main(["--check", "--output", str(cli_doc)]) == 0


def test_zensical_config_css_and_templates_follow_standards() -> None:
    """Verify zensical.toml, extra.css, and mkdocstrings templates enforce ecosystem invariants."""
    zensical_text = (_ROOT / "zensical.toml").read_text(encoding="utf-8")
    css_text = (_DOCS / "stylesheets" / "extra.css").read_text(encoding="utf-8")
    tpl_dir = _ROOT / "tools" / "docs" / "templates" / "python" / "material"
    summary_tpl = (tpl_dir / "summary" / "attributes.html.jinja").read_text(encoding="utf-8")
    docstring_tpl = (tpl_dir / "docstring" / "attributes.html.jinja").read_text(encoding="utf-8")

    assert '"navigation.indexes"' not in zensical_text
    assert 'site_url = "https://cofin.github.io/litestar-granian/"' in zensical_text
    assert 'repo_url = "https://github.com/cofin/litestar-granian"' in zensical_text
    assert "generator = false" in zensical_text
    assert "enable_inventory = true" in zensical_text

    assert "--granian-doc-guide-border:" in css_text
    assert ".md-typeset div.doc-contents:not(.first)" in css_text
    assert "border-left: 2px solid var(--granian-doc-guide-border);" in css_text
    assert "attribute.annotation or attribute.description" in summary_tpl
    assert "attribute.annotation or attribute.description" in docstring_tpl


def test_postbuild_and_verify_docs_artifacts_on_synthetic_site(tmp_path: Path) -> None:
    """Verify postbuild HTML compaction, llms.txt generation, flat .html redirects, and artifact verification."""
    docs_dir = tmp_path / "docs"
    site_dir = tmp_path / "site"
    (docs_dir / "getting-started").mkdir(parents=True)
    (docs_dir / "assets").mkdir(parents=True)
    (site_dir / "getting-started").mkdir(parents=True)
    (site_dir / "reference" / "plugin").mkdir(parents=True)
    (site_dir / "assets").mkdir(parents=True)

    logo_svg = (_DOCS / "assets" / "logo.svg").read_text(encoding="utf-8")
    (docs_dir / "assets" / "favicon.svg").write_text(logo_svg, encoding="utf-8")
    (site_dir / "assets" / "logo.svg").write_text(logo_svg, encoding="utf-8")
    (site_dir / "assets" / "favicon.svg").write_text(logo_svg, encoding="utf-8")

    (docs_dir / "index.md").write_text("# Litestar Granian\n\nSupervised Granian plugin.\n", encoding="utf-8")
    (docs_dir / "getting-started" / "quickstart.md").write_text(
        "# Quickstart\n\nRun `litestar run`.\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "zensical.toml"
    config_path.write_text(
        """
[project]
site_name = "Litestar Granian"
site_description = "Run Litestar applications with Granian."
site_url = "https://cofin.github.io/litestar-granian/"
docs_dir = "docs"
site_dir = "site"
nav = [
  { "Home" = "index.md" },
  { "Getting Started" = [
    { "Quickstart" = "getting-started/quickstart.md" },
  ] },
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (site_dir / "objects.inv").write_bytes(b"Sphinx inventory version 2\n")
    (site_dir / "index.html").write_text(
        "<!doctype html><html><body>"
        '  <div class="granian-hero"><span class="granian-brand-text">Litestar Granian</span></div>\n'
        "  <pre>    indented = True\n</pre>\n"
        "</body></html>",
        encoding="utf-8",
    )
    (site_dir / "getting-started" / "quickstart").mkdir(parents=True)
    (site_dir / "getting-started" / "quickstart" / "index.html").write_text(
        "<!doctype html><html><body>"
        '<nav class="md-nav md-nav--secondary"><a href="#install">Install</a></nav>'
        '<h1 id="quickstart">Quickstart</h1><h2 id="install">Install</h2>'
        "</body></html>",
        encoding="utf-8",
    )
    (site_dir / "reference" / "plugin" / "index.html").write_text(
        "<!doctype html><html><body><h1 id='plugin'>Plugin</h1></body></html>",
        encoding="utf-8",
    )

    redirects_written = build_postbuild_artifacts(config_path=config_path, docs_dir=docs_dir, site_dir=site_dir)
    assert redirects_written >= 2
    assert (site_dir / "llms.txt").is_file()
    assert (site_dir / "llms-full.txt").is_file()
    assert (site_dir / "favicon.svg").is_file()
    assert (site_dir / "getting-started" / "quickstart.html").is_file()
    assert "    indented = True" in (site_dir / "index.html").read_text(encoding="utf-8")

    assert verify_site_artifacts(site_dir=site_dir) == []

    (site_dir / "reference" / "plugin" / "index.html").write_text(
        "<!doctype html><html><body>Made with Zensical</body></html>",
        encoding="utf-8",
    )
    with pytest.raises(DocsVerificationError, match="Made with Zensical"):
        verify_site_artifacts(site_dir=site_dir)


def test_rendered_zensical_build_when_installed() -> None:
    """Run a full Zensical build and verify rendered plugin reference when zensical is installed."""
    zensical_bin = shutil.which("zensical")
    if zensical_bin is None:
        pytest.skip("zensical is installed in the doc dependency group")

    site_dir = _ROOT / "site"
    config_path = _ROOT / "zensical.toml"

    subprocess.run([zensical_bin, "build", "--clean"], cwd=_ROOT, check=True)
    build_postbuild_artifacts(config_path=config_path, docs_dir=_DOCS, site_dir=site_dir)
    assert verify_site_artifacts(site_dir=site_dir) == []

    rendered = (site_dir / "reference" / "plugin" / "index.html").read_text(encoding="utf-8")
    assert "GranianPlugin" in rendered
    assert "static" in rendered
    assert "on_cli_init" not in rendered
    assert "on_app_init" not in rendered


def test_readme_quickstart_matches_the_canonical_app() -> None:
    """Verify the README quickstart block matches docs/examples/app.py."""
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    source = (_EXAMPLES / "app.py").read_text(encoding="utf-8").strip()
    match = re.search(
        r"<!-- quickstart-app:start -->\n```python\n(?P<source>.*?)\n```\n<!-- quickstart-app:end -->",
        readme,
        flags=re.DOTALL,
    )

    assert match is not None
    assert match.group("source").strip() == source


def test_readme_and_project_metadata_align_with_deployed_docs() -> None:
    """Verify README banner/links and package metadata target the deployed docs site."""
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    zensical = tomllib.loads((_ROOT / "zensical.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    urls = project["urls"]
    site_url = "https://cofin.github.io/litestar-granian/"

    assert "banner-inline-dark.svg" in readme
    assert "banner-inline-light.svg" in readme
    assert f"({site_url})" in readme
    assert f"({site_url}contribution-guide/)" in readme
    assert "(docs/" not in readme

    assert project["description"] == zensical["project"]["site_description"]
    assert urls["Homepage"] == site_url
    assert urls["Documentation"] == site_url
    assert urls["Changelog"] == f"{site_url}changelog/"
    assert "litestar" in project["keywords"]
    assert "granian" in project["keywords"]
    assert "litestar-plugin" in project["keywords"]


def test_every_displayed_artifact_exists_is_referenced_and_is_exercisable() -> None:
    """Verify every file in docs/examples is referenced by Markdown docs and valid."""
    artifacts = {
        path.relative_to(_EXAMPLES)
        for path in _EXAMPLES.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    docs_source = "\n".join(path.read_text(encoding="utf-8") for path in _DOCS.rglob("*.md"))

    assert artifacts >= _CANONICAL_ARTIFACTS
    for artifact in _CANONICAL_ARTIFACTS - {Path("__init__.py")}:
        assert f"docs/examples/{artifact.as_posix()}" in docs_source

    config = json.loads((_EXAMPLES / "logging.json").read_text(encoding="utf-8"))
    logging.config.dictConfig(config)
    assert logging.getLogger("_granian").handlers
    assert (_EXAMPLES / "static" / "index.html").read_text(encoding="utf-8").strip() == "hello from static"


def test_documented_cli_recipes_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify every documented litestar run CLI recipe parses cleanly through run_command."""
    monkeypatch.chdir(_ROOT)
    commands: list[str] = []
    for path in [*_DOCS.rglob("*.md"), _ROOT / "README.md"]:
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
