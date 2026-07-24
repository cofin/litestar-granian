==========
Quickstart
==========

This page takes you from an empty file to a running Litestar application.

Install
========

Install Litestar Granian:

.. code-block:: shell

    python -m pip install litestar-granian

Create the application
======================

Save this example as ``example.py``:

.. literalinclude:: ../examples/app.py
    :language: python

Run it
======

Start the regular Litestar CLI:

.. code-block:: shell

    litestar --app example:app run

The plugin registers the ``run`` command and starts Granian behind a Litestar
parent process.

Verify it
=========

Open ``http://127.0.0.1:8000/`` in a browser, or run:

.. code-block:: shell

    curl http://127.0.0.1:8000/

The response is:

.. code-block:: json

    {"hello":"world"}

Press ``Ctrl+C`` in the server terminal. The port should close and the command
should return to your shell.

Where to go next
================

- Read :doc:`../concepts/how-it-works` before choosing worker or shutdown
  settings.
- Use :doc:`../guides/configuration` for bindings, reload, protocols, TLS,
  workers, and optional loops.
- Use :doc:`../guides/logging-and-metrics` to choose Granian log presentation.
- Keep :doc:`../reference/cli` open for the complete option list.
