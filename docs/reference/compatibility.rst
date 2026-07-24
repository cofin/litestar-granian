=============
Compatibility
=============

Package requirements
====================

``litestar-granian`` requires Python 3.10 or later, Litestar 2.19 or later, and
Granian 2.7.9 or later. Its public runtime API is:

- :class:`litestar_granian.GranianPlugin`;
- :data:`litestar_granian.__project__`;
- :data:`litestar_granian.__version__`.

CLI aliases
===========

The plugin owns Litestar's ``run`` compatibility surface. It preserves
Litestar aliases when they describe the same setting and forwards
Granian-native option names to the child.

.. list-table::
    :header-rows: 1

    * - Litestar-compatible spelling
      - Granian setting
    * - ``--web-concurrency`` / ``--wc``
      - ``--workers``
    * - ``--unix-domain-socket``
      - ``--uds``
    * - ``--ssl-certfile``
      - ``--ssl-certificate``
    * - ``--reload-dir``
      - ``--reload-paths``

Environment precedence
======================

Shared settings accept both namespaces. An explicit command-line value wins;
otherwise ``LITESTAR_*`` wins over the equivalent ``GRANIAN_*`` value. For
example, ``LITESTAR_PORT`` wins over ``GRANIAN_PORT``.

The generated :doc:`cli` page shows the accepted environment variables next
to each option.

Optional event loops
====================

The base package installs no optional loop. The ``rloop``, ``uvloop``, and
``winloop`` extras install one matching Granian integration. Install only the
loop being validated and pass its explicit ``--loop`` value. ``--loop auto``
remains the default.
