# Configuration & Runtime

`GranianPlugin()` registers a Granian-backed `litestar run` command. Server settings belong on that command, while the plugin constructor controls native static-file auto-discovery.

## Bindings and Reload

The default binding is `127.0.0.1:8000`. Change it with `--host` and `--port`, or pass `--uds` (`--unix-domain-socket`) for a Unix domain socket. On POSIX systems, `--fd` (`--file-descriptor`) accepts an inherited listening socket.

```bash
litestar --app docs.examples.app:app run --host 0.0.0.0 --port 8080
```

Use `--reload` during development. Passing `--reload-paths` (`--reload-dir`), `--reload-include`, or `--reload-exclude` also enables reload automatically. Reload and `--workers-max-rss` are rejected before application resolution on free-threaded Python builds (`3.14t` and `3.15t`) because Granian does not support those combinations on thread-based workers.

## Workers, Runtime, and Event Loops

- `--workers` (`--web-concurrency` or `--wc`) selects the number of application workers.
- `--runtime-threads` selects Rust network I/O threads per worker.
- `--runtime-mode` selects Granian's Rust runtime mode (`auto`, `st`, or `mt`).
- `--loop` selects the Python event-loop implementation (`auto`, `asyncio`, `uvloop`, `rloop`, or `winloop`).
- `--backlog` limits queued connections on the listening socket (per worker on Linux TCP sockets and shared across workers on UDS, Windows, and macOS).
- `--backpressure` limits concurrent requests per worker. Size `--backpressure` to stay within your per-worker database connection pool limit (such as `pool_size + max_overflow`) so queued requests wait at Granian's edge rather than exhausting pool connections inside the application.

The base installation includes no optional event loop. Install an optional loop extra and select it explicitly when validating it:

=== "uv"
    ```bash
    uv add "litestar-granian[uvloop]"
    ```
=== "pip"
    ```bash
    pip install "litestar-granian[uvloop]"
    ```
=== "pdm"
    ```bash
    pdm add "litestar-granian[uvloop]"
    ```
=== "poetry"
    ```bash
    poetry add "litestar-granian[uvloop]"
    ```

Then pass `--loop` to `litestar run`:

```bash
litestar --app docs.examples.app:app run --loop uvloop
```

The equivalent extras are `rloop` (Unix) and `winloop` (Windows) on platforms where those packages are available. The public default remains `--loop auto`.

## HTTP, WebSockets, and TLS

- `--http auto` forwards both HTTP/1 and HTTP/2 settings.
- `--http 1` forwards only HTTP/1 settings.
- `--http 2` forwards only HTTP/2 settings and disables WebSockets because WebSockets require HTTP/1.1 in this server configuration.

For Granian-managed TLS, pass both a certificate and its PKCS#8 private key:

```bash
litestar --app docs.examples.app:app run --ssl-certificate server.crt --ssl-keyfile server.key
```

`--ssl-client-verify` also requires `--ssl-ca`. A reverse proxy can terminate TLS instead when that matches your deployment boundary.

## Worker Environment and Lifecycle

`--working-dir` and repeatable `--env-files` are forwarded to Granian. They configure the worker environment and do not change the Litestar parent's current directory or load dotenv values into parent-owned server lifespans.

Granian also exposes worker respawn, lifetime, RSS, PID-file, and process-name settings. `--workers-kill-timeout` controls Granian's graceful worker deadline, and the Litestar supervisor adds five seconds before forcefully reaping the child process group.

See the [CLI Reference](../reference/cli.md) for every switch, default, range, and environment variable.
