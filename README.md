# Litestar Granian

Run Litestar applications with Granian while preserving Litestar startup,
shutdown, logging, and server integrations.

## Install

```shell
python -m pip install litestar-granian
```

## Run your first app

Save this as `example.py`:

<!-- quickstart-app:start -->
```python
from litestar import Litestar, get

from litestar_granian import GranianPlugin


@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}


app = Litestar(route_handlers=[hello], plugins=[GranianPlugin()])
```
<!-- quickstart-app:end -->

Start the server:

```shell
litestar --app example:app run
```

Open <http://127.0.0.1:8000/> in a browser, or run:

```shell
curl http://127.0.0.1:8000/
```

You should receive:

```json
{"hello":"world"}
```

Press `Ctrl+C` in the server terminal to stop it.

## Why use this plugin?

- Keep the familiar `litestar run` command while using Granian.
- Start Litestar server integrations once around all Granian workers.
- Configure workers, protocols, logging, metrics, and static files from one CLI.

## What the plugin changes

`GranianPlugin()` replaces Litestar's standard `run` command with a
Granian-backed command. It does not change commands that start another ASGI
server directly.

Run the complete command reference with:

```shell
litestar --app example:app run --help
```

<details>
<summary>Optional event loops</summary>

The default installation uses Granian's standard loop selection and installs
no optional event loop. Install and select one integration at a time:

```shell
python -m pip install "litestar-granian[uvloop]"
litestar --app example:app run --loop uvloop
```

On supported platforms, use the matching `rloop` or `winloop` extra and pass
`--loop rloop` or `--loop winloop`.

</details>

## Next steps

- [Quickstart](docs/getting-started/quickstart.rst) — repeat the first run and
  learn what to check.
- [Configuration](docs/guides/configuration.rst) — choose bindings, workers,
  protocols, TLS, reload, and event loops.
- [Logging and metrics](docs/guides/logging-and-metrics.rst) — see how Granian
  automatically matches Litestar's formatter or accepts a complete override.
- [Deployment](docs/guides/deployment.rst) — forward signals and verify clean
  shutdown.
- [CLI reference](docs/reference/cli.rst) — browse every option and environment
  variable.

## License

`litestar-granian` is distributed under the [MIT License](LICENSE).
