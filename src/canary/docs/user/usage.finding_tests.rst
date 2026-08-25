.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-finding:

Finding and listing test files
==============================

``canary find`` finds tests in a search path and prints basic information about each test.


Basic usage
-----------

.. doc-run::
   :before_script: [link-examples]
   :script: ["canary find -r ."]
   :cwd: /examples


Filter by keyword
-----------------

The ``-k`` option will filter tests by keyword.  Eg., find tests with the ``basic`` keyword:

.. doc-run::
   :before_script: [link-examples]
   :script: ["canary find -k basic -r ."]
   :cwd: /examples

The ``-k`` option can take a python expression, eg

.. doc-run::
   :before_script: [link-examples]
   :script: ["canary find -k 'basic and second' -r ."]
   :cwd: /examples


Print a test DAG
----------------

The ``-g`` option will print a graph of test dependencies:

.. doc-run::
   :before_script: [link-examples]
   :script: ["canary find -g -r ."]
   :cwd: /examples


Show available keywords
-----------------------

.. doc-run::
   :before_script: [link-examples]
   :script: ["canary find --keywords -r ."]
   :cwd: /examples
