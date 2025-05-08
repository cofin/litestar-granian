from __future__ import annotations

import os
import signal

import anyio
from litestar import Controller, Litestar, get

from litestar_granian import GranianPlugin

__all__ = ("SampleController", "dont_run_forever")


async def dont_run_forever() -> None:
    await anyio.sleep(5)
    os.kill(os.getpid(), signal.SIGTERM)


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever])
