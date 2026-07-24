==========
Deployment
==========

Start with a measured worker count and an explicit public binding:

.. code-block:: shell

    litestar --app docs.examples.app:app run --host 0.0.0.0 --port 8000 --workers 4 --granian-access-log

Keep the Litestar process at the top of the service tree. Service managers and
containers must send ``SIGINT`` or ``SIGTERM`` to that parent, not directly to
a Granian worker.

Process-manager checklist
=========================

- Use an init process when Litestar is container PID 1 so exited descendants
  are reaped.
- Send one termination signal to the Litestar parent and allow
  ``--workers-kill-timeout`` plus five seconds before an external hard kill.
- Probe the configured HTTP port for readiness.
- During shutdown, verify the port closes and no Granian descendant remains.
- Treat a non-zero child exit as a service failure; the parent preserves the
  Granian status.

Environment files and working directories
=========================================

``--env-files`` and ``--working-dir`` configure Granian workers only. Values
needed by Litestar server-lifespan integrations must already exist in the
parent environment.

For a complete option inventory, use :doc:`../reference/cli`. For the process
boundary, read :doc:`../concepts/how-it-works`.
