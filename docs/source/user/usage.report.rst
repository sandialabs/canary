.. _usage-report:

Generating reports
==================

Several report formats are available:

* :ref:`Junit<usage-junit>`
* :ref:`Markdown<usage-md>`
* :ref:`HTML<usage-html>`
* :ref:`CDash XML<usage-cdash>`

.. _usage-junit:

Junit
-----
A junit report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.junit ./basic
    :cwd: /examples
    :setup: rm -rf TestResults.junit
    :ellipsis: 0

.. command-output:: canary -C TestResults.junit report junit create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.junit/junit.xml
    :language: xml

.. _usage-md:

Markdown
--------
A markdown report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.Markdown ./basic
    :cwd: /examples
    :setup: rm -rf TestResults.Markdown
    :ellipsis: 0

.. command-output:: canary -C TestResults.Markdown report markdown create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.Markdown/Results.md
    :language: markdown

.. _usage-html:

HTML
----

A HTML report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.HTML ./basic
    :cwd: /examples
    :ellipsis: 0
    :setup: rm -rf TestResults.HTML

.. command-output:: canary -C TestResults.HTML report html create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.HTML/Results.html
    :language: html

.. _usage-cdash:

CDash XML
---------

A CDash report of a test session can be generated after the session has completed:

.. code-block:: console

    $ cd TestResults
    $ canary report cdash create --site=SITE --build=BUILD_NAME

The report can be uploaded to a CDash server via

.. code-block:: console

    $ canary report cdash post --project=PROJECT_NAME --url=URL FILE [FILE ...]
