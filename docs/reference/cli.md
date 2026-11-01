# CLI Reference

```python
from litestar_granian.cli import run_command
```

When [`GranianPlugin`](plugin.md) is registered on a Litestar application, it replaces the standard `litestar run` command with the Granian-backed implementation below. See the [Configuration & Runtime Guide](../guides/configuration.md) for usage examples.

## Synopsis

```bash
litestar [--app MODULE:APP] run [OPTIONS]
```

Start application server

## Server & Binding

Network binding, socket handoff, HTTP/WebSocket protocol toggles, and process metadata.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-H` `--host` | `text` | `127.0.0.1` | Host address to bind to. Env: `LITESTAR_HOST` or `GRANIAN_HOST` |
| `-p` `--port` | `integer` | `8000` | Port to bind to. Env: `LITESTAR_PORT` or `GRANIAN_PORT` |
| `-F` `--fd` `--file-descriptor` | `integer` | - | Bind to a socket from this file descriptor. Env: `LITESTAR_FILE_DESCRIPTOR` or `GRANIAN_FILE_DESCRIPTOR` |
| `-U` `--uds` `--unix-domain-socket` | `path` | - | Unix Domain Socket path. Env: `LITESTAR_UNIX_DOMAIN_SOCKET` or `GRANIAN_UDS` |
| `--uds-permissions` | `octal integer` | - | Unix Domain Socket permissions (octal). Env: `GRANIAN_UDS_PERMISSIONS` |
| `--http` | `choice(auto | 1 | 2)` | `auto` | HTTP version to use: auto, HTTP/1, or HTTP/2. Env: `GRANIAN_HTTP` |
| `--ws/--no-ws` | `flag` | `enabled` | Enable or disable WebSocket handling. Env: `GRANIAN_WEBSOCKETS` |
| `--url-path-prefix` | `text` | - | URL path prefix the app is mounted on. Env: `GRANIAN_URL_PATH_PREFIX` |
| `--backlog` | `integer range` | `1024` | Maximum number of connections to hold in backlog. Env: `GRANIAN_BACKLOG` |
| `--backpressure` | `integer range` | `backlog/workers` | Maximum number of requests to process concurrently (per worker). Env: `GRANIAN_BACKPRESSURE` |
| `--working-dir` | `directory` | - | Working directory to use when starting Granian workers. Env: `GRANIAN_WORKING_DIR` |
| `--env-files` | `file` | - | One or more dotenv files to load before starting workers (repeatable). Env: `GRANIAN_ENV_FILES` |
| `--process-name` | `text` | - | Set a custom name for Granian processes. Env: `GRANIAN_PROCESS_NAME` |
| `--pid-file` | `file` | - | A path to write the PID file to. Env: `GRANIAN_PID_FILE` |

## Workers & Runtime

Granian worker concurrency, Rust tokio runtime threads, blocking thread pools, event loops, and worker respawn policies.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-W` `--wc` `--web-concurrency` `--workers` | `integer range` | `1` | Number of Granian application workers (processes on GIL builds; threads on free-threaded builds). Env: `LITESTAR_WEB_CONCURRENCY` or `WEB_CONCURRENCY` or `GRANIAN_WORKERS` |
| `--runtime-mode` | `choice(auto | mt | st)` | `auto` | Granian Rust runtime mode (single/multi-threaded/auto-detect); ASGI auto resolves to multi-threaded. Env: `GRANIAN_RUNTIME_MODE` |
| `--runtime-threads` | `integer range` | `1` | Number of Rust network I/O threads per worker; does not control Python application parallelism. Env: `GRANIAN_RUNTIME_THREADS` |
| `--runtime-blocking-threads` | `integer range` | - | Number of runtime I/O blocking threads (per worker). Env: `GRANIAN_RUNTIME_BLOCKING_THREADS` |
| `--blocking-threads` | `integer range` | - | Number of blocking threads (per worker). Env: `GRANIAN_BLOCKING_THREADS` |
| `--blocking-threads-idle-timeout` | `duration` | `30` | The maximum amount of time an idle blocking thread will be kept alive (supports human-readable format like '5m', '30s'). Env: `GRANIAN_BLOCKING_THREADS_IDLE_TIMEOUT` |
| `--loop` | `choice(auto | asyncio | rloop | uvloop | winloop)` | `auto` | Event loop implementation. Env: `GRANIAN_LOOP` |
| `--task-impl` | `choice(asyncio | rust)` | `asyncio` | Async task implementation to use. Env: `GRANIAN_TASK_IMPL` |
| `--respawn-failed-workers/--no-respawn-failed-workers` | `flag` | `disabled` | Enable workers respawn on unexpected exit. Env: `GRANIAN_RESPAWN_FAILED_WORKERS` |
| `--respawn-interval` | `float` | `3.5` | The number of seconds to sleep between workers respawn. Env: `GRANIAN_RESPAWN_INTERVAL` |
| `--workers-lifetime` | `duration` | - | The maximum amount of time a worker will be kept alive before respawn (supports human-readable format like '6h', '30m'). Env: `GRANIAN_WORKERS_LIFETIME` |
| `--workers-kill-timeout` | `duration` | `5` | Granian worker shutdown timeout; the parent deadline adds five seconds. Env: `GRANIAN_WORKERS_KILL_TIMEOUT` |
| `--workers-max-rss` | `integer range` | - | The maximum amount of memory (in MiB) a worker can consume before respawn. Env: `GRANIAN_WORKERS_MAX_RSS` |
| `--rss-sample-interval` | `duration` | `30` | The sample rate in seconds (or a human-readable duration) for the resource monitor. Env: `GRANIAN_RSS_SAMPLE_INTERVAL` |
| `--rss-samples` | `integer range` | `1` | The number of consecutive samples to consider a worker over resource limit. Env: `GRANIAN_RSS_SAMPLES` |

## HTTP/1, HTTP/2 & TLS

Protocol-specific buffer and window tuning plus TLS certificate, key, and mTLS client verification options.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--http1-buffer-size` | `integer range` | `417792` | Sets the maximum buffer size for HTTP/1 connections. Env: `GRANIAN_HTTP1_BUFFER_SIZE` |
| `--http1-header-read-timeout` | `integer range` | `30000` | Sets a timeout (in milliseconds) to read headers. Env: `GRANIAN_HTTP1_HEADER_READ_TIMEOUT` |
| `--http1-keep-alive/--no-http1-keep-alive` | `flag` | `enabled` | Enables or disables HTTP/1 keep-alive. Env: `GRANIAN_HTTP1_KEEP_ALIVE` |
| `--http1-pipeline-flush/--no-http1-pipeline-flush` | `flag` | `disabled` | Aggregates HTTP/1 flushes to better support pipelined responses (experimental). Env: `GRANIAN_HTTP1_PIPELINE_FLUSH` |
| `--http2-adaptive-window/--no-http2-adaptive-window` | `flag` | `disabled` | Sets whether to use an adaptive flow control for HTTP2. Env: `GRANIAN_HTTP2_ADAPTIVE_WINDOW` |
| `--http2-initial-connection-window-size` | `integer range` | `1048576` | Sets the max connection-level flow control for HTTP2. Env: `GRANIAN_HTTP2_INITIAL_CONNECTION_WINDOW_SIZE` |
| `--http2-initial-stream-window-size` | `integer range` | `1048576` | Sets the `SETTINGS_INITIAL_WINDOW_SIZE` option for HTTP2 stream-level flow control. Env: `GRANIAN_HTTP2_INITIAL_STREAM_WINDOW_SIZE` |
| `--http2-keep-alive-interval` | `integer range` | - | Sets the interval (in milliseconds) between HTTP/2 keep-alive pings. Env: `GRANIAN_HTTP2_KEEP_ALIVE_INTERVAL` |
| `--http2-keep-alive-timeout` | `duration` | `20` | Sets a timeout for receiving an acknowledgement of the HTTP2 keep-alive ping (supports human-readable format like '20s'). Env: `GRANIAN_HTTP2_KEEP_ALIVE_TIMEOUT` |
| `--http2-max-concurrent-streams` | `integer range` | `200` | Sets the SETTINGS_MAX_CONCURRENT_STREAMS option for HTTP2 connections. Env: `GRANIAN_HTTP2_MAX_CONCURRENT_STREAMS` |
| `--http2-max-frame-size` | `integer range` | `16384` | Sets the maximum frame size to use for HTTP2. Env: `GRANIAN_HTTP2_MAX_FRAME_SIZE` |
| `--http2-max-headers-size` | `integer range` | `16777216` | Sets the max size of received header frames. Env: `GRANIAN_HTTP2_MAX_HEADERS_SIZE` |
| `--http2-max-send-buffer-size` | `integer range` | `409600` | Set the maximum write buffer size for each HTTP/2 stream. Env: `GRANIAN_HTTP2_MAX_SEND_BUFFER_SIZE` |
| `--ssl-certfile` `--ssl-certificate` | `file` | - | SSL certificate file (Granian alias: --ssl-certificate). Env: `LITESTAR_SSL_CERT_PATH` or `GRANIAN_SSL_CERTIFICATE` |
| `--ssl-keyfile` | `file` | - | SSL private key file (PKCS#8 format only). Env: `LITESTAR_SSL_KEY_PATH` or `GRANIAN_SSL_KEYFILE` |
| `--ssl-keyfile-password` | `text` | - | SSL key password. Env: `GRANIAN_SSL_KEYFILE_PASSWORD` |
| `--ssl-protocol-min` | `choice(tls1.2 | tls1.3)` | `tls1.3` | Set the minimum supported protocol for SSL connections. Env: `GRANIAN_SSL_PROTOCOL_MIN` |
| `--ssl-ca` | `file` | - | Root SSL certificate file for client verification. Env: `GRANIAN_SSL_CA` |
| `--ssl-crl` | `file` | - | SSL CRL file(s). Env: `GRANIAN_SSL_CRL` |
| `--ssl-client-verify/--no-ssl-client-verify` | `flag` | `disabled` | Verify clients SSL certificates. Env: `LITESTAR_SSL_CLIENT_VERIFY` or `GRANIAN_SSL_CLIENT_VERIFY` |
| `--create-self-signed-cert` | `flag` | - | If certificate and key are not found at specified locations, create a self-signed certificate and a key. Env: `LITESTAR_CREATE_SELF_SIGNED_CERT` |

## Logging, Metrics & Static Files

Granian logging and access logs, built-in Prometheus metrics exporter, and Rust-served static file mounts.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `--granian-log/--granian-no-log` | `flag` | `enabled` | Enable logging. Env: `GRANIAN_LOG_ENABLED` |
| `--granian-log-level` | `choice(critical | error | warning | warn | info | debug | notset)` | `info` | Log level. Env: `GRANIAN_LOG_LEVEL` |
| `--granian-access-log` `--access-log` `--granian-no-access-log` `--no-access-log` | `flag` | `disabled` | Enable access log. Env: `GRANIAN_LOG_ACCESS_ENABLED` |
| `--granian-access-log-fmt` `--access-log-fmt` | `text` | - | Access log format. Env: `GRANIAN_LOG_ACCESS_FMT` |
| `--log-config` | `file` | - | Explicit Granian JSON dictConfig; completely overrides automatic formatter matching. Env: `GRANIAN_LOG_CONFIG` |
| `--metrics/--no-metrics` | `flag` | `disabled` | Enable Granian's built-in Prometheus metrics endpoint. Env: `GRANIAN_METRICS_ENABLED` |
| `--metrics-scrape-interval` | `duration` | `15` | Metrics sample interval (supports human-readable format like '15s', '1m'). Env: `GRANIAN_METRICS_SCRAPE_INTERVAL` |
| `--metrics-address` | `text` | `127.0.0.1` | Address to bind the metrics endpoint to. Env: `GRANIAN_METRICS_ADDRESS` |
| `--metrics-port` | `integer range` | `9090` | Port to bind the metrics endpoint to. Env: `GRANIAN_METRICS_PORT` |
| `--static-path-route` | `text` | - | URL route prefix for Granian-served static files. Repeat for multi-mount; paired positionally with --static-path-mount. Env: `GRANIAN_STATIC_PATH_ROUTE` |
| `--static-path-mount` | `directory` | - | Directory path for Granian to serve static files from. Repeat for multi-mount; paired positionally with --static-path-route. Env: `GRANIAN_STATIC_PATH_MOUNT` |
| `--static-path-dir-to-file` | `text` | - | Filename to serve for directory requests under a static mount (e.g. 'index.html'). Enables HTML mode for SPA-style serving. Env: `GRANIAN_STATIC_PATH_DIR_TO_FILE` |
| `--static-path-expires` | `duration` | `86400` | Cache expiration for Granian static files (supports human-readable format like '1d', '1h'). Pass 0 to disable caching. Env: `GRANIAN_STATIC_PATH_EXPIRES` |

## Development, Reload & Compatibility

Watchfiles auto-reload filters, Litestar debug/PDB toggles, and deprecated compatibility flags.

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `-r` `--reload` `--no-reload` | `flag` | `disabled` | Enable auto reload when application files change. Env: `LITESTAR_RELOAD` or `GRANIAN_RELOAD` |
| `-R` `--reload-dir` `--reload-paths` | `path` | - | Paths to watch for changes; repeatable. Env: `LITESTAR_RELOAD_DIRS` or `GRANIAN_RELOAD_PATHS` |
| `-I` `--reload-include` | `path` | - | Glob patterns for files to include when watching for file changes. Env: `LITESTAR_RELOAD_INCLUDES` or `GRANIAN_RELOAD_INCLUDE` |
| `-E` `--reload-exclude` | `path` | - | Glob patterns for files to exclude when watching for file changes. Env: `LITESTAR_RELOAD_EXCLUDES` or `GRANIAN_RELOAD_EXCLUDE` |
| `--reload-ignore-dirs` | `text` | - | Names of directories to ignore. Extends the default directory list in watchfiles' default filter. Env: `GRANIAN_RELOAD_IGNORE_DIRS` |
| `--reload-ignore-patterns` | `text` | - | File/directory name patterns (regex) to ignore changes for. Extends the default list of patterns to ignore in watchfiles' default filter. Env: `GRANIAN_RELOAD_IGNORE_PATTERNS` |
| `--reload-ignore-paths` | `path` | - | Absolute paths to ignore changes for. Env: `GRANIAN_RELOAD_IGNORE_PATHS` |
| `--reload-tick` | `integer range` | `50` | The tick frequency (in milliseconds) the reloader watch for changes. Env: `GRANIAN_RELOAD_TICK` |
| `--reload-ignore-worker-failure/--no-reload-ignore-worker-failure` | `flag` | `disabled` | Ignore worker failures when auto reload is enabled. Env: `GRANIAN_RELOAD_IGNORE_WORKER_FAILURE` |
| `-d` `--debug` | `flag` | - | Run app in debug mode. Env: `LITESTAR_DEBUG` |
| `-P` `--pdb` `--use-pdb` | `flag` | - | Drop into PDB on an exception. Env: `LITESTAR_PDB` |
| `--in-subprocess/--no-subprocess` | `flag` | `False` | Deprecated compatibility option; supervised execution is always used. Env: `LITESTAR_GRANIAN_IN_SUBPROCESS` or `GRANIAN_IN_SUBPROCESS` |
| `--use-litestar-logger/--no-litestar-logger` | `flag` | `False` | Deprecated compatibility option; formatter matching is automatic. Env: `LITESTAR_GRANIAN_USE_LITESTAR_LOGGER` or `GRANIAN_USE_LITESTAR_LOGGER` |
