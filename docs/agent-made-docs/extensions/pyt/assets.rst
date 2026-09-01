.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Assets
======

Assets are files needed by jobs during execution. Assets are copied or linked to the job workspace before execution.

Asset Directives
----------------

### copy

Copy files to the workspace:

.. code-block:: python

   canary_pyt.directives.copy("input.txt")
   canary_pyt.directives.copy(["file1.txt", "file2.txt"])
   canary_pyt.directives.copy("*.dat")

**Behavior**:

- Files are copied from source tree to workspace
- Supports single files, lists, and glob patterns
- Files are read-only in workspace
- Copies are independent of source

### link

Create symbolic links to files:

.. code-block:: python

   canary_pyt.directives.link("input.txt")
   canary_pyt.directives.link(["file1.txt", "file2.txt"])
   canary_pyt.directives.link("*.dat")

**Behavior**:

- Files are symbolically linked from source tree
- Supports single files, lists, and glob patterns
- Changes to linked files affect source
- Uses less disk space than copying

### sources

Record source file associations:

.. code-block:: python

   canary_pyt.directives.sources("input.txt")
   canary_pyt.directives.sources(["file1.txt", "file2.txt"])

**Behavior**:

- Records source files in job metadata
- Files are not automatically copied or linked
- Used for tracking dependencies and provenance
- Accessible via ``instance.sources`` at runtime

Source and Destination
----------------------

**Relative Paths**:
   Paths are relative to the test file location.

.. code-block:: python

   canary_pyt.directives.copy("data/input.txt")

**Absolute Paths**:
   Not recommended; use relative paths.

**Destination**:
   Files are placed in the working directory.

.. code-block:: python

   canary_pyt.directives.copy("input.txt")  # Copied to ./input.txt

Glob Behavior
-------------

Glob patterns match multiple files:

.. code-block:: python

   canary_pyt.directives.copy("*.dat")
   canary_pyt.directives.copy("data/*.txt")
   canary_pyt.directives.copy("**/*.csv")

**Behavior**:

- Patterns match files in source tree
- Matched files are copied/linked individually
- Empty patterns result in no files copied

Example: Running Tests with Assets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./copy_and_link, python3 -m canary status -rA]
   :cwd: /examples

This example demonstrates running tests that use copy and link directives for asset management.

Execution Directory Setup
-------------------------

Assets are set up before job execution:

1. Workspace is created
2. Files are copied/linked to workspace
3. Environment is set up
4. Job executes
5. Workspace is cleaned up (unless configured otherwise)

--copy-all-resources Behavior
-----------------------------

If ``--copy-all-resources`` is used:

- All source files are copied to workspace
- Explicit ``copy`` and ``link`` directives are still processed
- Useful for ensuring complete workspace isolation

Assets vs Artifacts
-------------------

**Assets**:

- Files needed **before** execution
- Input files, test data, configuration
- Set up in workspace before job runs
- Use ``copy``, ``link``, ``sources``

**Artifacts**:

- Files saved **after** execution
- Output files, logs, results
- Collected after job completes
- Use ``artifact`` directive

Examples
--------

**Copy Test Data**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.copy("test_data.csv")
   canary_pyt.directives.copy("config.json")

**Link Large Dataset**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.link("large_dataset.dat")

**Record Source Files**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.sources("input.csv")
   canary_pyt.directives.sources("reference_data/")

**Glob Patterns**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.copy("inputs/*.txt")
   canary_pyt.directives.copy("data/*.csv")

Best Practices
--------------

1. **Copy for Isolation**:

   .. code-block:: python

      canary_pyt.directives.copy("test_data.csv")

2. **Link for Large Files**:

   .. code-block:: python

      canary_pyt.directives.link("large_dataset.dat")

3. **Record for Provenance**:

   .. code-block:: python

      canary_pyt.directives.sources("input.csv")

4. **Conditional Assets**:

   .. code-block:: python

      canary_pyt.directives.copy("large_data.dat", when="-o large")

See Also
--------

- :doc:`directive-reference/copy`: Copy directive
- :doc:`directive-reference/link`: Link directive
- :doc:`directive-reference/sources`: Sources directive
- :doc:`artifacts`: Artifacts overview
