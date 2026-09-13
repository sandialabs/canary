.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-job:

The Job object
==============

Understanding the three job-related objects
--------------------------------------------

``canary`` uses three distinct objects that represent a job at different stages of
its lifecycle:

.. list-table::
   :widths: 20 20 20 20
   :header-rows: 1

   * - Object
     - Phase
     - Mutability
     - Persistence
   * - ``JobSpecIR``
     - Discovery / Collection
     - Mutable
     - Temporary
   * - ``JobSpec``
     - Resolution / Planning
     - Immutable
     - Database
   * - ``Job``
     - Execution
     - Mutable
     - Session-only

**JobSpecIR** (Job Specification Intermediate Representation) is the generator-specific
output produced during the discovery phase.  It is a lightweight, possibly
template-variable-containing representation emitted by job generators (``canary_pyt``,
``canary_cmake``, ``canary_vvtest``, …).  JobSpecIR objects are converted to JobSpec
objects during dependency resolution and do not persist beyond that phase.

**JobSpec** is the canonical, fully-resolved job specification stored in
``workspace.sqlite3``.  It has a unique, deterministic SHA256-based identifier and
forms the nodes of the dependency graph.  JobSpec objects are immutable once created
and can be reused across multiple sessions.

**Job** is the executable runtime instance created from a JobSpec within a session.
It manages actual command execution, resource allocation, and result collection.

A job is a concrete instantiation of a :ref:`test file <basics-testfile>` with a unique set of parameters.  In the simplest case, a test file defines a single job whose name is the basename of the test file.  In more complex cases, a test file defines :ref:`parameters<usage-parameterize>` that expand to define multiple jobs whose names are a combination of the test name (default: ``basename testfile``) and parameter ``name=value`` pairs.  For example, the test file ``parameterize1.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 7-9

would expand into two test instances with names

* ``parameterize1[a=1]``
* ``parameterize1[a=4]``

Job execution
-------------

During a test session, ``canary`` creates a :ref:`unique test execution directory <test-exec-dir>` for each job and executes the script with the current python interpreter in its own subprocess.  Test parameters and other test-specific and runtime-specific information are accessed from the ``canary.test.instance`` object which is accessible via ``canary.get_instance()``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 11-13

The job object defines the following attributes and methods:

``file_root: str``:
  The job file's root search path, as passed to ``canary run``.

``file_path: str``:
  Path to the job's file, relative to ``file_root``.

``file: str``:
  Full path to the job's file.

``name: str``:
  The job's name.

``cpu_ids: list[int]``:
  List of CPUs reserved for this job [1]_.

``gpu_ids: list[int]``:
  List of GPUs reserved for this job [1]_.

``family: str``:
  The job family is the basename of ``test_path``

``keywords: list[str]``:
  The test file's :ref:`keywords  <directive-keywords>`.

``parameters: dict[str, Union[str, float, int]]``:
  The expanded :ref:`parameters <directive-parameterize>` for this job.

``timeout: float``:
  The job's :ref:`timeout <directive-timeout>`.

``runtime: float``:
  The approximate :ref:`run time <basics-runtimes>`.

``baseline: list[str]``:
  List of :ref:`baseline <directive-baseline>` assets.

``exec_root: str``:
  The root :ref:`session <basics-workspace>` execution directory.

``exec_dir: str``:
  The job's execution directory.

``id: str``:
  The job's stable, content-independent ID.  See :ref:`basics-spec-id-stability`.

``cmd_line: str``:
  The command line used to launch this test.

``variables: dict[str, str]``:
  Extra environment variables defined for this test.

``dependencies: list[Job]``:
  List of dependencies.

``cpus: int``:
  Number of cpus.

``gpus: int``:
  Number of gpus.

``get_dependency(**params) -> Job``:
  Returns the dependency having parameters equal to ``params``.

Job identity
------------

Each job has multiple identifiers that serve different purposes:

- **ID** — unique SHA256-based identifier (e.g., ``"a1b2c3..."``).  Used for database
  storage, result tracking, and stable cross-machine references.
- **Name** — parameterized job name (e.g., ``"test_case[a=1,b=2]"``).
  Human-readable identifier with parameters.
- **Fullname** — path-based name including the relative path from workspace root
  (e.g., ``"path/to/test_case[a=1,b=2]"``).  Used for display and reporting.
- **Family** — base job name without parameters (e.g., ``"test_case"``).  Shared
  by all parameterized variants of the same job definition.

Assets and artifacts
--------------------

Jobs manage file resources through two categories:

**Assets** are input files required before execution begins:

- Copied or linked from source locations into the job's execution directory
- Specified via the ``canary_pyt.directives.copy`` or ``canary_pyt.directives.link``
  directives, or the ``baseline`` attribute
- Availability is checked before the job starts

**Artifacts** are output files produced by execution and collected afterwards:

- Collected based on glob patterns defined by the job
- Collection can be conditional: ``always``, ``never``, ``on_failure``,
  ``on_success``
- Preserved in the job's execution directory for result analysis and reporting

.. _test-exec-dir:

Test execution directory
------------------------

.. note::

    The test execution directory is an implementation detail and could change.  Do not rely on it for dependent tests.  Instead, use the ``canary.test.instance.dependencies`` object to get the ``exec_dir`` of each dependency.

The current test exeuction directory naming scheme matches ``vvtest``'s: ``<work_tree>/<path>/<name>``, where ``path`` is the test file's path *relative* to the test file's search root.  Eg, if ``/the/search/root`` is passed to ``canary run`` and the test file is found in ``some/sub_directory/file.pyt``, the test execution directory would be ``<work_tree>/some/sub_directory/<name>``.

.. [1] The CPU and GPU ids are IDs used internally in ``canary`` and may, or may not, correspond to the actual hardware IDs.  In the simplest case, a test file defines a single job whose name is the basename of the test file.  In more complex cases, a test file defines :ref:`parameters<usage-parameterize>` that expand to define multiple jobs whose names are a combination of the test name (default: ``basename testfile``) and parameter ``name=value`` pairs.  For example, the test file ``parameterize1.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 7-9

would expand into two test instances with names

* ``parameterize1[a=1]``
* ``parameterize1[a=4]``

Job execution
-------------

During a test session, ``canary`` creates a :ref:`unique test execution directory <test-exec-dir>` for each job and executes the script with the current python interpreter in its own subprocess.  Test parameters and other test-specific and runtime-specific information are accessed from the ``canary.test.instance`` object which is accessible via ``canary.get_instance()``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python
    :lines: 11-13

The job object defines the following attributes and methods:

``file_root: str``:
  The job file's root search path, as passed to ``canary run``.

``file_path: str``:
  Path to the job's file, relative to ``file_root``.

``file: str``:
  Full path to the job's file.

``name: str``:
  The job's name.

``cpu_ids: list[int]``:
  List of CPUs reserved for this job [1]_.

``gpu_ids: list[int]``:
  List of GPUs reserved for this job [1]_.

``family: str``:
  The job family is the basename of ``test_path``

``keywords: list[str]``:
  The test file's :ref:`keywords  <directive-keywords>`.

``parameters: dict[str, Union[str, float, int]]``:
  The expanded :ref:`parameters <directive-parameterize>` for this job.

``timeout: float``:
  The job's :ref:`timeout <directive-timeout>`.

``runtime: float``:
  The approximate :ref:`run time <basics-runtimes>`.

``baseline: list[str]``:
  List of :ref:`baseline <directive-baseline>` assets.

``exec_root: str``:
  The root :ref:`session <basics-workspace>` execution directory.

``exec_dir: str``:
  The job's execution directory.

``id: str``:
  The job's stable, content-independent ID.  See :ref:`basics-spec-id-stability`.

``cmd_line: str``:
  The command line used to launch this test.

``variables: dict[str, str]``:
  Extra environment variables defined for this test.

``dependencies: list[Job]``:
  List of dependencies.

``cpus: int``:
  Number of cpus.

``gpus: int``:
  Number of gpus.

``get_dependency(**params) -> Job``:
  Returns the dependency having parameters equal to ``params``.

.. _test-exec-dir:

Test execution directory
------------------------

.. note::

    The test execution directory is an implementation detail and could change.  Do not rely on it for dependent tests.  Instead, use the ``canary.test.instance.dependencies`` object to get the ``exec_dir`` of each dependency.

The current test exeuction directory naming scheme matches ``vvtest``'s: ``<work_tree>/<path>/<name>``, where ``path`` is the test file's path *relative* to the test file's search root.  Eg, if ``/the/search/root`` is passed to ``canary run`` and the test file is found in ``some/sub_directory/file.pyt``, the test execution directory would be ``<work_tree>/some/sub_directory/<name>``.

.. [1] The CPU and GPU ids are IDs used internally in ``canary`` and may, or may not, correspond to the actual hardware IDs.
