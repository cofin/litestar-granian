===================
Direct vs subprocess
===================

``litestar-granian`` can run Granian in two modes. Both are available via
``--in-subprocess`` / ``--no-subprocess`` on ``litestar run``.

Direct mode (``--no-subprocess``)
=================================

- Granian is loaded and served from the same Python process that owns
  the Litestar application.
- The user's ``LoggingConfig`` / structlog configuration is preserved
  without extra setup — Granian's loggers are injected alongside the
  user's, and log lines share formatters.
- ``--reload`` is supported: the CLI forces ``multiprocessing`` start
  method to ``spawn`` so each Granian worker respawn is a fresh Python
  interpreter (fork-workers would inherit the parent's stale
  ``sys.modules`` and never observe source changes).

Subprocess mode (``--in-subprocess``, default)
==============================================

- Granian runs in a child process invoked as ``python -m granian ...``.
- The child does not inherit the parent's Python logging configuration.
  Pass ``--use-litestar-logger`` to serialize your ``LoggingConfig`` to a
  temporary dictconfig JSON file and forward it via ``--log-config``, or
  hand Granian an explicit ``--log-config FILE`` path yourself.
- Kept as the default for operational familiarity; switch to direct
  mode when you want the Litestar logging experience without extra
  flags.

Logging on macOS / Windows
==========================

Queue-based log handlers such as
``litestar.logging.standard.QueueListenerHandler`` spawn a listener
thread that drains log records to stdout. On fork-based Linux workers
this is fine because each worker reconfigures its logging fresh. On
macOS and Windows (spawn workers) the listener thread does not survive
process creation cleanly and produces interleaved output or lines that
appear after ``"Granian workers stopped"``.

``litestar-granian`` now neutralizes queue handlers to ``StreamHandler``
on spawn platforms automatically. Linux configurations are passed
through unchanged.

Metrics
=======

Pass ``--metrics`` to enable Granian's Prometheus-compatible metrics
endpoint, or install ``litestar.plugins.prometheus.PrometheusPlugin`` to
have it enabled automatically. Tune with ``--metrics-address``,
``--metrics-port``, and ``--metrics-scrape-interval``.

Uvicorn-compatible aliases
==========================

The following Uvicorn flag names are accepted as aliases for the
Granian-native names:

======================  ==========================
Uvicorn-style alias     Granian-native
======================  ==========================
``--reload-include``    ``--reload-paths``
``--reload-exclude``    ``--reload-ignore-dirs``
``--ssl-certfile``      ``--ssl-certificate``
======================  ==========================
