# Compatibility & Behaviour

## Package Requirements

`litestar-granian` requires Python `>= 3.11`, Litestar `>= 2.19.0`, and Granian `>= 2.8.5`. Its public runtime API exports:

- [`litestar_granian.GranianPlugin`](plugin.md#litestar_granian.GranianPlugin)
- [`litestar_granian.__project__`](plugin.md#litestar_granian.__project__)
- [`litestar_granian.__version__`](plugin.md#litestar_granian.__version__)

## CLI Aliases

The plugin owns Litestar's `run` compatibility surface. It preserves Litestar option aliases when they describe the same setting and forwards Granian-native option names to the child process group.

| Litestar-Compatible Spelling | Granian Setting |
| --- | --- |
| `--web-concurrency` or `--wc` | `--workers` |
| `--unix-domain-socket` | `--uds` |
| `--ssl-certfile` | `--ssl-certificate` |
| `--reload-dir` | `--reload-paths` |
| `--access-log` or `--no-access-log` | `--granian-access-log` or `--granian-no-access-log` |
| `--access-log-fmt` | `--granian-access-log-fmt` |

## Environment Precedence

Shared settings accept both environment variable namespaces. An explicit command-line flag always wins; otherwise `LITESTAR_*` takes precedence over the equivalent `GRANIAN_*` variable. For example, `LITESTAR_PORT` takes precedence over `GRANIAN_PORT`.

The generated [CLI Reference](cli.md) lists the accepted environment variables alongside each option.

## Optional Event Loops

The base package installs no optional event loop. The `rloop`, `uvloop`, and `winloop` extras install the matching Granian integration. Install only the loop being validated and pass its explicit `--loop` value when testing it. `--loop auto` remains the default.
