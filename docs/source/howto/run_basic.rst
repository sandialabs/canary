.. _howto-run-basic:

How to run tests
================

Basic usage
-----------

.. command-output:: nvtest run ./basic
    :cwd: /examples

Filter tests to run by keyword
------------------------------

.. code-block:: console

   nvtest run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression such as ``-k 'fast and regression'``.  For example

.. command-output:: nvtest run -k first ./basic
    :cwd: /examples

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   nvtest run -l session:workers:N PATH [PATHS...]

where ``N`` is a number of workers.  For example,

.. command-output:: nvtest run -l session:workers:1 ./basic
    :cwd: /examples

Set a timeout on the test session
---------------------------------

.. code-block:: console

   nvtest run -l session:timeout:T PATH [PATHS...]

where ``T`` is a number or a human-readable number representation like ``1 sec``, ``1s``, etc.  For example,

.. command-output:: nvtest run -l 'session:timeout:1 min' ./basic
    :cwd: /examples
