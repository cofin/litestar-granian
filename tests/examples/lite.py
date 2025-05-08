# ruff: noqa: PLR6301
from __future__ import annotations

from pathlib import Path

import anyio
from litestar import Controller, Litestar, MediaType, Response, get
from litestar.exceptions import NotFoundException
from litestar.plugins.structlog import StructlogPlugin

from litestar_granian import GranianPlugin

__all__ = ("SampleController",)


HERE = Path(__file__).parent


class SampleController(Controller):
    @get("/", opt={"exclude_from_auth": True})
    async def index(self) -> Response:
        exists = await anyio.Path(Path(__file__).parent / "index.html").exists()
        if exists:
            async with await anyio.open_file(anyio.Path(HERE / "index.html")) as file:
                content = await file.read()
                return Response(content=content, status_code=200, media_type=MediaType.HTML)
        msg = "Site index was not found"
        raise NotFoundException(msg)

    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin(), StructlogPlugin()], route_handlers=[SampleController])
