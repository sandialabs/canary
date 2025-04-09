.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-finding:

Finding and listing test files
==============================

``canary find`` finds tests in a search path and prints basic information about each test.


Basic usage
-----------

.. command-output:: canary find .
    :cwd: /examples


Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``basic`` keyword:

.. command-output:: canary find -k basic .
    :cwd: /examples

The ``-k`` option can take a python expression, eg

.. command-output:: canary find -k 'basic and second' .
    :cwd: /examples


Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies:

.. command-output:: canary find -g .
    :cwd: /examples


Show available keywords
-----------------------

.. command-output:: canary find --keywords .
    :cwd: /examples
