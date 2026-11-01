# Quickstart

This guide takes you from an empty file to a running Litestar application powered by Granian.

## Install

Install `litestar-granian` with your preferred package manager:

=== "uv"
    ```bash
    uv add litestar-granian
    ```
=== "pip"
    ```bash
    pip install litestar-granian
    ```
=== "pdm"
    ```bash
    pdm add litestar-granian
    ```
=== "poetry"
    ```bash
    poetry add litestar-granian
    ```

## Create the Application

Save this example as `example.py`:

```python
--8<-- "docs/examples/app.py"
```

## Run the Server

Start the regular Litestar CLI:

```bash
litestar --app example:app run
```

`GranianPlugin` registers the `run` command and starts Granian behind a supervised Litestar parent process.

## Verify the Endpoint

Open `http://127.0.0.1:8000/` in a browser, or run:

```bash
curl http://127.0.0.1:8000/
```

The response payload is:

```json
{"hello":"world"}
```

Press `Ctrl+C` in the server terminal. The port closes cleanly and the command returns to your shell after unwinding any Litestar server lifespans.

## Next Steps

- Read [Configuration & Runtime](../guides/configuration.md) for bindings, reload, protocols, TLS, workers, and optional event loops.
- Read [Deployment & TLS](../guides/deployment.md) for signal handling, graceful shutdown deadlines, and Linux socket tuning.
- Read [Logging & Metrics](../guides/logging-and-metrics.md) for automatic formatter matching and Prometheus metrics.
- Keep the [CLI Reference](../reference/cli.md) open for the complete option list.
