.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

link
====

.. currentmodule:: canary_pyt.directives

.. autofunction:: link

Purpose
-------

Create symbolic links to files in the job workspace. This directive specifies files that should be linked from the source tree to the execution workspace.

Parameters
----------

:param files: File patterns to link (string or list)
:param when: Optional conditional activation (WhenType)
:param \*\*kwargs: Additional options (e.g., rename)

Effect on Generated Jobs
------------------------

- Adds source assets with action ``link``
- Files are symbolically linked to workspace
- Supports file patterns and globs
- Files are accessible in the working directory
- Changes to linked files affect the source

When
----

- **Affects**: Generation phase (asset recording)
- **Runtime**: Links created during workspace setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.link("data.txt", when="-o with_data")

Examples
--------

**Single File**:

.. code-block:: python

   canary_pyt.directives.link("input.txt")

**Multiple Files**:

.. code-block:: python

   canary_pyt.directives.link(["file1.txt", "file2.txt"])

**File Pattern**:

.. code-block:: python

   canary_pyt.directives.link("*.dat")

**Directory**:

.. code-block:: python

   canary_pyt.directives.link("data/")

**Conditional Link**:

.. code-block:: python

   canary_pyt.directives.link("large_file.dat", when="-o extended")

**With Rename**:

.. code-block:: python

   canary_pyt.directives.link("input.txt", rename="data.txt")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.link("missing.txt")  # Warning/Error

**Empty Pattern**:

.. code-block:: python

   canary_pyt.directives.link("*.nonexistent")  # No files linked

**Broken Symlink**:

.. code-block:: python

   canary_pyt.directives.link("broken_link.txt")  # Warning if target missing

Notes
-----

- Files are linked relative to the test file location
- Supports glob patterns for multiple files
- Links are created before test execution
- Use ``copy`` for copies instead of symlinks
- Linked files can be modified (affects source)
- Broken symlinks may cause test failures

Comparison with copy
--------------------

**link**:

.. code-block:: python

   canary_pyt.directives.link("file.txt")  # Creates symlink

**copy**:

.. code-block:: python

   canary_pyt.directives.copy("file.txt")  # Creates copy

When to Use
-----------

**Use link when**:

- Files are large and copying is expensive
- Multiple tests need the same large files
- You want changes to propagate to source
- Disk space is limited

**Use copy when**:

- Files should be isolated from source
- Tests modify files
- You need a snapshot of the file
- Source files may change during execution

Runtime Access
--------------

.. code-block:: python

   def main():
       # Linked files are in working directory
       with open("input.txt", "r") as f:
           data = f.read()

Best Practices
--------------

1. **Large Files**:

   .. code-block:: python

      canary_pyt.directives.link("large_dataset.dat")

2. **Read-Only Data**:

   .. code-block:: python

      canary_pyt.directives.link("reference_data/")

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.link("optional_data.dat", when="-o with_data")

4. **Document Purpose**:

   .. code-block:: python

      # Large reference dataset (symlinked to save space)
      canary_pyt.directives.link("dataset.csv")

See Also
--------

- :doc:`copy`: Copy directive
- :doc:`sources`: Sources directive
- :doc:`artifact`: Artifact directive
- :doc:`../assets`: Assets overview
