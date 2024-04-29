.. _howto-html:

How to generate html output
===========================

A HTML report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -vw -d TestHTMLResults .
    :cwd: /examples/basic
    :ellipsis: 0

.. command-output:: nvtest -C TestHTMLResults report html create
    :cwd: /examples/basic

.. literalinclude:: /examples/basic/TestHTMLResults/Results.html
    :language: html
