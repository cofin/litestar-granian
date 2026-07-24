============
Static files
============

Explicit native mounts
======================

Pair every URL route with one directory mount:

.. code-block:: shell

    litestar --app docs.examples.app:app run --static-path-route /assets --static-path-mount docs/examples/static

The example directory contains:

.. literalinclude:: ../examples/static/index.html
    :language: text

Repeat both options in the same order for multiple mounts. Their counts must
match. ``--static-path-dir-to-file`` chooses a directory index such as
``index.html``; ``--static-path-expires 0`` disables cache expiry.

Provider auto-discovery
=======================

``GranianPlugin(static="auto")`` looks for exactly one registered plugin with a
callable ``get_static_server_config()`` method. A native config must contain:

- local absolute URL routes;
- existing, non-empty directories;
- one consistent directory-index value.

No provider, multiple providers, ASGI placement, unsafe paths, or malformed
data produces one INFO message and leaves Litestar's static router in place.
Auto-discovery is an optimization; Litestar remains the fallback.
