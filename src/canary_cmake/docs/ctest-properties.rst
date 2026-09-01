CTest Properties
================

Canary maps a wide range of CTest properties to its own internal job specifications.

Supported Properties
--------------------

The following CTest properties are supported and mapped to Canary behavior:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Property
     - Canary Mapping
   * - ATTACHED_FILES
     - Added as Canary artifacts (always).
   * - ATTACHED_FILES_ON_FAIL
     - Added as Canary artifacts (on failure).
   * - DEPENDS
     - Created as Canary dependencies (on success).
   * - DISABLED
     - The job is masked (skipped) with a note that it was explicitly disabled.
   * - ENVIRONMENT
     - Added to the job's environment variables.
   * - ENVIRONMENT_MODIFICATION
     - Applied as environment variable modifications (set, unset, append, prepend).
   * - FAIL_REGULAR_EXPRESSION
     - Used during post-execution to mark a job as failed if the pattern matches.
   * - FIXTURES_SETUP / REQUIRED / CLEANUP
     - Mapped to Canary dependencies to ensure correct setup/teardown ordering.
   * - LABELS
     - Added as Canary keywords (along with the default ctest keyword).
   * - PASS_REGULAR_EXPRESSION
     - Used during post-execution to mark a job as successful if the pattern matches.
   * - PROCESSORS
     - Mapped to the cpus parameter.
   * - RESOURCE_GROUPS
     - Mapped to Canary resource requirements.
   * - RUN_SERIAL
     - The job is marked as exclusive.
   * - SKIP_REGULAR_EXPRESSION
     - Used during post-execution to mark a job as skipped if the pattern matches.
   * - SKIP_RETURN_CODE
     - Marks the job as skipped if the return code matches.
   * - TIMEOUT
     - Set as the job's timeout.
   * - WILL_FAIL
     - Inverts the success logic: success is reported if the test fails.
   * - WORKING_DIRECTORY
     - Set as the job's execution directory.

Unsupported Properties
----------------------

The following properties are currently **not** supported. Using them will trigger a warning:

*   COST
*   GENERATED_RESOURCE_SPEC_FILE
*   MEASUREMENT
*   PROCESSOR_AFFINITY
*   REQUIRED_FILES
*   RESOURCE_LOCK
*   TIMEOUT_AFTER_MATCH
*   TIMEOUT_SIGNAL_GRACE_PERIOD
*   TIMEOUT_SIGNAL_NAME
