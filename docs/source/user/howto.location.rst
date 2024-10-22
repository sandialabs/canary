.. _howto-location:

Find locations of test assets
=============================

It is often useful to know the location a test's execution directory.  The :ref:`nvtest location<nvtest-location>` command can display the locations of test assets:


.. command-output:: nvtest location -h

For example to move to the test execution directory, simply:

.. code-block:: console

    cd $(nvtest location /ID)

where ``ID`` is the test ID that is printed by :ref:`nvtest status<howto-status>`.

.. note::

    ``nvtest log`` should be run inside of a test session by either navigating to the session's directory or by ``nvtest -C PATH``.
