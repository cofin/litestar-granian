from __future__ import annotations

import structlog
from litestar import Controller, Litestar, get
from litestar.logging.config import StructLoggingConfig

from litestar_granian import GranianPlugin

logger = structlog.get_logger()


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController], logging_config=StructLoggingConfig())
