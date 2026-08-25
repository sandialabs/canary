.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Directives
=================

This page documents the VVTest directive DSL supported by ``canary_vvtest``. Each directive is parsed from ``#VVT:`` comments and converted to Canary job specifications.

Directive Reference
-------------------

### keywords

Add keywords to the test for classification and filtering.

**Syntax**:

.. code-block:: text

   #VVT: keywords : keyword1 keyword2 keyword3
   #VVT: keywords (testname="test_name") : keyword1 keyword2

**Behavior**:

- Whitespace-separated arguments become keywords
- Keywords are used for test selection with ``-k`` option
- Conditional activation with ``testname`` option

**Example**:

.. code-block:: text

   #VVT: keywords : smoke unit performance

### copy, link, sources

Manage file assets for the test.

**Syntax**:

.. code-block:: text

   #VVT: copy : file1.txt file2.txt
   #VVT: link : directory/
   #VVT: sources : input.csv

**Behavior**:

- ``copy``: Copy files to workspace
- ``link``: Create symbolic links
- ``sources``: Record source files (no copy/link)
- Supports glob patterns
- ``rename`` option for file renaming

**Example**:

.. code-block:: text

   #VVT: copy : inputs/*.dat
   #VVT: link : reference_data/

### preload

Preload data or modules before test execution.

**Syntax**:

.. code-block:: text

   #VVT: preload : data.csv
   #VVT: preload (testname="test_name") : module.py

**Behavior**:

- Loads data into memory or sets up environment
- Effect depends on execution backend
- May have limited effect in some environments

### parameterize

Define parameter sets for test variants.

**Syntax**:

.. code-block:: text

   #VVT: parameterize : name = value1 value2 value3
   #VVT: parameterize (type=int) : size = 10 20 30

**Behavior**:

- Creates multiple test instances with different parameters
- Supports type options: ``autotype``, ``int``, ``float``, ``str``
- Special names ``np``, ``ndevice``, ``nnode`` forced to integer
- Original string preserved for execution path naming

**Example**:

.. code-block:: text

   #VVT: parameterize : size = 10 20 30
   #VVT: parameterize (type=int) : np = 1 2 4

### analyze

Create composite analysis jobs.

**Syntax**:

.. code-block:: text

   #VVT: analyze : --flag argument
   #VVT: analyze : script.py

**Behavior**:

- Argument starting with ``-`` becomes a flag
- Other argument becomes a script
- Creates parent job that depends on child jobs
- Used for aggregation and analysis workflows

**Example**:

.. code-block:: text

   #VVT: analyze : --analyze results.txt

### timeout

Set execution timeout.

**Syntax**:

.. code-block:: text

   #VVT: timeout : 30
   #VVT: timeout : 5m
   #VVT: timeout : 2h30m

**Behavior**:

- Accepts seconds, minutes, hours, days
- Supports ``MM:SS`` and ``HH:MM:SS`` formats
- Invalid formats raise parse errors

**Example**:

.. code-block:: text

   #VVT: timeout : 5m

### filter_warnings

Control warning filtering.

**Syntax**:

.. code-block:: text

   #VVT: filter_warnings : true
   #VVT: filter_warnings : false

**Behavior**:

- Boolean argument controls warning filtering
- JSON booleans and integers supported
- Evaluated through safe expression evaluation

### skipif

Conditionally skip tests.

**Syntax**:

.. code-block:: text

   #VVT: skipif (reason="Not applicable") : condition

**Behavior**:

- Skips test when condition is true
- ``reason`` option explains why test is skipped
- False expressions do not skip

**Example**:

.. code-block:: text

   #VVT: skipif (reason="Windows not supported") : platform == "windows"

### baseline

Declare baseline files for comparison.

**Syntax**:

.. code-block:: text

   #VVT: baseline : output.txt
   #VVT: baseline : --flag results.txt

**Behavior**:

- Flag-based baseline (starts with ``--``)
- Copy-based baseline (``src,dst`` pairs)
- Used for regression testing

**Example**:

.. code-block:: text

   #VVT: baseline : expected_output.txt

### enable

Enable or disable tests.

**Syntax**:

.. code-block:: text

   #VVT: enable : true
   #VVT: enable : false

**Behavior**:

- ``true`` or nonempty string enables test
- ``false`` disables test
- Conditional activation supported

### name / testname

Set test name.

**Syntax**:

.. code-block:: text

   #VVT: name : test_name
   #VVT: testname : test_name

**Behavior**:

- Both forms are equivalent
- Sets explicit test name
- Used for multi-test files

### depends on / depends_on

Define dependencies between tests.

**Syntax**:

.. code-block:: text

   #VVT: depends on : setup_test
   #VVT: depends on (expect=1, result=pass) : setup_test

**Behavior**:

- ``depends on`` normalized to ``depends_on``
- ``expect`` option controls dependency count
- ``result`` option maps to Canary results:
  - ``pass`` → ``success``
  - ``diff`` → ``diffed``
  - ``fail`` → ``failed``
  - ``skip`` → ``skipped``
- Dependency patterns support wildcards

**Example**:

.. code-block:: text

   #VVT: depends on : setup_test

### include / insert_directive_file

Include directives from another file.

**Syntax**:

.. code-block:: text

   #VVT: include : common.vvt

**Behavior**:

- Handled during parsing
- Include path resolved relative to current file
- Included directives processed as if present in current file
- Include conditions combine with included directive conditions

Examples
--------

### Simple Test

.. code-block:: text
   :caption: test_exec_dir.vvt

   #VVT: testname = "simple_test"
   #VVT: command = "python simple.py"
   #VVT: timeout = 30

### Complex Workflow

.. code-block:: text
   :caption: empire.vvt (example)

   #VVT: testname = "complex_workflow"
   #VVT: command = "python complex.py"
   #VVT: nodes = 2
   #VVT: cpus = 8
   #VVT: timeout = 120

See Also
--------

- :doc:`vvtest-parameterization`: Parameterization details
- :doc:`vvtest-dependencies`: Dependency patterns
- :doc:`vvtest-analysis`: Analysis workflows
