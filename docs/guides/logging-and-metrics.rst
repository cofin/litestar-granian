===================
Logging and metrics
===================

Granian automatically matches Litestar's active formatter. Configure logging
once in Litestar; the Granian server and access loggers use the same standard,
custom JSON, structlog, or other compatible formatter.

Automatic formatter matching
----------------------------

Litestar and Granian run in separate processes, so they must own separate
logger and handler objects. Before serving, the plugin reads Litestar's active
logging graph and reconstructs only the effective formatter in Granian's
process. It follows:

- direct Litestar handlers;
- queue-listener output handlers;
- propagated and root handlers;
- structurally compatible Litestar logging configuration when the active graph
  has no formatter.

Discovery is read-only. It does not call Litestar's ``configure()``, start or
stop queue listeners, change logger levels, or retain application-owned
formatter objects. The generated configuration is a deep copy of Granian's
native logging configuration with only its ``generic`` and ``access``
formatters replaced. Granian keeps its own handlers, loggers, streams, levels,
queues, locks, and listener lifecycle.

The one mode-600 generated configuration remains available for the full
supervised process lifetime, including worker reload and respawn, and is
removed when the supervisor exits. Its serialized payload contains only the
selected formatter's object graph, which can include formatter-owned state
such as a structlog processor chain. It does not contain Litestar's logging
configuration, handlers, queues, listeners, loggers, locks, or levels.

If Litestar has no compatible formatter, Granian keeps its native formatting.
If an active formatter is selected but cannot be reconstructed, startup stops
with an error that directs you to ``--log-config`` instead of silently changing
output.

Automatic matching reproduces the active **formatter**, not the active
**handler**. A handler that owns its own presentation — for example
``rich.logging.RichHandler`` — renders differently in the Granian child,
because handlers stay process-local by design and only the formatter crosses
the process boundary. Use ``--log-config`` to configure an equivalent handler
directly in Granian's process when matching presentation matters.

Optional formatting packages
----------------------------

The plugin does not import or depend on structlog or a JSON logging package.
Those choices work automatically when your application installs and configures
a compatible formatter upstream.

Explicit configuration
----------------------

``--log-config`` is a complete Granian logging override. It bypasses automatic
formatter matching.

This example uses direct stdout handlers:

.. literalinclude:: ../examples/logging.json
    :language: json

Run it with:

.. code-block:: shell

    litestar --app docs.examples.app:app run --log-config docs/examples/logging.json

Granian logging and access logging remain separate. Use
``--granian-no-log`` to disable server logs and ``--granian-access-log`` to
enable request logs.

The retained ``--use-litestar-logger`` and ``--no-litestar-logger`` switches
are deprecated no-ops. They warn that matching is automatic.

Metrics
-------

Metrics are disabled until ``--metrics`` is set:

.. code-block:: shell

    litestar --app docs.examples.app:app run --metrics

This exposes Granian server and worker metrics. When no Litestar Prometheus
middleware or plugin is detected, the command warns that application-level
request metrics are not included. Configure the endpoint with
``--metrics-address``, ``--metrics-port``, and
``--metrics-scrape-interval``.
