from __future__ import annotations

import asyncio
import asyncio.tasks
import os
import signal

from litestar import Controller, Litestar, get
from litestar.plugins.structlog import StructlogPlugin

from litestar_granian import GranianPlugin

__all__ = ("SampleController", "dont_run_forever")


async def dont_run_forever() -> None:
    async def _fn() -> None:
        await asyncio.sleep(5)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.ensure_future(_fn())


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(
    plugins=[GranianPlugin(), StructlogPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever]
)
