from __future__ import annotations

from pathlib import Path

import anyio
from litestar import Controller, Litestar, MediaType, get
from litestar.exceptions import NotFoundException
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK

from litestar_granian import GranianPlugin

here = Path(__file__).parent


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        """Sample Route."""
        return {"sample": "hello-world"}

    @get(path="/test")
    async def test_route(self) -> Response:
        """Sample Route."""
        exists = await anyio.Path(here / "index.html").exists()
        if exists:
            async with await anyio.open_file(anyio.Path(here / "index.html")) as file:
                content = await file.read()
                return Response(content=content, status_code=HTTP_200_OK, media_type=MediaType.HTML)
        msg = "Site index was not found"
        raise NotFoundException(msg)


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController])
