.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CTest Properties
================

Supported CTest Properties
--------------------------

The following CTest properties are supported by ``canary_cmake``:

+------------------------------------+--------------------------------------------------+
| Property                            | Description                                     |
+====================================+==================================================+
| ``ATTACHED_FILES``                 | Files to attach on test completion               |
+------------------------------------+--------------------------------------------------+
| ``ATTACHED_FILES_ON_FAIL``         | Files to attach on test failure                  |
+------------------------------------+--------------------------------------------------+
| ``DEPENDS``                        | Test dependencies (with result consideration)    |
+------------------------------------+--------------------------------------------------+
| ``DISABLED``                       | Disable test execution                           |
+------------------------------------+--------------------------------------------------+
| ``ENVIRONMENT``                    | Environment variables for test                   |
+------------------------------------+--------------------------------------------------+
| ``ENVIRONMENT_MODIFICATION``       | Environment variable modifications               |
+------------------------------------+--------------------------------------------------+
| ``FAIL_REGULAR_EXPRESSION``        | Regular expressions indicating failure           |
+------------------------------------+--------------------------------------------------+
| ``FIXTURES_CLEANUP``               | Fixtures to cleanup after test                   |
+------------------------------------+--------------------------------------------------+
| ``FIXTURES_REQUIRED``              | Required fixtures                                |
+------------------------------------+--------------------------------------------------+
| ``FIXTURES_SETUP``                 | Fixtures to setup before test                    |
+------------------------------------+--------------------------------------------------+
| ``LABELS``                         | Test labels (converted to Canary keywords)       |
+------------------------------------+--------------------------------------------------+
| ``PASS_REGULAR_EXPRESSION``        | Regular expressions indicating success           |
+------------------------------------+--------------------------------------------------+
| ``PROCESSORS``                     | Number of processors                             |
+------------------------------------+--------------------------------------------------+
| ``RESOURCE_GROUPS``                | Resource group requirements                      |
+------------------------------------+--------------------------------------------------+
| ``RUN_SERIAL``                     | Run test serially (exclusive execution)          |
+------------------------------------+--------------------------------------------------+
| ``SKIP_REGULAR_EXPRESSION``        | Regular expressions indicating skip              |
+------------------------------------+--------------------------------------------------+
| ``SKIP_RETURN_CODE``               | Return code indicating skip                      |
+------------------------------------+--------------------------------------------------+
| ``TIMEOUT``                        | Test timeout                                     |
+------------------------------------+--------------------------------------------------+
| ``WILL_FAIL``                      | Test expected to fail                            |
+------------------------------------+--------------------------------------------------+
| ``WORKING_DIRECTORY``              | Test working directory                           |
+------------------------------------+--------------------------------------------------+

Unsupported CTest Properties
----------------------------

The following CTest properties are currently not supported:

+------------------------------------+--------------------------------------------------+
| Property                            | Reason                                          |
+====================================+==================================================+
| ``COST``                           | Test cost estimation not implemented             |
+------------------------------------+--------------------------------------------------+
| ``GENERATED_RESOURCE_SPEC_FILE``   | Generated resource specification not supported   |
+------------------------------------+--------------------------------------------------+
| ``MEASUREMENT``                    | Test measurements not implemented                |
+------------------------------------+--------------------------------------------------+
| ``PROCESSOR_AFFINITY``             | Processor affinity not supported                 |
+------------------------------------+--------------------------------------------------+
| ``REQUIRED_FILES``                 | Required files not implemented                   |
+------------------------------------+--------------------------------------------------+
| ``RESOURCE_LOCK``                  | Resource locking not supported                   |
+------------------------------------+--------------------------------------------------+
| ``TIMEOUT_AFTER_MATCH``            | Timeout after pattern match not implemented      |
+------------------------------------+--------------------------------------------------+
| ``TIMEOUT_SIGNAL_GRACE_PERIOD``    | Signal grace period not supported                |
+------------------------------------+--------------------------------------------------+
| ``TIMEOUT_SIGNAL_NAME``            | Signal name not supported                        |
+------------------------------------+--------------------------------------------------+

Behavior Differences from CTest
-------------------------------

DEPENDS
~~~~~~~

In CTest, the ``DEPENDS`` property sets execution order but does not consider test results. In Canary, dependencies consider test results - if a dependency fails, the dependent test will not run.

RESOURCE_GROUPS
~~~~~~~~~~~~~~~

Canary supports CTest resource specification files. Resource groups are mapped to Canary's resource pool system. See :doc:`resources` for details.

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`status-and-regex` - Status determination behavior
- :doc:`resources` - Resource group handling
