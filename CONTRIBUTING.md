# Contribution Guide

## Setting Up the Environment

1. Run `make install-uv` to install [uv](https://docs.astral.sh/uv/) if not already installed.
2. Run `make install` to install all dependencies and pre-commit hooks.

## Code Contributions

### Workflow

1. [Fork](https://github.com/cofin/litestar-granian/fork) the [`litestar-granian` repository](https://github.com/cofin/litestar-granian).
2. Clone your fork locally with `git`.
3. [Set up the environment](#setting-up-the-environment).
4. Make your changes.
5. Run `make lint` or `uvx prek run --all-files` to run linters and formatters.
6. Commit your changes to `git`.
7. Push the changes to your fork.
8. Open a [pull request](https://docs.github.com/en/pull-requests) with a descriptive Conventional Commit title indicating what it changes.

!!! tip
    Pull requests and commits must follow the [Conventional Commits](https://www.conventionalcommits.org) specification.

## Guidelines for Writing Code

- All code must be strictly [typed](https://peps.python.org/pep-0484/) and validated with [mypy](https://mypy.readthedocs.io/en/stable/) and Pyright.
- All code must be tested with [pytest](https://docs.pytest.org/en/stable/).
- All code must be formatted and linted with [Ruff](https://docs.astral.sh/ruff/).

### Writing and Running Tests

Run the complete test suite with `make test`. Use a focused `uv run pytest path/to/test_file.py` command while developing, then run `make lint`, `make type-check`, `make docs`, and `make build` before release.

Runtime changes should cover both focused command-building behavior and real subprocess shutdown. Signal tests must target the top-level Litestar PID and verify that the port closes, server lifespans unwind, and no Granian descendant is orphaned.

## Project Documentation

The documentation lives in the `docs/` directory and is built with [Zensical](https://zensical.org/) and [`mkdocstrings-python`](https://mkdocstrings.github.io/python/).

### Running the Docs Locally

Serve the documentation locally with `make docs-serve` or build and verify all documentation artifacts with `make docs`.

## Creating a New Release

1. Increment the version in [`pyproject.toml`](https://github.com/cofin/litestar-granian/blob/main/pyproject.toml) following [Semantic Versioning](https://semver.org/) and [PEP 440](https://peps.python.org/pep-0440/).
2. [Draft a new release](https://github.com/cofin/litestar-granian/releases/new) on GitHub using `vMAJOR.MINOR.PATCH` as both the tag and release title.
3. Commit your changes and push to `main`.
4. Publish the release and verify that the GitHub Actions release workflow completes cleanly.
