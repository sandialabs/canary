.. _howto-html:

How to generate html output
===========================

A HTML report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -d TestResults.HTML ./basic
    :cwd: /examples
    :ellipsis: 0

.. command-output:: nvtest -C TestResults.HTML report html create
    :cwd: /examples

.. literalinclude:: /examples/TestResults.HTML/Results.html
    :language: html
