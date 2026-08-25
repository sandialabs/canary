.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Environment and Runtime
===============================

Environment directives control test execution environment and runtime behavior.

preload Directive
-----------------

Preload data or modules before test execution:

.. code-block:: text

   #VVT: preload : data.csv
   #VVT: preload (testname="test_name") : module.py

### Behavior

- Loads data into memory or sets up environment
- Effect depends on execution backend
- May have limited effect in some environments

timeout Directive
-----------------

Set execution timeout:

.. code-block:: text

   #VVT: timeout : 30
   #VVT: timeout : 5m
   #VVT: timeout : 2h30m

### Accepted Formats

- Seconds: ``30``
- Minutes: ``5m``
- Hours: ``2h``
- Combined: ``2h30m``
- ``MM:SS`` format
- ``HH:MM:SS`` format

### to_seconds Function

Converts time formats to seconds:

.. code-block:: python

   from canary_vvtest.vvt import to_seconds
   to_seconds("5m")  # Returns 300

enable Directive
----------------

Enable or disable tests:

.. code-block:: text

   #VVT: enable : true
   #VVT: enable : false

### Behavior

- ``true`` or nonempty string enables test
- ``false`` disables test
- Conditional activation supported

skipif Directive
----------------

Conditionally skip tests:

.. code-block:: text

   #VVT: skipif (reason="Not applicable") : condition

### Behavior

- Skips test when condition is true
- ``reason`` option explains why test is skipped
- False expressions do not skip

### Boolean Evaluation

Uses safe expression evaluation with namespace:

- ``os``
- ``sys``
- ``importable``

filter_warnings Directive
--------------------------

Control warning filtering:

.. code-block:: text

   #VVT: filter_warnings : true
   #VVT: filter_warnings : false

### Behavior

- Boolean argument controls warning filtering
- JSON booleans and integers supported
- Evaluated through safe expression evaluation

Runtime Compatibility Utility
------------------------------

``canary_vvtest`` writes a ``vvtest_util.py`` compatibility module into the execution directory for ``.vvt`` jobs during ``canary_runteststart``.

### Important Attributes

From ``get_vvtest_attrs()`` in ``__init__.py``:

- ``JOBID``
- ``CASEID``
- ``NAME``
- ``TESTID``
- ``PLATFORM``
- ``COMPILER``
- ``TESTROOT``
- ``VVTESTSRC``
- ``PROJECT``
- ``OPTIONS``
- ``OPTIONS_OFF``
- ``SRCDIR``
- ``TIMEOUT``
- ``KEYWORDS``
- ``diff_exit_status``
- ``skip_exit_status``
- ``opt_analyze``
- ``is_analysis_only``
- ``is_analyze``
- ``is_baseline``
- ``PARAM_DICT``
- ``DEPDIRS``
- ``DEPDIRMAP``
- ``exec_dir``
- ``exec_root``
- ``exec_path``
- ``file_root``
- ``file_dir``
- ``file_path``
- ``RESOURCE_np``
- ``RESOURCE_IDS_np``
- ``RESOURCE_ndevice``
- ``RESOURCE_IDS_ndevice``

### Parameter Access

Job parameters are written as module variables:

.. code-block:: python

   import vvtest_util as vvt
   size = vvt.size  # Access parameter

### Analysis Jobs

Analysis jobs get ``PARAM_<names>`` tables from parameter sets.

### DEPDIRMAP

Currently empty in source (may be populated in future).

Canary Integration
------------------

### opt_analyze and is_analysis_only

Both based on ``--execute-analysis-sections`` in ``sys.argv``:

.. code-block:: console

   python3 -m canary run -a tests/

### Rerun Option (-R)

The ``-R`` option forces rerun of all tests, overriding normal completion checking:

.. code-block:: console

   python3 -m canary run -R tests/

This option is equivalent to ``--only=all`` and ensures tests are executed even if they previously completed successfully.

### Resource Mappings

- ``np`` → ``cpus``
- ``ndevice`` → ``gpus``
- ``nnode`` → ``nodes``

Examples
--------

### Preload Data

.. code-block:: text

   #VVT: preload : dataset.csv

### Timeout

.. code-block:: text

   #VVT: timeout : 5m

### Enable Test

.. code-block:: text

   #VVT: enable : true

### Skip Conditionally

.. code-block:: text

   #VVT: skipif (reason="Windows not supported") : platform == "windows"

### Filter Warnings

.. code-block:: text

   #VVT: filter_warnings : true

Best Practices
--------------

1. **Use Timeouts**:

   .. code-block:: text

      #VVT: timeout : 5m

2. **Conditional Skipping**:

   .. code-block:: text

      #VVT: skipif (reason="Not needed") : -o quick

3. **Environment Setup**:

   .. code-block:: text

      #VVT: preload : setup.sh

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`file-format`: File format details
