.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-testcase:

The test case
=============

A test case is a concrete instantiation of a :ref:`test file <basics-testfile>` with a unique set of parameters.  In the simplest case, a test file defines a single test case whose name is the basename of the test file.  In more complex cases, a test file defines :ref:`parameters<usage-parameterize>` that expand to define multiple test cases whose names are a combination of the test name (default: ``basename testfile``) and parameter ``name=value`` pairs.  For example, the test file ``parameterize1.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 7-9

would expand into two test instances with names

* ``parameterize1[a=1]``
* ``parameterize1[a=4]``

Test case execution
-------------------

During a test session, ``canary`` creates a :ref:`unique test execution directory <test-exec-dir>` for each test case and executes the script with the current python interpreter in its own subprocess.  Test parameters and other test-specific and runtime-specific information are accessed from the ``canary.test.instance`` object which is accessible via ``canary.get_instance()``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 11-13

The test instance object defines the following attributes and methods:

``file_root: str``:
  The test case file's root search path, as passed to ``canary run``.

``file_path: str``:
  Path to the test case's file, relative to ``file_root``.

``file: str``:
  Full path to the test case's file.

``name: str``:
  The test case's name.

``cpu_ids: list[int]``:
  List of CPUs reserved for this job [1]_.

``gpu_ids: list[int]``:
  List of GPUs reserved for this job [1]_.

``family: str``:
  The test case family is the basename of ``test_path``

``keywords: list[str]``:
  The test file's :ref:`keywords  <directive-keywords>`.

``parameters: dict[str, Union[str, float, int]]``:
  The expanded :ref:`parameters <directive-parameterize>` for this test case.

``timeout: float``:
  The test cases :ref:`timeout <directive-timeout>`.

``runtime: float``:
  The approximate :ref:`run time <basics-runtimes>`.

``baseline: list[str]``:
  List of :ref:`baseline <directive-baseline>` assets.

``exec_root: str``:
  The root :ref:`session <basics-session>` execution directory.

``exec_dir: str``:
  The test case's execution directory.

``id: str``:
  The test case's ID.

``cmd_line: str``:
  The command line used to launch this test.

``variables: dict[str, str]``:
  Extra environment variables defined for this test.

``dependencies: list[TestInstance]``:
  List of dependencies.

``cpus: int``:
  Number of cpus.

``gpus: int``:
  Number of gpus.

``get_dependency(**params) -> TestInstance``:
  Returns the dependency having parameters equal to ``params``.

.. _test-exec-dir:

Test execution directory
------------------------

.. note::

    The test execution directory is an implementation detail and could change.  Do not rely on it for dependent tests.  Instead, use the ``canary.test.instance.dependencies`` object to get the ``exec_dir`` of each dependency.

The current test exeuction directory naming scheme matches ``vvtest``'s: ``<work_tree>/<path>/<name>``, where ``path`` is the test file's path *relative* to the test file's search root.  Eg, if ``/the/search/root`` is passed to ``canary run`` and the test file is found in ``some/sub_directory/file.pyt``, the test execution directory would be ``<work_tree>/some/sub_directory/<name>``.

.. [1] The CPU and GPU ids are IDs used internally in ``canary`` and may, or may not, correspond to the actual hardware IDs.
