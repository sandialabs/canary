.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-run-basic:

Running tests
=============

Use :ref:`canary run<canary-run>` to run tests.

Basic usage
-----------

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "cwd": "examples"}]

Filter tests to run by keyword
------------------------------

.. code-block:: console

   canary run -k KEYWORD_EXPR PATH [PATHS...]

where ``KEYWORD_EXPR`` is a Python expression such as ``-k 'fast and regression'``.  For example

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run -k first ./basic", "cwd": "examples"}]

Limit the number of concurrent tests
------------------------------------

.. code-block:: console

   canary run --workers=N PATH [PATHS...]

where ``N`` is a number of workers.  For example,

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run --workers=1 ./basic", "cwd": "examples"}]

Set a timeout on the test session
---------------------------------

.. code-block:: console

   canary run --timeout session=T PATH [PATHS...]

where ``T`` is a duration in Go's duration format (``40s,``, ``1h20m``, ``2h``, ``4h30m30s``, etc.)  For example,

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run --timeout session=1m ./basic", "returns": 7, "cwd": "examples"}]

Run specific test files
-----------------------

Run a file directly
~~~~~~~~~~~~~~~~~~~

Test files can be run directly by passing their paths to ``canary run``

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic/first/first.pyt", "cwd": "examples"}]

If a path separator is replaced with a colon ``:``, the path is interpreted as ``root:path``.  ie, path segments after the ``:`` are used as the relative path to the test execution directory:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run .:basic/first/first.pyt", "cwd": "examples"}, {"args": "ls -F TestResults", "cwd": "examples"}]

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
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary tree --exclude-results .", "cwd": "examples"}]

To run only ``centered_space/centered_space.pyt`` and ``parameterize/parameterize2.pyt``, write the following to ``tests.json``

.. literalinclude:: /examples/tests.json
    :language: json

and pass it to ``canary run``:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run -f tests.json", "cwd": "examples"}]

Additional run options
-----------------------

Allow an empty test set
~~~~~~~~~~~~~~~~~~~~~~~

By default ``canary run`` exits with code 7 if no tests match the given criteria.
Pass ``--empty-ok`` to treat an empty match as a normal (zero-exit) result:

.. code-block:: console

   canary run --empty-ok -k "nonexistent_keyword" .

Stop at the first failure
~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``--fail-fast`` to stop the session as soon as any job fails:

.. code-block:: console

   canary run --fail-fast .

This is useful during development for fast feedback when a failure early in the
dependency graph would make subsequent failures meaningless.

Pass arguments to test scripts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Arguments placed after ``--`` on the command line are forwarded to every test
script that is executed:

.. code-block:: console

   canary run . -- --verbose --debug-level=2

Clean work directories before running
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``-w`` to remove and recreate each job's execution directory before running,
ensuring a completely clean environment:

.. code-block:: console

   canary run -w .

Run from view paths
~~~~~~~~~~~~~~~~~~~~

A path inside the ``TestResults/`` view can be passed directly to ``canary run``
to re-execute only the jobs whose results live at that location:

.. code-block:: console

   canary run ./TestResults/path/to/subdirectory/

Run configuration summary
--------------------------

.. list-table:: Common ``canary run`` options
   :widths: 30 70
   :header-rows: 1

   * - Option
     - Purpose
   * - ``--only {all,changed,failed,not_pass,not_run}``
     - Rerun strategy (see :ref:`usage-rerun`)
   * - ``--empty-ok``
     - Allow empty test set (no error on zero matches)
   * - ``--fail-fast``
     - Stop at first job failure
   * - ``--workers N``
     - Limit concurrent workers
   * - ``--timeout session=T``
     - Limit total session duration
   * - ``--timeout default=T``
     - Set default per-job timeout
   * - ``-w``
     - Clean work directories before running
   * - ``--``
     - Pass remaining arguments to test scripts
   * - ``-f FILE``
     - Read test paths from a JSON/YAML file
   * - ``-k EXPR``
     - Filter by keyword expression
