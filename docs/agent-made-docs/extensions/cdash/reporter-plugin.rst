.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CDash Reporter Plugin
======================

The ``canary_cdash`` extension uses Canary's plugin architecture to allow customization of CDash reporting behavior through hooks.

Plugin Architecture
-------------------

The CDash reporter calls several hooks during XML generation to allow plugins to customize behavior:

+------------------------------------+--------------------------------------------------+
| Hook                                | Purpose                                         |
+====================================+==================================================+
| ``canary_cdash_labels``            | Add custom labels to CDash tests                 |
+------------------------------------+--------------------------------------------------+
| ``canary_cdash_subproject_label``  | Assign subproject labels to tests                |
+------------------------------------+--------------------------------------------------+
| ``canary_cdash_labels_for_subproject`` | Define subproject label sets                 |
+------------------------------------+--------------------------------------------------+
| ``canary_cdash_artifacts``         | Add custom artifacts to CDash tests              |
+------------------------------------+--------------------------------------------------+

Hook Reference
--------------

canary_cdash_labels
~~~~~~~~~~~~~~~~~~~

Add custom labels to CDash tests.

**When Called**: During XML generation for each job

**Arguments**: ``case`` - The Canary job being processed

**Expected Return**: List of label strings or ``None``

**Effect on XML**: Labels are added to the CDash test element

**Default Behavior**: No custom labels added

Example:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_labels(case):
       """Add custom labels based on job attributes"""
       labels = []
       if case.spec.attributes.get("important"):
           labels.append("important")
       if "gpu" in case.spec.keywords:
           labels.append("gpu")
       return labels

canary_cdash_subproject_label
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assign a subproject label to a test.

**When Called**: During XML generation for each job

**Arguments**: ``case`` - The Canary job being processed

**Expected Return**: Subproject label string or ``None``

**Effect on XML**: Test is associated with the specified subproject

**Default Behavior**: No subproject assignment

Example:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_subproject_label(case):
       """Assign subproject based on job family"""
       if case.spec.family.startswith("unit_"):
           return "UnitTests"
       elif case.spec.family.startswith("integration_"):
           return "IntegrationTests"
       return None

canary_cdash_labels_for_subproject
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Define sets of labels that should be treated as subprojects.

**When Called**: During reporter initialization

**Arguments**: None

**Expected Return**: List of label sets, where each set is a list of labels

**Effect on XML**: Labels in the sets are treated as subproject labels

**Default Behavior**: No predefined subproject label sets

Example:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_labels_for_subproject():
       """Define subproject label sets"""
       return [
           ["unit", "fast"],      # Tests with both labels go to "unit" subproject
           ["integration", "slow"], # Tests with both labels go to "integration" subproject
       ]

canary_cdash_artifacts
~~~~~~~~~~~~~~~~~~~~~~

Add custom artifacts to CDash tests.

**When Called**: During XML generation for each job

**Arguments**: ``case`` - The Canary job being processed

**Expected Return**: List of artifact file paths or ``None``

**Effect on XML**: Artifacts are attached to the CDash test

**Default Behavior**: No custom artifacts added

Example:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       """Add custom artifacts based on job type"""
       artifacts = []
       if case.status.is_failure():
           # Attach debug logs for failed tests
           debug_log = f"/path/to/debug/{case.spec.family}.log"
           if os.path.exists(debug_log):
               artifacts.append(debug_log)
       return artifacts

Plugin Registration
-------------------

To use these hooks, register them in a Canary plugin:

.. code-block:: python

   # my_cdash_plugin.py
   import canary

   @canary.hookimpl
   def canary_cdash_labels(case):
       # Custom label logic
       return ["custom_label"]

   @canary.hookimpl
   def canary_cdash_subproject_label(case):
       # Custom subproject logic
       return "MySubproject"

Enable the plugin using Canary's plugin system:

.. code-block:: console

   $ python3 -m canary --plugins my_cdash_plugin.py report cdash create --build MyBuild

Hook Interaction
----------------

The hooks are called in this order during XML generation:

1. ``canary_cdash_labels_for_subproject`` - Define subproject label sets
2. ``canary_cdash_subproject_label`` - Assign subproject to each test
3. ``canary_cdash_labels`` - Add custom labels to each test
4. ``canary_cdash_artifacts`` - Add custom artifacts to each test

Best Practices
--------------

1. **Performance**: Keep hook implementations efficient
2. **Error Handling**: Handle exceptions gracefully
3. **Default Behavior**: Return ``None`` or empty lists when no customization needed
4. **Documentation**: Document hook behavior in plugin code
5. **Testing**: Test hooks with different job types and statuses

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`xml-generation` - XML generation process
- :doc:`customization` - Customization examples
