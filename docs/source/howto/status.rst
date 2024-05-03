.. _howto-status:

Get the status of a test session
================================

After running a test session, the ``status`` subcommand can show the status of the test session

.. command-output:: nvtest run .
    :cwd: /examples
    :returncode: 22
    :ellipsis: 0
    :extraargs: -rv -w

.. command-output:: nvtest -C TestResults status .
    :cwd: /examples

.. note::

    ``nvtest status`` should be run inside of a test session by either navigating to the session's directory or by ``nvtest -C PATH``.
