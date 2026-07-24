:layout: landing

================
Litestar Granian
================

Run Litestar applications with Granian while preserving Litestar startup,
shutdown, logging, and server integrations.

.. container:: buttons

    :doc:`Run the quickstart <getting-started/quickstart>`
    :doc:`Browse configuration <guides/configuration>`

Choose your next task
---------------------

.. grid:: 1 1 3 3
    :gutter: 2

    .. grid-item-card:: Start the server
        :link: getting-started/quickstart
        :link-type: doc

        Install the plugin, save one small app, and verify the JSON response.

    .. grid-item-card:: Understand the runtime
        :link: concepts/how-it-works
        :link-type: doc

        See which process owns startup, workers, signals, and shutdown.

    .. grid-item-card:: Prepare a deployment
        :link: guides/deployment
        :link-type: doc

        Choose a service command and verify graceful process cleanup.

.. toctree::
    :titlesonly:
    :caption: Start here
    :hidden:

    getting-started/quickstart

.. toctree::
    :titlesonly:
    :caption: Learn
    :hidden:

    concepts/how-it-works

.. toctree::
    :titlesonly:
    :caption: Guides
    :hidden:

    guides/configuration
    guides/logging-and-metrics
    guides/static-files
    guides/deployment

.. toctree::
    :titlesonly:
    :caption: Reference
    :hidden:

    reference/index
    migration/v0.16
    changelog
    contribution-guide
