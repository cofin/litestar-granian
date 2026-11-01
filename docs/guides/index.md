# Guides

Operational guides for configuring, observing, serving static files, and deploying Litestar applications with Granian.

## In This Section

| Guide | Topics Covered |
| --- | --- |
| **[Configuration & Runtime](configuration.md)** | Network bindings, hot reload, worker and Rust runtime thread tuning, optional event loops (`uvloop`, `rloop`, `winloop`), HTTP/1 and HTTP/2, and TLS. |
| **[Logging & Metrics](logging-and-metrics.md)** | Automatic Litestar formatter reconstruction in Granian workers, explicit `--log-config` JSON overrides, access logs, and Prometheus metrics. |
| **[Static Files](static-files.md)** | Native Rust static file mounts (`--static-path-mount`) and `GranianPlugin(static="auto")` provider discovery. |
| **[Deployment & TLS](deployment.md)** | Production worker topology, signal forwarding (`SIGINT`, `SIGTERM`, `SIGHUP`), graceful shutdown deadlines, and Linux `SO_REUSEPORT` tuning. |
