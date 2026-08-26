Customization
=============

Users can customize how Canary results are mapped to CDash by implementing specific plugin hooks in their own Canary extensions.

Plugin Hooks
------------

The canary_cdash extension defines several hooks that allow developers to inject custom logic into the XML generation process.

**Note**: These hooks are called during the execution of canary report cdash create.

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Hook Name
     - Description
     - Return Value
   * - canary_cdash_name
     - Customizes the name of the test as it appears in CDash.
     - A string representing the test name.
   * - canary_cdash_named_measurements
     - Allows mapping specific Canary measurements to named CDash measurements.
     - A dictionary mapping measurement names to values.
   * - canary_cdash_artifacts
     - Specifies additional files to be attached as artifacts to the CDash test.
     - A list of file paths.
   * - canary_cdash_labels
     - Adds custom labels to the test.
     - A sorted list of strings.
   * - canary_cdash_subproject_label
     - Determines the subproject label for a specific test.
     - A string representing the subproject.
   * - canary_cdash_labels_for_subproject
     - Provides a list of labels that should be treated as subprojects for the entire session.
     - A list of strings.

Example Plugin
-------------

The following example shows how to add a label based on whether a job used a GPU:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_cdash_labels(case):
       labels = set(case.spec.keywords)
       if case.gpus:
           labels.add("gpu")
       return sorted(labels)

Default Behavior
----------------

If no plugin implements a hook, the extension falls back to its default behavior (e.g., using job identities as names and session keywords as labels).
