.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-run-basic:

Running tests
=============

Use :ref:`canary run<canary-run>` to run tests.

Basic usage
-----------

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run ./basic]
   :cwd: /examples

Filter tests to run by keyword
------------------------------

.. code-block:: console

   canary run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression such as ``-k 'fast and regression'``.  For example

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run -k first ./basic]
   :cwd: /examples

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   canary run --workers=N PATH [PATHS...]

where ``N`` is a number of workers.  For example,

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run --workers=1 ./basic]
   :cwd: /examples

Set a timeout on the test session
---------------------------------

.. code-block:: console

   canary run --timeout session=T PATH [PATHS...]

where ``T`` is a duration in Go's duration format (``40s,``, ``1h20m``, ``2h``, ``4h30m30s``, etc.)  For example,

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run --timeout session=1m ./basic]
   :cwd: /examples
   :returncode: [7]

Run specific test files
-----------------------

Run a file directly
~~~~~~~~~~~~~~~~~~~

Test files can be run directly by passing their paths to ``canary run``

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run ./basic/first/first.pyt, ls -F TestResults]
   :cwd: /examples

If a path separator is replaced with a colon ``:``, the path is interpreted as ``root:path``.  ie, path segments after the ``:`` are used as the relative path to the test execution directory:

.. doc-run::
   :before_script: [copy-examples]
   :script: ['canary run .:/basic/first/first.pyt', 'ls -F TestResults']
   :cwd: /examples
   :returncode: [3, 0]

Running tests from a file
~~~~~~~~~~~~~~~~~~~~~~~~~

Select tests can be executed by specifying their paths in a ``json`` or ``yaml`` configuration file with the following layout:

.. code-block:: yaml

    testpaths:
    - root: <root>
      paths:
      - <path_1>
      - <path_2>
      ...
      - <path_n>

where ``<root>`` is a parent directory of the tests and ``<path_i>`` are the file paths relative to ``<root>``.  If ``<root>`` is a relative path, it is considered relative to the path of the configuration file.  Consider, for example, the examples directory tree:

.. doc-run::
   :before_script: [link-examples]
   :script: [canary tree --exclude-results .]
   :cwd: /examples

To run only ``centered_space/centered_space.pyt`` and ``parameterize/parameterize2.pyt``, write the following to ``tests.json``

.. literalinclude:: /examples/tests.json
    :language: json

and pass it to ``canary run``:

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run -f tests.json]
   :cwd: /examples
