<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/cofin/litestar-granian/main/docs/assets/banner-inline-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/cofin/litestar-granian/main/docs/assets/banner-inline-light.svg">
  <img alt="Litestar Granian" src="https://raw.githubusercontent.com/cofin/litestar-granian/main/docs/assets/banner-inline-light.svg" width="520">
</picture>

<p><strong>Granian HTTP and WebSocket server plugin for Litestar applications.</strong></p>

[![PyPI](https://img.shields.io/pypi/v/litestar-granian)](https://pypi.org/project/litestar-granian/)
[![Python](https://img.shields.io/pypi/pyversions/litestar-granian)](https://pypi.org/project/litestar-granian/)
[![License](https://img.shields.io/pypi/l/litestar-granian)](https://github.com/cofin/litestar-granian/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-litestar--granian-1d4ed8)](https://cofin.github.io/litestar-granian/)

[Documentation](https://cofin.github.io/litestar-granian/) · [Quickstart](https://cofin.github.io/litestar-granian/getting-started/quickstart/) · [Configuration](https://cofin.github.io/litestar-granian/guides/configuration/) · [Deployment](https://cofin.github.io/litestar-granian/guides/deployment/) · [CLI Reference](https://cofin.github.io/litestar-granian/reference/cli/) · [Plugin API](https://cofin.github.io/litestar-granian/reference/plugin/)

</div>

`litestar-granian` runs [Litestar](https://litestar.dev/) applications on [Granian](https://github.com/emmett-framework/granian)'s Rust HTTP/1, HTTP/2, and WebSocket runtime through the standard `litestar run` CLI. A supervised parent process manages `server_lifespan` hooks, forwards OS signals across the Granian worker group, bridges Litestar's active log formatters, and promotes static asset directories to Granian's native file server.

## Install

```bash
uv add litestar-granian
```

Or with `pip`:

```bash
pip install litestar-granian
```

Install an optional event loop extra when needed (`uvloop`, `rloop`, or `winloop`):

```bash
uv add "litestar-granian[uvloop]"
```

## Quickstart

Save as `example.py`:

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

Start the server with `litestar run`:

```bash
litestar --app example:app run
```

## Capabilities

| Area | Overview |
| --- | --- |
| **Drop-In `litestar run`** | Replaces Litestar's `run` command with Granian's HTTP/1, HTTP/2, and WebSocket server while keeping `LITESTAR_*` flags and environment variables. |
| **Process Supervision** | Runs `server_lifespan` context managers once in the parent process and forwards `SIGINT`/`SIGTERM` cleanly across the Granian worker process group. |
| **Log Formatter Bridge** | Reconstructs Litestar's active standard, JSON, or `structlog` formatters inside Granian workers, or accepts an explicit `--log-config` override. |
| **Native Static Files** | Serves static asset directories directly from Granian via `--static-path-mount` or automatic `GranianPlugin(static="auto")` discovery. |
| **Event Loops & Runtimes** | Supports `asyncio`, `uvloop`, `rloop`, and `winloop` across Python 3.11–3.15, including free-threaded `3.14t` and `3.15t` builds. |

## Documentation

- **[Getting Started & Quickstart](https://cofin.github.io/litestar-granian/getting-started/quickstart/)** — installation, first server run, and `v0.16` migration notes.
- **[Configuration & Runtime](https://cofin.github.io/litestar-granian/guides/configuration/)** — bindings, workers, runtime threads, HTTP/2, reload, and event loops.
- **[Logging & Metrics](https://cofin.github.io/litestar-granian/guides/logging-and-metrics/)** — automatic formatter matching, custom log configs, and Prometheus metrics.
- **[Static Files](https://cofin.github.io/litestar-granian/guides/static-files/)** — native Rust static asset mounts and SPA index rewrites.
- **[Deployment & TLS](https://cofin.github.io/litestar-granian/guides/deployment/)** — signal handling, container deployments, UNIX domain sockets, TLS, and mTLS.
- **[API & CLI Reference](https://cofin.github.io/litestar-granian/reference/)** — `GranianPlugin` API, `litestar run` CLI options, and compatibility notes.

## Contributing & License

Contributions are welcome; see the [Contribution Guide](https://cofin.github.io/litestar-granian/contribution-guide/) for local environment setup, testing, and release workflow. Distributed under the [MIT License](https://github.com/cofin/litestar-granian/blob/main/LICENSE).
