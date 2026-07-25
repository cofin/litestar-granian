=========
Changelog
=========

All commits to this project will be documented in this file.

Litestar Granian Changelog

0.16.0
======

Modified behavior
-----------------

- ``litestar run`` now has one execution model: the Litestar parent enters
  server lifespans once and supervises a fresh Granian child process group.
- ``--in-subprocess``/``--no-subprocess`` and
  ``--use-litestar-logger``/``--no-litestar-logger`` remain as deprecated
  no-op compatibility switches for 0.16. They warn when used and are planned
  for removal in 0.17. Supervision and automatic formatter matching remain
  unconditional.
- Restored Litestar's ``-I``/``--reload-include`` and
  ``-E``/``--reload-exclude`` glob behavior. Reload directories and filters
  now enable reload automatically, matching ``litestar run``.
- Added Litestar-compatible ``-F``/``--fd``/``--file-descriptor`` inherited
  socket support on POSIX.
- Added Litestar-compatible ``-U`` and ``--unix-domain-socket`` aliases for
  Granian's retained native ``--uds`` option.
- ``--pdb``/``--use-pdb`` and ``LITESTAR_PDB=true`` now propagate
  Litestar's ``pdb_on_exception`` behavior into Granian workers.
- Granian metrics are explicit and disabled by default. When ``--metrics`` is
  used without Litestar Prometheus middleware, the command warns that only
  Granian server and worker metrics will be exported.
- The deprecated ``InitPluginProtocol`` base is replaced by ``InitPlugin``.

Supervisor and lifespans
------------------------

- POSIX starts Granian in a new session and forwards signals to the process
  group. Windows uses a new process group, ``CTRL_BREAK_EVENT`` for graceful
  shutdown, and list-based ``taskkill`` only after escalation.
- The first termination signal is forwarded once and starts a deadline equal
  to ``--workers-kill-timeout`` plus five seconds. A second signal or expired
  deadline kills the Granian process group.
- Litestar's server lifespans remain active until Granian exits and are still
  unwound after forced termination.
- The resolved application path, bind host, and bind port are available to
  server-lifespan sidecars as ``LITESTAR_APP``, ``LITESTAR_HOST``, and
  ``LITESTAR_PORT``, and previous environment values are restored afterward.
- Granian's exact child status is returned; signal exits use ``128 + signal``.

Logging
-------

- Granian now matches Litestar's active compatible formatter automatically.
  Direct handlers, queue-listener output handlers, propagation/root handlers,
  and structurally compatible configuration fallback are supported without
  classifying the formatter as standard, JSON, or structlog.
- Formatter presentation is no longer a plugin mode or built-in schema.
  Optional structlog and JSON packages remain application choices and are not
  production dependencies of this plugin.
- Generated configurations deep-copy Granian's native logging configuration
  and replace only its ``generic`` and ``access`` formatters. Parent handlers,
  queues, listeners, locks, loggers, and levels are never transplanted or
  mutated.
- One mode-600 generated file remains available for the complete supervised
  lifetime so worker reload and respawn reuse the same formatter payload. It is
  removed idempotently after normal exit, startup failure, signal termination,
  or lifespan failure.
- If no compatible formatter exists, Granian retains native formatting. If a
  selected formatter cannot be reconstructed, startup fails before serving
  with actionable ``--log-config`` guidance instead of silently changing
  presentation.
- Explicit ``--log-config`` bypasses matching and wins completely.

Granian 2.7.9 parity
--------------------

- The plugin continues to own Litestar's ``run`` command surface and translates
  it to Granian. Litestar aliases are retained where their semantics match,
  Granian-native option spellings remain available, and both environment
  namespaces are accepted for equivalent settings with explicit
  ``LITESTAR_*`` precedence.
- CLI help now presents every standard Litestar ``run`` option first, in
  Litestar's order, followed by Granian-specific extensions and then the
  deprecated compatibility shims.
- Removed the CPU-derived worker ceiling; ``--workers`` now validates only a
  minimum of one.
- HTTP mode forwarding is protocol-aware. ``auto`` receives HTTP/1 and HTTP/2
  settings, HTTP/1 receives only HTTP/1 settings, and HTTP/2 receives only
  HTTP/2 settings with WebSockets disabled.
- Updated every HTTP/2 numeric range to Granian 2.7.9.
- ``--ssl-client-verify`` now requires ``--ssl-ca``.
- Existing help descriptions are preserved unless behavior changed. The seven
  revised descriptions cover stable UDS support, the actual HTTP choices,
  supervised PDB propagation, HTTP/2 keep-alive units, Granian's PKCS#8
  key requirement, the parent shutdown deadline, and new logging-config
  precedence.
- Minimum dependencies are now ``litestar>=2.19.0`` and
  ``granian[all]>=2.7.9``. ``rloop``, ``uvloop``, and ``winloop`` extras are
  delegated through Granian; redundant direct ``httptools`` and
  ``websockets`` dependencies are removed.

Static serving
--------------

- Added ``GranianPlugin(static="auto")`` as a structural consumer of one
  plugin exposing ``get_static_server_config()``.
- Discovery validates local absolute routes, existing non-empty directories,
  consistent directory-index values, and explicit fallback reasons.
- Missing, multiple, malformed, or ineligible providers produce one INFO
  fallback and leave serving to Litestar. Explicit CLI mounts always win.

Documentation and release repair
--------------------------------

- Replaced the stale direct/subprocess guide with beginner-first process,
  signal, logging, deployment, native-option, and migration documentation.
- Replaced the custom multiversion Pages builder with the official
  configure/upload/deploy actions and one current site artifact.
- Corrected project URLs to
  ``https://cofin.github.io/litestar-granian/`` and removed ``latest/``
  assumptions.

Known upstream limitations
--------------------------

- Granian's open shutdown defect remains tracked in `#875
  <https://github.com/emmett-framework/granian/issues/875>`_. Granian 2.7.9
  may force-kill workers without running their ASGI shutdown hooks. On
  free-threaded Python it may report all worker threads stopped while still
  missing some shutdown hooks.
- Granian 2.7.9 rejects reload on free-threaded Python.
- Granian metrics remain explicit because of the open shutdown panic in `#881
  <https://github.com/emmett-framework/granian/issues/881>`_.
- The PyO3 pointer panic remains tracked in `#884
  <https://github.com/emmett-framework/granian/issues/884>`_.

0.15.0
======

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
- Python 3.9 support is dropped; Python 3.14 and 3.14t (free-threaded) are
  added to the test matrix.

Migration notes
---------------

Defaults that did **not** change (for clarity):

- ``--in-subprocess`` is still the default. Direct mode is available via
  ``--no-subprocess`` (or ``LITESTAR_GRANIAN_IN_SUBPROCESS=false``) and is
  now usable on all platforms, but the default has not been flipped.

Silent behavioral shifts to watch for when upgrading from ``v0.14.2``:

- **``_granian`` / ``granian.access`` loggers are no longer overwritten.**
  Prior to this release the plugin unconditionally replaced any user
  configuration for these two loggers with
  ``{"handlers": ["console"], "level": "INFO", "propagate": False}``.
  If your app's ``LoggingConfig`` (or structlog
  ``standard_lib_logging_config``) defines them — for example routing
  ``_granian`` through ``["queue_listener"]`` — your config is now
  honored as written. Granian's log lines may flow through a different
  handler than they did on ``v0.14.2``.
- **``--runtime-mode`` default flip** may change worker threading for
  apps that never set the flag. Pin ``--runtime-mode st`` to restore
  the old behavior.
- **Static mounts are now multi-mount.** Apps that relied on the
  implicit ``/static`` route must now pass both ``--static-path-route``
  and ``--static-path-mount`` (repeatable; paired positionally).
- **``--static-path-expires=0``** now means *disable caching* rather
  than failing the previous ``min=60`` validation.

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
