.. _howto-run-basic:

How to run tests
================

Basic usage
-----------

.. command-output:: nvtest run -vw ./basic
    :cwd: /examples

Filter tests to run by keyword
------------------------------

.. code-block:: console

   nvtest run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression.  For example, ``-k 'key1 and not key2'``.

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   nvtest run -l session:workers:N PATH [PATHS...]

Set a timeout on the test session
---------------------------------

.. code-block:: console

   nvtest run -l session:timeout:T PATH [PATHS...]

where ``T`` is a number or a human-readable number representation like ``1 sec``, ``1s``, etc.
