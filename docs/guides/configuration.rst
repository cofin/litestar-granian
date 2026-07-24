=============
Configuration
=============

``GranianPlugin()`` registers a Granian-backed ``litestar run`` command. Server
settings belong on that command; the plugin constructor only controls static
auto-discovery and generated log presentation.

Bindings and reload
===================

The default binding is ``127.0.0.1:8000``. Change it with ``--host`` and
``--port``, or use ``--uds`` for a Unix domain socket. On POSIX,
``--fd`` accepts an inherited listening socket.

.. code-block:: shell

    litestar --app docs.examples.app:app run --host 0.0.0.0 --port 8080

Use ``--reload`` during development. ``--reload-paths``,
``--reload-include``, or ``--reload-exclude`` also enable reload. Reload and
``--workers-max-rss`` are rejected before application resolution on a
free-threaded Python build because Granian cannot run those combinations.

Workers, runtime, and event loops
=================================

- ``--workers`` selects application workers.
- ``--runtime-threads`` selects Rust network-I/O threads per worker.
- ``--runtime-mode`` selects Granian's Rust runtime mode.
- ``--loop`` selects the event-loop implementation.
- ``--backlog`` limits queued connections globally.
- ``--backpressure`` limits concurrent requests per worker.

The default installation includes no optional event loop. Install one
integration and select it explicitly when validating it:

.. code-block:: shell

    python -m pip install "litestar-granian[uvloop]"
    litestar --app docs.examples.app:app run --loop uvloop

The equivalent extras are ``rloop`` and ``winloop`` on platforms where those
packages are available. The public default remains ``--loop auto``.

HTTP, WebSockets, and TLS
=========================

``--http auto`` forwards HTTP/1 and HTTP/2 settings. ``--http 1`` forwards only
HTTP/1 settings. ``--http 2`` forwards only HTTP/2 settings and disables
WebSockets because WebSockets require HTTP/1.1 in this server configuration.

For Granian-managed TLS, pass both a certificate and its PKCS#8 private key:

.. code-block:: shell

    litestar --app docs.examples.app:app run --ssl-certificate server.crt --ssl-keyfile server.key

``--ssl-client-verify`` also requires ``--ssl-ca``. A reverse proxy can own TLS
instead when that is the deployment boundary.

Worker environment and lifecycle
================================

``--working-dir`` and repeatable ``--env-files`` are forwarded to Granian.
They change the worker environment; they do not change the Litestar parent's
current directory or load dotenv values into parent-owned server lifespans.

Granian also exposes worker respawn, lifetime, RSS, PID-file, and process-name
settings. ``--workers-kill-timeout`` controls Granian's graceful worker
deadline; the Litestar supervisor adds five seconds before it forcefully reaps
the child group.

Use :doc:`../reference/cli` for every switch, default, range, and environment
variable.
