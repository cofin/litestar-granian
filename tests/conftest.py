from __future__ import annotations

import importlib.util
import operator
import sys
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Callable, Protocol, cast

import pytest
from click.testing import CliRunner
from litestar.cli._utils import (
    LitestarGroup,
    _path_to_dotted_path,  # noqa: PLC2701
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from unittest.mock import MagicMock

    from _pytest.fixtures import FixtureRequest
    from pytest_mock import MockerFixture

pytestmark = pytest.mark.anyio
here = Path(__file__).parent


APP_DEFAULT_CONFIG_FILE_CONTENT = """
from __future__ import annotations

import os
import signal

import anyio
from litestar import Controller, Litestar, get

from litestar_granian import GranianPlugin


async def dont_run_forever() -> None:
    await anyio.sleep(5)
    os.kill(os.getpid(), signal.SIGTERM)


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever])

"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_litestar_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITESTAR_APP", raising=False)


@pytest.fixture
def patch_autodiscovery_paths(request: FixtureRequest) -> Callable[[list[str]], None]:
    def patcher(paths: list[str]) -> None:
        from litestar.cli._utils import AUTODISCOVERY_FILE_NAMES  # noqa: PLC2701

        old_paths = AUTODISCOVERY_FILE_NAMES[::]
        AUTODISCOVERY_FILE_NAMES[:] = paths

        def finalizer() -> None:
            AUTODISCOVERY_FILE_NAMES[:] = old_paths

        request.addfinalizer(finalizer)

    return patcher


class CreateAppFileFixture(Protocol):
    def __call__(
        self,
        file: str | Path,
        directory: str | Path | None = None,
        content: str | None = None,
        init_content: str = "",
        subdir: str | None = None,
    ) -> Path: ...


def _purge_module(module_names: list[str], path: str | Path) -> None:
    for name in module_names:
        if name in sys.modules:
            del sys.modules[name]
    Path(importlib.util.cache_from_source(path)).unlink(missing_ok=True)  # type: ignore[arg-type]


@pytest.fixture()
def root_command() -> LitestarGroup:
    import litestar.cli.main

    return cast("LitestarGroup", importlib.reload(litestar.cli.main).litestar_group)


@pytest.fixture(autouse=True)
def tmp_project_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "project_dir"
    path.mkdir(exist_ok=True)
    monkeypatch.chdir(path)
    return path


@pytest.fixture
def create_app_file(tmp_project_dir: Path, request: FixtureRequest) -> CreateAppFileFixture:
    def _create_app_file(
        file: str | Path,
        directory: str | Path | None = None,
        content: str | None = None,
        init_content: str = "",
        subdir: str | None = None,
    ) -> Path:
        base = tmp_project_dir
        if directory:
            base /= Path(Path(directory) / subdir) if subdir else Path(directory)
            base.mkdir(parents=True)
            base.joinpath("__init__.py").write_text(init_content)

        tmp_app_file = base / file
        tmp_app_file.write_text(content or APP_DEFAULT_CONFIG_FILE_CONTENT)

        if directory:
            request.addfinalizer(lambda: rmtree(directory))
            request.addfinalizer(
                lambda: _purge_module(
                    [directory, _path_to_dotted_path(tmp_app_file.relative_to(Path.cwd()))],  # type: ignore[list-item]
                    tmp_app_file,
                ),
            )
        else:
            request.addfinalizer(tmp_app_file.unlink)
            request.addfinalizer(lambda: _purge_module([str(file).replace(".py", "")], tmp_app_file))
        return tmp_app_file

    return _create_app_file


@pytest.fixture
def app_file(create_app_file: CreateAppFileFixture) -> Path:
    return create_app_file("app.py")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_granian_worker(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("granian._granian.ASGIWorker")


@pytest.fixture()
def mock_subprocess_run(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("subprocess.run")


@pytest.fixture
def mock_confirm_ask(mocker: MockerFixture) -> Generator[MagicMock, None, None]:
    yield mocker.patch("rich.prompt.Confirm.ask", return_value=True)


@pytest.fixture(
    params=[
        pytest.param((APP_DEFAULT_CONFIG_FILE_CONTENT, "app"), id="app_obj"),
    ],
)
def _app_file_content(request: FixtureRequest) -> tuple[str, str]:  # pyright: ignore[reportUnusedFunction]
    return cast("tuple[str, str]", request.param)


@pytest.fixture
def app_file_content(app_file_content_: tuple[str, str]) -> str:
    return cast("str", operator.itemgetter(0)(app_file_content_))


@pytest.fixture
def app_file_app_name(app_file_content_: tuple[str, str]) -> str:
    return cast("str", operator.itemgetter(1)(app_file_content_))
