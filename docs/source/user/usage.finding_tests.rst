.. _usage-finding:

Find and list test files
========================

``nvtest find`` finds tests in a search path and prints basic information about each test.


Basic usage
-----------

.. command-output:: nvtest find .
    :cwd: /examples


Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``basic`` keyword:

.. command-output:: nvtest find -k basic .
    :cwd: /examples

The ``-k`` option can take a python expression, eg

.. command-output:: nvtest find -k 'basic and second' .
    :cwd: /examples


Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies:

.. command-output:: nvtest find -g .
    :cwd: /examples


Show available keywords
-----------------------

.. command-output:: nvtest find --keywords .
    :cwd: /examples
