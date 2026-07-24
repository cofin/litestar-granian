============
How it works
============

Litestar Granian keeps Litestar in charge of the outer server lifecycle while
Granian owns HTTP handling and ASGI workers.

Process ownership
=================

Version 0.16 uses one execution model:

.. code-block:: text

    Litestar parent
    ├── server-lifespan integrations
    └── supervised Granian child process group
        └── one or more Granian ASGI workers

The Litestar parent resolves the application, enters server lifespans once,
sets ``LITESTAR_APP`` and ``LITESTAR_PORT`` for integrations, and starts a
fresh Granian process group. Granian's workers still run the application's
normal ASGI lifespan.

This boundary matters for integrations such as frontend development servers
and background-worker sidecars. They surround the web server once instead of
starting once per Granian worker.

Signals and shutdown
====================

Send termination signals to the top-level Litestar PID:

1. The first ``SIGINT`` or ``SIGTERM`` is forwarded to Granian.
2. The parent waits for Granian's worker timeout plus five seconds.
3. A second termination signal or an expired deadline kills the Granian
   process group.
4. Litestar unwinds its server lifespans before the parent exits.

On POSIX, ``SIGHUP`` is forwarded without starting shutdown. On Windows, the
parent requests graceful shutdown with ``CTRL_BREAK_EVENT`` before it uses a
process-tree kill.

Exit status
===========

A normal Granian exit is returned unchanged. A POSIX signal exit is normalized
to the shell convention ``128 + signal``. For example, an unhandled
``SIGTERM`` exit is ``143``.

Workers and runtime threads
===========================

``--workers`` controls Granian application workers. ``--runtime-threads``
controls Rust network-I/O threads inside each worker; it does not create Python
application workers. Measure the application before changing either value.
