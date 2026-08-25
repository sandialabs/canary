.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

sources
=======

.. currentmodule:: canary_pyt.directives

.. autofunction:: sources

Purpose
-------

Declare source files associated with the job. Source files are recorded for reference but not automatically copied or linked to the workspace.

Parameters
----------

:param \*args: Source file patterns (string or list)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Records source file associations
- Source files are listed in job metadata
- Files are not automatically copied or linked
- Useful for tracking dependencies and provenance

When
----

- **Affects**: Generation phase (source recording)
- **Runtime**: Source files accessible via instance

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.sources("data.txt", when="-o with_data")

Examples
--------

**Single Source**:

.. code-block:: python

   canary_pyt.directives.sources("input.txt")

**Multiple Sources**:

.. code-block:: python

   canary_pyt.directives.sources("file1.txt", "file2.txt")

**File Pattern**:

.. code-block:: python

   canary_pyt.directives.sources("*.dat")

**Conditional Sources**:

.. code-block:: python

   canary_pyt.directives.sources("optional.txt", when="-o extended")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.sources("missing.txt")  # Warning

**Empty Pattern**:

.. code-block:: python

   canary_pyt.directives.sources("*.nonexistent")  # No sources recorded

**Duplicate Sources**:

.. code-block:: python

   canary_pyt.directives.sources("file.txt")
   canary_pyt.directives.sources("file.txt")  # Redundant

Notes
-----

- Source files are recorded but not automatically copied
- Use ``copy`` or ``link`` to make files available in workspace
- Source files appear in job metadata and reports
- Useful for tracking data provenance
- Does not affect job execution

Comparison with copy/link
-------------------------

**sources**:

.. code-block:: python

   canary_pyt.directives.sources("file.txt")  # Records only

**copy**:

.. code-block:: python

   canary_pyt.directives.copy("file.txt")  # Copies to workspace

**link**:

.. code-block:: python

   canary_pyt.directives.link("file.txt")  # Links to workspace

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       for source in instance.sources:
           print(f"Source: {source}")

Best Practices
--------------

1. **Reference Files**:

   .. code-block:: python

      canary_pyt.directives.sources("reference_data.txt")

2. **Documentation**:

   .. code-block:: python

      canary_pyt.directives.sources("README.txt")

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.sources("optional.txt", when="-o with_sources")

4. **Provenance Tracking**:

   .. code-block:: python

      # Track input data sources
      canary_pyt.directives.sources("input.csv", "config.json")

See Also
--------

- :doc:`copy`: Copy directive
- :doc:`link`: Link directive
- :doc:`artifact`: Artifact directive
