.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

copy
====

.. currentmodule:: canary_pyt.directives

.. autofunction:: copy

Purpose
-------

Copy files to the job workspace. This directive specifies files that should be copied from the source tree to the execution workspace.

Parameters
----------

:param files: File patterns to copy (string or list)
:param when: Optional conditional activation (WhenType)
:param \*\*kwargs: Additional options (e.g., rename)

Effect on Generated Jobs
------------------------

- Adds source assets with action ``copy``
- Files are copied to workspace before execution
- Supports file patterns and globs
- Files are accessible in the working directory

When
----

- **Affects**: Generation phase (asset recording)
- **Runtime**: Files copied during workspace setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.copy("data.txt", when="-o with_data")

Examples
--------

**Single File**:

.. code-block:: python

   canary_pyt.directives.copy("input.txt")

**Multiple Files**:

.. code-block:: python

   canary_pyt.directives.copy(["file1.txt", "file2.txt"])

**File Pattern**:

.. code-block:: python

   canary_pyt.directives.copy("*.dat")

**Directory**:

.. code-block:: python

   canary_pyt.directives.copy("data/")

**Conditional Copy**:

.. code-block:: python

   canary_pyt.directives.copy("large_file.dat", when="-o extended")

**With Rename**:

.. code-block:: python

   canary_pyt.directives.copy("input.txt", rename="data.txt")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.copy("missing.txt")  # Warning/Error

**Empty Pattern**:

.. code-block:: python

   canary_pyt.directives.copy("*.nonexistent")  # No files copied

**Duplicate Files**:

.. code-block:: python

   canary_pyt.directives.copy("file.txt")
   canary_pyt.directives.copy("file.txt")  # Redundant

Notes
-----

- Files are copied relative to the test file location
- Supports glob patterns for multiple files
- Files are copied before test execution
- Use ``link`` for symbolic links instead of copies
- Copied files are read-only in the workspace
- Large files may impact performance

Comparison with link
--------------------

**copy**:

.. code-block:: python

   canary_pyt.directives.copy("file.txt")  # Creates copy

**link**:

.. code-block:: python

   canary_pyt.directives.link("file.txt")  # Creates symlink

Runtime Access
--------------

.. code-block:: python

   def main():
       # Copied files are in working directory
       with open("input.txt", "r") as f:
           data = f.read()

Best Practices
--------------

1. **Specific Files**:

   .. code-block:: python

      canary_pyt.directives.copy("test_data.csv")

2. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.copy("large_dataset.dat", when="-o large")

3. **Patterns**:

   .. code-block:: python

      canary_pyt.directives.copy("inputs/*.txt")

4. **Document Purpose**:

   .. code-block:: python

      # Test data for performance benchmark
      canary_pyt.directives.copy("benchmark_data.csv")

See Also
--------

- :doc:`link`: Link directive
- :doc:`sources`: Sources directive
- :doc:`artifact`: Artifact directive
- :doc:`../assets`: Assets overview
