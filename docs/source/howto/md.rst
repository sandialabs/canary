.. _howto-md:

How to generate markdown output
===============================

A markdown report of a test session can be generated after the session has completed:

.. command-output:: nvtest run -vw -d TestMarkdownResults .
    :cwd: /examples/basic
    :ellipsis: 0

.. command-output:: nvtest -C TestMarkdownResults report markdown create
    :cwd: /examples/basic

.. literalinclude:: /examples/basic/TestMarkdownResults/Results.md
    :language: markdown
