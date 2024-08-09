.. _introduction-testcase:

The test case
=============

A test case is a concrete instantiation of a :ref:`test file <introduction-testfile>` with a unique set of parameters.  In the simplest case, a test file defines a single test case whose name is the basename of the test file.  In more complex cases, a single test file defines parameters that expand to define multiple test cases whose names are a combination of the basename of the test file and parameter ``name=value`` pairs.  For example, the test file ``parameterize.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 2-4

would expand into two test instances with names

* ``parameterize1[a=1]``
* ``parameterize1[a=4]``

Test case execution
-------------------

During a test session, ``nvtest`` creates a :ref:`unique test execution directory <test-exec-dir>` for each test case and executes the script with the current python interpreter in its own subprocess.  Test parameters and other test-specific and runtime-specific information are accessed from the ``nvtest.test.instance`` object which is accessible via ``nvtest.get_instance()``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 2-8

The test instance object defines the following attributes and methods:

``file_root``:
  The test case file's root search path, as passed to ``nvtest run``.

``file_path``:
  Path to the test case's file, relative to ``file_root``.

``file``:
  Full path to the test case's file.

``name``:
  The test case's name.

``cpu_ids``:
  List of CPUs reserved for this job [1]_.

``gpu_ids``:
  List of GPUs reserved for this job [1]_.

``analyze``:
  Whether this job is an :ref:`analyze <directive-analyze>` job, or not.

``family``:
  The test case family is the basename of ``test_path``

``keywords``:
  The test file's :ref:`keywords  <directive-keywords>`.

``parameters``:
  The expanded :ref:`parameters <directive-parameterize>` for this test case.

``timeout``:
  The test cases :ref:`timeout <directive-timeout>`.

``runtime``:
  The approximate :ref:`run time <introduction-runtimes>`.

``baseline``:
  List of :ref:`baseline <directive-baseline>` assets.

``exec_root``:
  The root :ref:`session <introduction-session>` execution directory.

``exec_dir``:
  The test case's execution directory.

``id``:
  The test case's ID.

``cmd_line``:
  The command line used to launch this test.

``variables``:
  Extra environment variables defined for this test.

``dependencies``:
  List of dependencies.

``cpus``:
  Number of cpus.

``gpus``:
  Number of gpus.

``def get_dependency(**params)``:
  Returns the dependency having parameters equal to ``params``.

.. _test-exec-dir:

Test execution directory
------------------------

.. note::

    The test execution directory is an implementation detail and could change.  Do not rely on it for dependent tests.  Instead, use the ``nvtest.test.instance.dependencies`` object to get the ``exec_dir`` of each dependency.

The current test exeuction directory naming scheme matches ``vvtest``'s: ``<session_root>/<path>/<name>``, where ``path`` is the test file's path *relative* to the test file's search root.  Eg, if ``/the/search/root`` is passed to ``nvtest run`` and the test file is found in ``some/sub_directory/file.pyt``, the test execution directory would be ``<session_root>/some/sub_directory/<name>``.

.. [1] The CPU and GPU ids are IDs used internally in ``nvtest`` and may, or may not, correspond to the actual hardware IDs.
