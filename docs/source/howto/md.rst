.. _howto-md:

How to generate markdown output
===============================

A markdown report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -d TestResults.Markdown ./basic
    :cwd: /examples
    :ellipsis: 0

.. command-output:: nvtest -C TestResults.Markdown report markdown create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.Markdown/Results.md
    :language: markdown
