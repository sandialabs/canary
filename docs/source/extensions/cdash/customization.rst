.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Customization
=============

Customize CDash reporting behavior using command-line options and plugin hooks.

Command-Line Customization
--------------------------

Name Format
~~~~~~~~~~~

Control test name format with ``--name-format``:

.. code-block:: console

   # Short format (default)
   $ python3 -m canary report cdash create --name-format short

   # Long format
   $ python3 -m canary report cdash create --name-format long

Subproject Labels
~~~~~~~~~~~~~~~~~~

Treat specific labels as subprojects:

.. code-block:: console

   # Single subproject label
   $ python3 -m canary report cdash create -L "integration"

   # Multiple subproject labels
   $ python3 -m canary report cdash create --subproject-labels "unit,integration,system"

Chunking
~~~~~~~~

Control XML file chunking:

.. code-block:: console

   # Default chunking (500 tests per file)
   $ python3 -m canary report cdash create -n 500

   # No chunking (single file)
   $ python3 -m canary report cdash create -n -1

   # Custom chunk size
   $ python3 -m canary report cdash create -n 200

Plugin Customization
--------------------

Custom Labels
~~~~~~~~~~~~~

Add custom labels based on job attributes:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_labels(case):
       """Add labels based on job attributes"""
       labels = []

       # Add label for important tests
       if case.spec.attributes.get("priority", "normal") == "high":
           labels.append("high_priority")

       # Add label for GPU tests
       if "gpu" in case.spec.keywords:
           labels.append("gpu")

       # Add label for long-running tests
       if case.spec.attributes.get("expected_duration", 0) > 300:
           labels.append("long_running")

       return labels

Subproject Assignment
~~~~~~~~~~~~~~~~~~~~~

Assign tests to subprojects based on patterns:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_subproject_label(case):
       """Assign subprojects based on test patterns"""

       # Unit tests
       if case.spec.family.startswith("unit_"):
           return "UnitTests"

       # Integration tests
       elif case.spec.family.startswith("integration_"):
           return "IntegrationTests"

       # Performance tests
       elif "perf" in case.spec.keywords:
           return "PerformanceTests"

       # Default: no subproject
       return None

Custom Artifacts
~~~~~~~~~~~~~~~~

Attach additional files to CDash tests:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       """Add custom artifacts for failed tests"""
       artifacts = []

       # Attach debug logs for failed tests
       if case.status.is_failure():
           debug_dir = "/path/to/debug/logs"
           log_file = os.path.join(debug_dir, f"{case.spec.family}.debug.log")
           if os.path.exists(log_file):
               artifacts.append(log_file)

       # Attach performance data for performance tests
       if "perf" in case.spec.keywords:
           perf_file = os.path.join("/path/to/perf", f"{case.spec.family}.perf.json")
           if os.path.exists(perf_file):
               artifacts.append(perf_file)

       return artifacts

Subproject Label Sets
~~~~~~~~~~~~~~~~~~~~~

Define label combinations that create subprojects:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_labels_for_subproject():
       """Define subproject label sets"""
       return [
           # Tests with both "unit" and "fast" labels go to "unit" subproject
           ["unit", "fast"],

           # Tests with both "integration" and "slow" labels go to "integration" subproject
           ["integration", "slow"],

           # Tests with "system" label go to "system" subproject
           ["system"],
       ]

Custom Metadata
~~~~~~~~~~~~~~~

While metadata is primarily collected automatically, you can influence it through Canary configuration:

.. code-block:: python

   # Set custom metadata in Canary configuration
   canary.config.set("system:os:release", "CustomOS 1.0")
   canary.config.set("system:platform", "CustomPlatform")

Complete Customization Example
------------------------------

.. code-block:: python

   # my_cdash_customization.py
   import os
   import canary

   @canary.hookimpl
   def canary_cdash_labels(case):
       """Add custom labels"""
       labels = []

       # Priority labels
       priority = case.spec.attributes.get("priority", "normal")
       labels.append(f"priority:{priority}")

       # Environment labels
       if "gpu" in case.spec.keywords:
           labels.append("env:gpu")
       if "mpi" in case.spec.keywords:
           labels.append("env:mpi")

       return labels

   @canary.hookimpl
   def canary_cdash_subproject_label(case):
       """Assign to subprojects"""
       if case.spec.family.startswith("unit_"):
           return "UnitTests"
       elif case.spec.family.startswith("integration_"):
           return "IntegrationTests"
       elif case.spec.family.startswith("system_"):
           return "SystemTests"
       return "OtherTests"

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       """Add debug artifacts for failures"""
       if case.status.is_failure():
           debug_log = f"/logs/{case.spec.family}.debug"
           if os.path.exists(debug_log):
               return [debug_log]
       return []

Use the customization:

.. code-block:: console

   $ python3 -m canary --plugins my_cdash_customization.py report cdash create --build MyBuild

Best Practices
--------------

1. **Consistency**: Use consistent naming conventions for labels and subprojects
2. **Performance**: Keep hook implementations efficient
3. **Documentation**: Document customization logic
4. **Testing**: Test customizations with different job types
5. **Default Behavior**: Return ``None`` or empty lists when no customization needed

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`reporter-plugin` - Plugin hooks reference
- :doc:`xml-generation` - XML generation details