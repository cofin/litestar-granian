# Changelog

All notable changes to `litestar-granian` are documented in this file.

## 0.17.0

### Added

- Added `--access-log`/`--no-access-log` and `--access-log-fmt` CLI aliases for `--granian-access-log`/`--granian-no-access-log` and `--granian-access-log-fmt` ([#82](https://github.com/cofin/litestar-granian/pull/82)).

### Changed

- Dropped Python 3.10 support (`requires-python = ">=3.11"`) and added Python 3.15 and 3.15t (free-threaded) support and CI coverage ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Updated minimum Granian requirement to `granian[all]>=2.8.5` (and the `rloop`, `uvloop`, and `winloop` extras to `>=2.8.5`), adopting Granian 2.8's per-worker `SO_REUSEPORT` TCP listener sockets on Linux, `%(header{...})s` access log format atoms, and upstream free-threaded Python (`3.14t`) lifecycle fixes ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Updated `--backlog` CLI help text and configuration guidance to reflect Granian 2.8's per-socket backlog semantics and documented `--backpressure` sizing relative to per-worker database connection pools ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Retained `--in-subprocess`/`--no-subprocess` and `--use-litestar-logger`/`--no-litestar-logger` as deprecated no-op compatibility switches for `0.17.0`, planned for removal in `0.18` ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Added `slots=True` to `_GranianCommand` and `_StaticMounts` ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Migrated documentation to Zensical with `mkdocstrings-python`, automated CLI reference generation, `llms.txt` / `llms-full.txt` artifacts, and HTML verification gates ([#82](https://github.com/cofin/litestar-granian/pull/82)).
- Bumped `actions/checkout` to `v7.0.1`, `actions/setup-python` to `v6.2.0`, `actions/upload-pages-artifact` to `v5`, `actions/deploy-pages` to `v5`, `astral-sh/setup-uv` to `v10.3.2`, and `pypa/gh-action-pypi-publish` to `v1.14.3` across GitHub Actions workflows ([#82](https://github.com/cofin/litestar-granian/pull/82), [#84](https://github.com/cofin/litestar-granian/pull/84), [#85](https://github.com/cofin/litestar-granian/pull/85)).

### Fixed

- Promoted the free-threaded Python (`3.14t`) repeated metrics lifecycle ([emmett-framework/granian#881](https://github.com/emmett-framework/granian/issues/881)) and WebSocket teardown ([emmett-framework/granian#884](https://github.com/emmett-framework/granian/issues/884)) diagnostics to standard integration regressions now that both upstream defects are fixed in Granian 2.8.5 ([#82](https://github.com/cofin/litestar-granian/pull/82)).

## 0.16.0

### Modified Behavior

- `litestar run` now has one execution model: the Litestar parent enters server lifespans once and supervises a fresh Granian child process group.
- `--in-subprocess`/`--no-subprocess` and `--use-litestar-logger`/`--no-litestar-logger` remain as deprecated no-op compatibility switches for `0.16`. Supervision and automatic formatter matching remain unconditional.
- Restored Litestar's `-I`/`--reload-include` and `-E`/`--reload-exclude` glob behavior. Reload directories and filters now enable reload automatically, matching `litestar run`.
- Added Litestar-compatible `-F`/`--fd`/`--file-descriptor` inherited socket support on POSIX.
- Added Litestar-compatible `-U` and `--unix-domain-socket` aliases for Granian's retained native `--uds` option.
- `--pdb`/`--use-pdb` and `LITESTAR_PDB=true` now propagate Litestar's `pdb_on_exception` behavior into Granian workers.
- Granian metrics are explicit and disabled by default. When `--metrics` is used without Litestar Prometheus middleware, the command warns that only Granian server and worker metrics will be exported.
- The deprecated `InitPluginProtocol` base is replaced by `InitPlugin`.

### Supervisor and Lifespans

- POSIX starts Granian in a new session and forwards signals to the process group. Windows uses a new process group, `CTRL_BREAK_EVENT` for graceful shutdown, and list-based `taskkill` only after escalation.
- The first termination signal is forwarded once and starts a deadline equal to `--workers-kill-timeout` plus five seconds. A second signal or expired deadline kills the Granian process group.
- Litestar's server lifespans remain active until Granian exits and are still unwound after forced termination.
- The resolved application path, bind host, and bind port are available to server-lifespan sidecars as `LITESTAR_APP`, `LITESTAR_HOST`, and `LITESTAR_PORT`, and previous environment values are restored afterward.
- Granian's exact child status is returned; signal exits use `128 + signal`.

### Logging

- Granian now matches Litestar's active compatible formatter automatically. Direct handlers, queue-listener output handlers, propagation/root handlers, and structurally compatible configuration fallback are supported without classifying the formatter as standard, JSON, or `structlog`.
- Formatter presentation is no longer a plugin mode or built-in schema. Optional `structlog` and JSON packages remain application choices and are not production dependencies of this plugin.
- Generated configurations deep-copy Granian's native logging configuration and replace only its `generic` and `access` formatters. Parent handlers, queues, listeners, locks, loggers, and levels are never transplanted or mutated.
- One mode-`0600` generated file remains available for the complete supervised lifetime so worker reload and respawn reuse the same formatter payload. It is removed idempotently after normal exit, startup failure, signal termination, or lifespan failure.
- If no compatible formatter exists, Granian retains native formatting. If a selected formatter cannot be reconstructed, startup fails before serving with actionable `--log-config` guidance instead of silently changing presentation.
- Explicit `--log-config` bypasses matching and wins completely.

### Granian 2.7.9 Parity

- The plugin continues to own Litestar's `run` command surface and translates it to Granian. Litestar aliases are retained where their semantics match, Granian-native option spellings remain available, and both environment namespaces are accepted for equivalent settings with explicit `LITESTAR_*` precedence.
- CLI help presents every standard Litestar `run` option first, in Litestar's order, followed by Granian-specific extensions and then the deprecated compatibility shims.
- Removed the CPU-derived worker ceiling; `--workers` validates only a minimum of one.
- HTTP mode forwarding is protocol-aware. `auto` receives HTTP/1 and HTTP/2 settings, HTTP/1 receives only HTTP/1 settings, and HTTP/2 receives only HTTP/2 settings with WebSockets disabled.
- Updated every HTTP/2 numeric range to Granian 2.7.9.
- `--ssl-client-verify` requires `--ssl-ca`.
- Minimum dependencies updated to `litestar>=2.19.0` and `granian[all]>=2.7.9`. `rloop`, `uvloop`, and `winloop` extras are delegated through Granian; redundant direct `httptools` and `websockets` dependencies are removed.

### Static Serving

- Added `GranianPlugin(static="auto")` as a structural consumer of one plugin exposing `get_static_server_config()`.
- Discovery validates local absolute routes, existing non-empty directories, consistent directory-index values, and explicit fallback reasons.
- Missing, multiple, malformed, or ineligible providers produce one `INFO` fallback and leave serving to Litestar. Explicit CLI mounts always win.

### Documentation and Release Repair

- Replaced the stale direct/subprocess guide with beginner-first process, signal, logging, deployment, native-option, and migration documentation.
- Replaced the custom multiversion Pages builder with the official configure/upload/deploy actions and one current site artifact.
- Corrected project URLs to `https://cofin.github.io/litestar-granian/` and removed `latest/` assumptions.

### Known Upstream Limitations (2.7.9)

- Granian's open shutdown defect tracked in [emmett-framework/granian#875](https://github.com/emmett-framework/granian/issues/875).
- Granian 2.7.9 rejects reload on free-threaded Python.
- Granian metrics remain explicit because of the shutdown panic in [emmett-framework/granian#881](https://github.com/emmett-framework/granian/issues/881).
- The PyO3 pointer panic tracked in [emmett-framework/granian#884](https://github.com/emmett-framework/granian/issues/884).

## 0.15.0

### Breaking Changes

- `--runtime-mode` default changed from `single` (`st`) to `auto`. Pass `--runtime-mode st` explicitly if you relied on the old default.
- `--static-path-route` and `--static-path-mount` are repeatable for multi-mount serving. The previous implicit `/static` default has been removed.
- `--static-path-expires` type changed from `IntRange(min=60)` to `Duration(0)`. `0` disables caching; human-readable values like `1d` and `1h` are accepted.
- Duration type migrations: `--blocking-threads-idle-timeout`, `--workers-kill-timeout`, and `--http2-keep-alive-timeout` accept human-readable durations in addition to integer seconds.
- Minimum `granian` bumped to `>=2.7.0`.
- Python 3.9 support dropped; Python 3.14 and 3.14t (free-threaded) added to the test matrix.

### Migration Notes

- `_granian` and `granian.access` loggers are no longer overwritten when defined in user `LoggingConfig`.
- `granian.log.LOGGING_CONFIG` is no longer mutated across invocations.
- Added `--working-dir`, `--env-files`, `--log-config`, `--static-path-dir-to-file`, `--metrics`, `--metrics-scrape-interval`, `--metrics-address`, `--metrics-port`, `--reload-include`, `--reload-exclude`, and `--ssl-certfile`.
- Fixed `--pid-file` path serialization and `--respawn-failed-workers` subprocess forwarding.
