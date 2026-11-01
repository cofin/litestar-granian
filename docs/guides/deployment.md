# Deployment & TLS

Start production deployments with an explicit worker count and public network binding:

```bash
litestar --app docs.examples.app:app run --host 0.0.0.0 --port 8000 --workers 4 --granian-access-log
```

Keep the `litestar` process at the top of the service tree. Service managers and container runtimes must send `SIGINT` or `SIGTERM` to that parent process rather than directly to a Granian worker.

## Process-Manager Checklist

- Use an init process (such as `tini` or Docker `--init`) when `litestar` runs as container PID 1 so exited descendants are reaped cleanly.
- Send one termination signal to the Litestar parent and allow `--workers-kill-timeout` plus five seconds before issuing an external `SIGKILL`.
- Probe the configured HTTP port for readiness.
- During shutdown, verify that the port closes and no Granian descendant process remains.
- Treat a non-zero child exit as a service failure; the parent preserves Granian's exit status.

## Signals and Exit Status

```mermaid
flowchart LR
    Signal["SIGINT / SIGTERM"] --> Parent["Litestar Parent"]
    Parent --> Forward["Forward Signal to Granian Group"]
    Forward --> Wait["Await workers-kill-timeout + 5s"]
    Wait --> Lifespan["Unwind Litestar server_lifespan"]
```

1. The first `SIGINT` or `SIGTERM` is forwarded to the Granian process group.
2. The parent waits for `--workers-kill-timeout` plus five seconds.
3. A second termination signal or an expired deadline forcefully terminates the Granian process group.
4. Litestar unwinds its `server_lifespan` context managers before the parent exits.

On POSIX, `SIGHUP` is forwarded to Granian, which treats it as a native worker-reload signal rather than a shutdown request. A terminal hangup therefore does not stop a supervised server; use `SIGINT` or `SIGTERM`. On Windows, the parent requests graceful shutdown with `CTRL_BREAK_EVENT` before falling back to a process-tree kill.

A normal Granian exit code is returned unchanged. A POSIX signal exit is normalized to the shell convention `128 + signal`, so an unhandled `SIGTERM` exit reports `143`.

## Environment Files and Working Directories

`--env-files` and `--working-dir` configure Granian workers only. Environment variables required by Litestar `server_lifespan` integrations must already exist in the parent process environment.

## Linux Socket Tuning for Worker Reloads

Granian 2.8+ binds independent per-worker listener sockets on Linux using `SO_REUSEPORT`. When a worker is stopped or respawned (such as via `SIGHUP`, `--workers-lifetime`, or `--respawn-failed-workers`), the Linux kernel requires kernel `>= 5.14` and `net.ipv4.tcp_migrate_req=1` to migrate pending `SYN` / `ACK` connection requests from the closing listener socket to surviving worker sockets without dropping client connections:

```bash
sysctl -w net.ipv4.tcp_migrate_req=1
```

To persist this setting across reboots, add `/etc/sysctl.d/99-granian.conf`:

```ini
net.ipv4.tcp_migrate_req = 1
```

For a complete option inventory, see the [CLI Reference](../reference/cli.md).
