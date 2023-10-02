# Litestar Granian Plugin

## Installation

```shell
pip install litestar-granian
```

## Usage

Here is a basic application that demonstrates how to use the plugin.

```python
from __future__ import annotations

from litestar import Controller, Litestar, get

from litestar_granian import GranianPlugin


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self ) -> dict[str, str]:
        """Sample Route."""
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController])

```

Now, you can use the standard Litestar CLI and it will run with Granian instead of Uvicorn.

```shell
❯ litestar --app examples.basic:app run
Using Litestar app from env: 'examples.basic:app'
Starting granian server process ──────────────────────────────────────────────
┌──────────────────────────────┬──────────────────────┐
│ Litestar version             │ 2.1.1                │
│ Debug mode                   │ Disabled             │
│ Python Debugger on exception │ Disabled             │
│ CORS                         │ Disabled             │
│ CSRF                         │ Disabled             │
│ OpenAPI                      │ Enabled path=/schema │
│ Compression                  │ Disabled             │
└──────────────────────────────┴──────────────────────┘
[INFO] Starting granian
[INFO] Listening at: 127.0.0.1:8000
[INFO] Spawning worker-1 with pid: 2719082
[INFO] Started worker-1
[INFO] Started worker-1 runtime-1
```
