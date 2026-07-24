from litestar import Litestar, get

from litestar_granian import GranianPlugin


@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}


app = Litestar(route_handlers=[hello], plugins=[GranianPlugin()])
