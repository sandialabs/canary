.. _howto-run-basic:

Run tests
=========

Use :ref:`nvtest run<nvtest-run>` to run tests.

Basic usage
-----------

.. command-output:: nvtest run -d TestResults.Basic ./basic
    :cwd: /examples
    :extraargs: -rv -w

.. note::

    The ``-d`` flag specifies the name of the results directory.  The default value is ``TestResults``.

Filter tests to run by keyword
------------------------------

.. code-block:: console

   nvtest run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression such as ``-k 'fast and regression'``.  For example

.. command-output:: nvtest run -d TestResults.Basic -k first ./basic
    :cwd: /examples
    :extraargs: -rv -w

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   nvtest run -l session:workers=N PATH [PATHS...]

where ``N`` is a number of workers.  For example,

.. command-output:: nvtest run -d TestResults.Basic -l session:workers=1 ./basic
    :cwd: /examples
    :extraargs: -rv -w

Set a timeout on the test session
---------------------------------

.. code-block:: console

   nvtest run -l session:timeout=T PATH [PATHS...]

where ``T`` is a number or a human-readable number representation like ``1 sec``, ``1s``, etc.  For example,

.. command-output:: nvtest run -d TestResults.Basic -l 'session:timeout=1 min' ./basic
    :cwd: /examples
    :extraargs: -rv -w
