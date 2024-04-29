.. _howto-finding:

How to find and list test files
===============================

``nvtest find`` finds tests in a search path and prints basic information about each test:


Basic usage
-----------

.. command-output:: nvtest find examples
    :cwd: /


Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``basic`` keyword:

.. command-output:: nvtest find -k basic examples
    :cwd: /

The ``-k`` option can take a python expression, eg

.. command-output:: nvtest find -k 'basic and second' examples
    :cwd: /


Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies:

.. command-output:: nvtest find -g examples
    :cwd: /


Show available keywords
-----------------------

.. command-output:: nvtest find --keywords examples
    :cwd: /
