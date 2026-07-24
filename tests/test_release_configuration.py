"""Release-version configuration contract tests."""

import re
import subprocess
import sys
from pathlib import Path

import tomllib
from packaging.version import Version

ROOT = Path(__file__).parents[1]


def test_bumpversion_supports_pep440_prereleases() -> None:
    """The release configuration accepts and serializes each supported stage."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = config["project"]["version"]
    bumpversion = config["tool"]["bumpversion"]

    assert bumpversion["current_version"] == project_version
    assert Version(project_version)
    assert re.fullmatch(bumpversion["parse"], "0.16.0-beta.1")
    assert Version("0.16.0-beta.1").is_prerelease
    assert bumpversion["serialize"] == [
        "{major}.{minor}.{patch}",
        "{major}.{minor}.{patch}-{pre}.{pre_n}",
    ]
    assert bumpversion["parts"]["pre"]["values"] == ["alpha", "beta", "rc", "stable"]


def test_bumpversion_updates_each_version_source_once() -> None:
    """The config file is implicit; only the lockfile needs an explicit mapping."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    bumpversion = config["tool"]["bumpversion"]
    configured_files = [entry["filename"] for entry in bumpversion["files"]]

    assert configured_files == ["uv.lock"]
    lock_data = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    package = next(item for item in lock_data["package"] if item["name"] == "litestar-granian")
    assert package["version"] == config["project"]["version"]


def test_current_prerelease_can_finalize_without_advancing_release_line() -> None:
    """A release dry run strips the prerelease suffix from the current line."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    current_version = Version(config["project"]["version"])

    if not current_version.is_prerelease:
        return

    bump_my_version = Path(sys.executable).with_name("bump-my-version")
    assert bump_my_version.is_file()
    result = subprocess.run(
        [
            str(bump_my_version),
            "bump",
            "--dry-run",
            "--verbose",
            "--new-version",
            current_version.base_version,
            "pre",
        ],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert f"New version will be '{current_version.base_version}'" in output
