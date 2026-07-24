import asyncio

from litestar import Litestar, WebSocket, get, websocket

from litestar_granian import GranianPlugin


@get("/cpu")
async def cpu(iterations: int = 25_000) -> dict[str, int]:
    checksum = 0
    for value in range(iterations):
        checksum = (checksum + value * value) % 1_000_000_007
    return {"checksum": checksum}


@get("/io")
async def io(delay: float = 0.01) -> dict[str, float]:
    await asyncio.sleep(delay)
    return {"delay": delay}


@get("/correctness/http2")
async def http2_correctness() -> dict[str, bool]:
    return {"ok": True}


@websocket("/correctness/ws")
async def websocket_correctness(socket: WebSocket) -> None:
    await socket.accept()
    await socket.send_text(await socket.receive_text())
    await socket.close()


app = Litestar(
    route_handlers=[cpu, io, http2_correctness, websocket_correctness],
    plugins=[GranianPlugin(log_style="json")],
)
