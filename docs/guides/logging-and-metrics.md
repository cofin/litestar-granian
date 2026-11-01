# Logging & Metrics

Granian automatically matches Litestar's active formatter. Configure logging once in Litestar, and the Granian server and access loggers will use the same standard, custom JSON, `structlog`, or other compatible formatter.

## Automatic Formatter Matching

Litestar and Granian run in separate processes, so they own separate logger and handler instances. Before serving, the plugin inspects Litestar's active logging graph and reconstructs only the effective formatter in Granian's process. It inspects:

- Direct Litestar handlers
- Queue-listener output handlers
- Propagated and root handlers
- Structurally compatible Litestar logging configuration when the active graph has no formatter

Discovery is strictly read-only. It does not call Litestar's `configure()`, start or stop queue listeners, change logger levels, or retain application-owned formatter objects. The generated configuration is a deep copy of Granian's native logging configuration with only its `generic` and `access` formatters replaced. Granian keeps its own handlers, loggers, streams, levels, queues, locks, and listener lifecycle.

The mode-`0600` generated configuration file remains available for the full supervised process lifetime, including worker reload and respawn, and is removed when the supervisor exits. Its serialized payload contains only the selected formatter's object graph, which can include formatter-owned state such as a `structlog` processor chain. It does not contain Litestar's logging configuration, handlers, queues, listeners, loggers, locks, or levels.

If Litestar has no compatible formatter, Granian keeps its native formatting. If an active formatter is selected but cannot be reconstructed, startup stops with an error that directs you to `--log-config` instead of silently changing output.

!!! note
    Automatic matching reproduces the active **formatter**, not the active **handler**. A handler that owns its own presentation — such as `rich.logging.RichHandler` — renders differently in the Granian child because handlers remain process-local by design and only the formatter crosses the process boundary. Use `--log-config` to configure an equivalent handler directly in Granian's process when handler-level presentation matters.

## Optional Formatting Packages

The plugin does not import or depend on `structlog` or any JSON logging package. Those libraries work automatically when your application installs and configures a compatible formatter upstream.

## Explicit Configuration

`--log-config` is a complete Granian logging override that bypasses automatic formatter matching.

This example uses direct `stdout` handlers:

```json
--8<-- "docs/examples/logging.json"
```

Run it with:

```bash
litestar --app docs.examples.app:app run --log-config docs/examples/logging.json
```

Granian server logging and access logging remain independent:

- Use `--granian-no-log` to disable server logs.
- Use `--access-log` (or `--granian-access-log`) to enable request access logs.
- Use `--access-log-fmt` (or `--granian-access-log-fmt`) to customize the access log format string, including Granian 2.8+'s `%(header{...})s` request header atom such as `%(header{x-forwarded-for})s`.

The retained `--use-litestar-logger` and `--no-litestar-logger` switches are deprecated no-ops that warn that formatter matching is automatic.

## Metrics

Prometheus metrics are disabled until `--metrics` is passed:

```bash
litestar --app docs.examples.app:app run --metrics
```

This exposes Granian server and worker metrics. When no Litestar Prometheus middleware or plugin is detected, the command warns that application-level request metrics are not included. Configure the exporter endpoint with `--metrics-address`, `--metrics-port`, and `--metrics-scrape-interval`.
