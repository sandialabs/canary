.. _howto-report:

Generate reports
================

Several report formats are available:

* :ref:`Markdown<md>`
* :ref:`HTML<html>`
* :ref:`CDash XML<cdash>`

.. _md:

Markdown
--------
A markdown report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -d TestResults.Markdown ./basic
    :cwd: /examples
    :extraargs: -rv -w
    :ellipsis: 0

.. command-output:: nvtest -C TestResults.Markdown report markdown create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.Markdown/Results.md
    :language: markdown
.. _howto-html:

.. _html:

HTML
----

A HTML report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -d TestResults.HTML ./basic
    :cwd: /examples
    :ellipsis: 0
    :extraargs: -rv -w

.. command-output:: nvtest -C TestResults.HTML report html create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.HTML/Results.html
    :language: html
.. _howto-cdash:


.. _cdash:

CDash XML
---------

After completing a test session

.. code-block:: console

    $ cd TestResults
    $ nvtest report cdash create -p <PROJECT_NAME> -b <BUILD_NAME>

The report can be uploaded to a CDash server via

.. code-block:: console

    $ cd TestResults
    $ nvtest report cdash post URL
