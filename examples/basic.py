from __future__ import annotations

from litestar import Controller, Litestar, get

from litestar_granian import GranianPlugin


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self ) -> dict[str, str]:
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController])
