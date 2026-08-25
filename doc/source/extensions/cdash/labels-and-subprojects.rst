.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Labels and Subprojects
=======================

Organize CDash tests using labels and subprojects.

Labels
------

Labels categorize tests in CDash and enable filtering.

Sources of Labels
~~~~~~~~~~~~~~~~~

1. **Job Keywords**: Automatically converted to labels
2. **Custom Labels**: Added via ``canary_cdash_labels`` hook
3. **Subproject Labels**: Special labels that create subprojects

Label Format
~~~~~~~~~~~~

Labels are simple text strings:

- Alphanumeric characters and underscores
- No spaces (use underscores instead)
- Case-sensitive

Examples: ``unit``, ``fast``, ``gpu_test``, ``nightly``

Label Usage
~~~~~~~~~~~

Labels appear in CDash XML:

.. code-block:: xml

   <Test>
     <Name>my_test</Name>
     <Labels>
       <Label>unit</Label>
       <Label>fast</Label>
       <Label>important</Label>
     </Labels>
   </Test>

Subprojects
-----------

Subprojects organize tests into logical groups in CDash.

Subproject Sources
~~~~~~~~~~~~~~~~~~

1. **Explicit Assignment**: Via ``canary_cdash_subproject_label`` hook
2. **Label-Based**: Via ``-L`` or ``--subproject-labels`` options
3. **Label Sets**: Via ``canary_cdash_labels_for_subproject`` hook

Subproject Assignment
~~~~~~~~~~~~~~~~~~~~

Tests are assigned to subprojects through:

1. **Hook Return Value**: ``canary_cdash_subproject_label`` returns subproject name
2. **Label Matching**: Tests with matching labels are assigned to subprojects
3. **Label Sets**: Tests matching label combinations are assigned to subprojects

Subproject in XML
~~~~~~~~~~~~~~~~~

.. code-block:: xml

   <Test>
     <Name>my_test</Name>
     <SubProject>UnitTests</SubProject>
     <Labels>
       <Label>unit</Label>
     </Labels>
   </Test>

Subproject Examples
-------------------

Command-Line Subprojects
~~~~~~~~~~~~~~~~~~~~~~~~

Treat specific labels as subprojects:

.. code-block:: console

   # Single subproject label
   $ python3 -m canary report cdash create -L "unit"

   # Multiple subproject labels
   $ python3 -m canary report cdash create --subproject-labels "unit,integration,system"

Hook-Based Subprojects
~~~~~~~~~~~~~~~~~~~~~~

Assign subprojects via plugin hook:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_subproject_label(case):
       if case.spec.family.startswith("unit_"):
           return "UnitTests"
       elif case.spec.family.startswith("integration_"):
           return "IntegrationTests"
       return "OtherTests"

Label Set Subprojects
~~~~~~~~~~~~~~~~~~~~~

Define subprojects based on label combinations:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_labels_for_subproject():
       return [
           ["unit", "fast"],      # Tests with both labels → "unit" subproject
           ["integration", "slow"], # Tests with both labels → "integration" subproject
       ]

Subproject Best Practices
-------------------------

1. **Logical Grouping**: Group related tests together
2. **Consistent Naming**: Use consistent subproject names
3. **Avoid Overlap**: Minimize test overlap between subprojects
4. **Document Conventions**: Document subproject naming conventions
5. **Performance**: Large subprojects may impact CDash performance

Labels vs Subprojects
---------------------

+----------------------------+--------------------------------------------------+
| Feature                    | Labels                                           |
+============================+==================================================+
| **Purpose**               | Categorization and filtering                      |
+----------------------------+--------------------------------------------------+
| **Scope**                 | Individual tests                                 |
+----------------------------+--------------------------------------------------+
| **Hierarchy**             | Flat                                             |
+----------------------------+--------------------------------------------------+
| **CDash Display**         | Filterable tags                                  |
+----------------------------+--------------------------------------------------+

+----------------------------+--------------------------------------------------+
| Feature                    | Subprojects                                      |
+============================+==================================================+
| **Purpose**               | Logical grouping of tests                        |
+----------------------------+--------------------------------------------------+
| **Scope**                 | Groups of tests                                 |
+----------------------------+--------------------------------------------------+
| **Hierarchy**             | Can be nested                                    |
+----------------------------+--------------------------------------------------+
| **CDash Display**         | Separate test groups                             |
+----------------------------+--------------------------------------------------+

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`reporter-plugin` - Plugin hooks
- :doc:`customization` - Customization examples