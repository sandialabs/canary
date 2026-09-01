.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Analysis
===============

The ``analyze`` directive creates composite analysis jobs that aggregate results from multiple child jobs. This enables workflow patterns where a parent job analyzes or reports on child job results.

analyze Directive
-----------------

### Syntax

.. code-block:: text

   #VVT: analyze : --flag argument
   #VVT: analyze : script.py

### Flag-Based Analysis

Arguments starting with ``-`` become flags:

.. code-block:: text

   #VVT: analyze : --analyze results.txt

### Script-Based Analysis

Other arguments become scripts:

.. code-block:: text

   #VVT: analyze : analyze_results.py

### Options

Additional options are passed through to analysis setup:

.. code-block:: text

   #VVT: analyze (option=value) : script.py

Relationship to Child Jobs
--------------------------

### Parameterized Children

Analysis jobs depend on parameterized child jobs:

.. code-block:: text

   #VVT: parameterize : size = 10 20 30
   #VVT: analyze : report.py

Generates:
- ``test[size=10]``
- ``test[size=20]``
- ``test[size=30]``
- ``test[analyze]`` (depends on all children)

### Composite Behavior

The composite parent job:

- Runs after all children complete
- Has access to child results
- Can aggregate or analyze data
- Uses ``TestMultiInstance`` for child access

### Shared Model/Emitter

Analysis behavior derives from:

- ``VVTestModel``: Shared model with child jobs
- ``VVTestLockEmitter``: Shared emitter for job specifications
- ``PYTModel``: Inherited from ``canary_pyt``

Interaction with -a / --analyze
--------------------------------

### --analyze Option

Appends ``--execute-analysis-sections`` to script arguments:

.. code-block:: console

   python3 -m canary run -a tests/

### analyze Directive

Works with ``-a`` option:

.. code-block:: text

   #VVT: analyze : script.py

When run with ``-a``, the script receives the analysis flag.

Examples
--------

### Flag-Based Analysis

.. code-block:: text

   #VVT: analyze : --analyze output.txt

### Script-Based Analysis

.. code-block:: text

   #VVT: analyze : analyze_results.py

### With Options

.. code-block:: text

   #VVT: analyze (option=value) : script.py

### Composite Workflow

.. code-block:: text

   #VVT: parameterize : config = a b c
   #VVT: analyze : aggregate.py

This creates:
- 3 child jobs (config=a, config=b, config=c)
- 1 analysis job that depends on all children

Best Practices
--------------

1. **Analysis Scripts**:

   .. code-block:: text

      #VVT: analyze : analyze_results.py

2. **Flag-Based**:

   .. code-block:: text

      #VVT: analyze : --analyze output.txt

3. **With Parameters**:

   .. code-block:: text

      #VVT: parameterize : size = 10 20 30
      #VVT: analyze : report.py

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`vvtest-parameterization`: Parameterization details
