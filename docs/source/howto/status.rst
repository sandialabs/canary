.. _howto-status:

How to get the status of a test session
=======================================

After running a test session, the ``status`` subcommanda can show the status of the test session

.. command-output:: nvtest run .
    :cwd: /examples
    :returncode: 22
    :ellipsis: 0

.. command-output:: nvtest -C TestResults status .
    :cwd: /examples
