=========
Changelog
=========

All commits to this project will be documented in this file.

Litestar Granian Changelog

Unreleased
==========

Breaking changes
----------------

- ``--runtime-mode`` default changed from ``single`` (``st``) to ``auto``.
  Pass ``--runtime-mode st`` explicitly if you relied on the old default.
- ``--static-path-route`` and ``--static-path-mount`` are now repeatable for
  multi-mount serving. The previous implicit ``/static`` default has been
  removed — you must now pass the route explicitly alongside the mount.
- ``--static-path-expires`` type changed from ``IntRange(min=60)`` to a
  ``Duration(0)``. ``0`` disables caching; human-readable values like
  ``1d`` / ``1h`` are accepted.
- Duration type migrations: ``--blocking-threads-idle-timeout``,
  ``--workers-kill-timeout``, ``--http2-keep-alive-timeout`` now accept
  human-readable durations in addition to integer seconds.
- Minimum ``granian`` is bumped to ``>=2.7.0``.

Direct mode and reload
----------------------

- ``--reload`` works with ``--no-subprocess`` again. Historically
  ``--reload`` silently forced subprocess mode because fork-workers
  inherit the parent process's ``sys.modules`` — respawned workers
  reused the cached app module and never saw source changes. The fix
  is in the parent: when reload is active we set the multiprocessing
  start method to ``spawn`` so each Granian respawn is a fresh Python
  interpreter. Direct mode is generally preferred because it keeps the
  parent's Litestar logging configuration intact without requiring
  ``--use-litestar-logger``.

Logging on macOS / Windows
--------------------------

- Queue-based log handlers (``litestar.logging.standard.QueueListenerHandler``,
  ``logging.handlers.QueueHandler``) are now neutralized to
  ``StreamHandler`` on macOS and Windows, where spawn workers cannot
  safely share the parent's listener threads. On Linux fork workers the
  queue handlers are preserved unchanged. This fixes the "logs after
  close" and interleaved-output symptoms tracked in issues #21 and #41.
- ``granian.log.LOGGING_CONFIG`` is no longer mutated across invocations
  — every call works on a fresh deepcopy.
- User-defined ``_granian`` / ``granian.access`` logger entries are now
  preserved instead of being clobbered with defaults.

New CLI options
---------------

- ``--working-dir PATH`` — set the worker working directory.
- ``--env-files PATH`` (repeatable) — dotenv files to load in workers.
- ``--log-config FILE`` — path to a JSON ``dictConfig`` file. When set,
  takes precedence over ``--use-litestar-logger``.
- ``--static-path-dir-to-file NAME`` — filename to serve for directory
  requests under a static mount (e.g. ``index.html`` for SPA mode).
- ``--metrics`` / ``--no-metrics`` — enable Granian's Prometheus metrics
  endpoint.
- ``--metrics-scrape-interval`` / ``--metrics-address`` / ``--metrics-port``
  — configure the metrics endpoint.
- Subprocess-mode forwarding of ``--use-litestar-logger`` now works:
  the parent serializes the computed dictconfig to a temp ``--log-config``
  file and passes its path to the child.

Uvicorn-compatible aliases (issue #61)
---------------------------------------

- ``--reload-include`` alias for ``--reload-paths``.
- ``--reload-exclude`` alias for ``--reload-ignore-dirs``.
- ``--ssl-certfile`` alias for ``--ssl-certificate``.

Auto-detection
--------------

- When ``PrometheusPlugin`` is registered on the Litestar app, ``--metrics``
  is auto-enabled (explicit ``--metrics`` / ``--no-metrics`` always wins).

Bug fixes
---------

- ``--pid-file`` now writes a real absolute path instead of the
  stringified ``<built-in method absolute>`` bound-method repr.
- ``--respawn-failed-workers`` is actually forwarded to the subprocess
  now; it was previously a silent no-op.
- Removed the unreachable ``sys.modules`` purge block in ``_run_granian``
  — it ran once at parent startup, not per-reload, so it could never
  have accomplished its stated goal.
- Removed dead/unguarded structlog branch in ``GranianPlugin.on_app_init``
  that double-updated ``_granian`` loggers and overwrote user config.
