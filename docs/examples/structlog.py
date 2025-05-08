from __future__ import annotations

from litestar import Controller, Litestar, get
from litestar.plugins.structlog import StructlogPlugin

from litestar_granian import GranianPlugin

__all__ = ("SampleController", )


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        """Sample Route."""  # noqa: DOC201
        return {"sample": "hello-world"}


app = Litestar(
    plugins=[GranianPlugin(), StructlogPlugin()], route_handlers=[SampleController]
)
