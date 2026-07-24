===================
Logging and metrics
===================

Litestar and Granian run in separate processes, so they own separate logger
and handler objects. The plugin can match presentation without copying live
handlers, queues, listeners, locks, or configured loggers across that boundary.

Log styles
==========

``GranianPlugin(log_style=...)`` accepts:

.. list-table::
    :header-rows: 1

    * - Style
      - Granian presentation
    * - ``auto``
      - Match an active Litestar ``LoggingConfig`` or ``StructLoggingConfig``;
        otherwise keep Granian-native output.
    * - ``native``
      - Use Granian's built-in presentation.
    * - ``standard``
      - Use a child-owned stdout handler with the active standard formatter.
    * - ``json``
      - Use the active structlog formatter, or the built-in JSON fields.

The generated configuration reconstructs a fresh formatter in the Granian
child. If reconstruction fails, it warns and uses the selected built-in
preset.

Precedence is:

1. An explicit ``--log-config`` controls the entire Granian dictConfig.
2. ``--granian-log-style`` overrides the plugin constructor.
3. ``GranianPlugin(log_style=...)`` supplies the default.

Explicit JSON configuration
===========================

This complete example uses direct stdout handlers:

.. literalinclude:: ../examples/logging.json
    :language: json

Run it with:

.. code-block:: shell

    litestar --app docs.examples.app:app run --log-config docs/examples/logging.json

Granian logging and access logging remain separate. Use
``--granian-no-log`` to disable server logs and ``--granian-access-log`` to
enable request logs.

Metrics
========

Metrics are disabled until ``--metrics`` is set:

.. code-block:: shell

    litestar --app docs.examples.app:app run --metrics

This exposes Granian server and worker metrics. When no Litestar Prometheus
middleware or plugin is detected, the command warns that application-level
request metrics are not included. Configure the endpoint with
``--metrics-address``, ``--metrics-port``, and
``--metrics-scrape-interval``.
