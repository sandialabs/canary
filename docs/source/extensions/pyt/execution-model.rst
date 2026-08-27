.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Execution Model
===============

The ``canary_pyt`` execution model follows a multi-phase approach to convert `.pyt` files into executable jobs.

Phases
------

1. **Discovery Phase**
   - Canary scans for `.pyt` files
   - ``PYTLoader`` executes each file with ``__name__ == "__load__"``
   - Directives are monkeypatched to ``DirectiveRecorder``
   - File execution records directives without running test logic

2. **Recording Phase**

   - ``DirectiveRecorder`` captures:

     - Directive name
     - Positional arguments
     - Keyword arguments
     - File path
     - Line number

   - Both ``canary_pyt.directives`` and ``canary.directives`` are monkeypatched

3. **Model Construction Phase**
   - ``PYTAdapter`` applies recorded directives to ``PYTModel``
   - ``PYTModel`` stores directive effects in reducible fields
   - Parameter sets are combined (Cartesian product)
   - Conditional activation is evaluated

4. **Generation Phase**
   - ``PYTLockEmitter`` converts ``PYTModel`` to ``JobSpecIR`` objects
   - Jobs are named based on parameters and directives
   - Dependencies are resolved
   - Resource requirements are calculated

5. **Core Execution Phase**
   - Canary core schedules and executes jobs
   - Results are persisted
   - Status is reported

Discovery/Loading Details
-------------------------

During discovery:

- ``PYTLoader.parse()`` executes the `.pyt` file
- The file is executed in a controlled environment
- Directives are intercepted and recorded
- Test functions are defined but not executed
- ``__name__`` is set to ``"__load__"`` during discovery

Directive Recording
-------------------

``DirectiveRecorder`` captures:

.. code-block:: python

   {
       'name': 'parameterize',
       'args': (['size', [10, 20, 30]]),
       'kwargs': {},
       'file': '/path/to/test.pyt',
       'line': 15
   }

This allows:

- Source-accurate error reporting
- Line-specific diagnostics
- Reproducible job generation

Model Construction
------------------

``PYTModel`` stores:

- **Keywords**: Test classification
- **Parameters**: Parameter sets and combinations
- **Resources**: CPU, GPU, node requirements
- **Dependencies**: Job dependency graph
- **Assets**: Files to copy/link
- **Artifacts**: Expected output files
- **Baselines**: Reference data
- **Timeouts**: Execution time limits
- **Conditional Activation**: When expressions

Parameter Combination
---------------------

Multiple ``parameterize`` directives combine using Cartesian product:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20])
   canary_pyt.directives.parameterize("mode", ["fast", "slow"])

Generates 4 jobs:

- ``test[size=10,mode=fast]``
- ``test[size=10,mode=slow]``
- ``test[size=20,mode=fast]``
- ``test[size=20,mode=slow]``

Job Naming
----------

Job names follow the pattern:

.. code-block:: text

   <base_name>[param1=value1,param2=value2]

Where:

- ``<base_name>`` is derived from the file name
- Parameters are listed alphabetically
- Resource directives (``cpus``, ``gpus``, ``nodes``) don't add to job name
- Explicit IDs (via ``set_id``) override generated names

Dependency Resolution
---------------------

Dependencies are resolved after job generation:

1. ``depends_on`` directives create dependency edges
2. Canary builds a dependency graph
3. Jobs are scheduled in topological order
4. Composite analysis jobs depend on their children

Conditional Activation
----------------------

Jobs are activated based on:

- Command-line options (``-o``)
- Keywords (``-k``)
- Platform detection
- Parameter values
- Custom ``when`` expressions

See :doc:`conditional-activation` for details.

Resource Allocation
-------------------

Resources are allocated based on:

- Fixed resource directives (``cpus(N)``, ``gpus(N)``, ``nodes(N)``)
- Parameterized resources (``parameterize("cpus", [...])``)
- ``exclusive`` flag
- Available resource pool

See :doc:`resources` for details.

Execution Workflow
------------------

For each job:

1. **Setup**:
   - Create workspace
   - Copy/link assets
   - Set up environment

2. **Execution**:
   - Run test function
   - Capture output
   - Monitor timeout

3. **Analysis**:
   - Check expected results
   - Compare baselines
   - Generate artifacts

4. **Cleanup**:
   - Persist results
   - Clean up workspace (unless configured otherwise)

Error Handling
--------------

Errors are handled at multiple levels:

- **Discovery Errors**: Invalid directives, syntax errors
- **Generation Errors**: Invalid parameters, circular dependencies
- **Execution Errors**: Test failures, timeouts, resource exhaustion
- **Analysis Errors**: Missing artifacts, baseline mismatches

Diagnostics
-----------

Common diagnostic messages:

- ``Directive not recorded``: Directive executed outside discovery phase
- ``Parameter combination exceeds limit``: Too many parameter combinations
- ``Circular dependency detected``: Invalid dependency graph
- ``Resource requirement exceeds pool capacity``: Insufficient resources
- ``Timeout exceeded``: Job ran too long

See :doc:`limitations` for edge cases.

Example: Execution Flow
-----------------------

.. code-block:: console

   $ python3 -m canary describe tests/example.pyt
   --- example.pyt -------------
   File: tests/example.pyt
   Keywords: smoke, unit
   4 test specs:
     example[size=10,mode=fast]
     example[size=10,mode=slow]
     example[size=20,mode=fast]
     example[size=20,mode=slow]

   $ python3 -m canary run tests/example.pyt
   Running example[size=10,mode=fast]... PASSED
   Running example[size=10,mode=slow]... PASSED
   Running example[size=20,mode=fast]... PASSED
   Running example[size=20,mode=slow]... PASSED

   $ python3 -m canary status -rA
   example[size=10,mode=fast]: PASSED
   example[size=10,mode=slow]: PASSED
   example[size=20,mode=fast]: PASSED
   example[size=20,mode=slow]: PASSED

See Also
--------

- :doc:`overview`: Introduction to canary_pyt
- :doc:`directives`: Available directives
- :doc:`parameterization`: Parameter combination details
- :doc:`dependencies`: Dependency resolution
- :doc:`conditional-activation`: When expressions
