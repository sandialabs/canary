.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Artifacts
=========

Attach files to CDash tests as artifacts.

Artifact Types
--------------

The CDash reporter handles several types of artifacts:

1. **Job Output**: Captured stdout/stderr from job execution
2. **Custom Artifacts**: Files added via ``canary_cdash_artifacts`` hook
3. **Compressed Output**: Large output files are compressed

Job Output Artifacts
--------------------

Canary automatically captures job output:

- **stdout**: Standard output from job execution
- **stderr**: Standard error from job execution
- **Combined**: Both streams captured together

Output Compression
~~~~~~~~~~~~~~~~~~

Large output is automatically compressed:

- **Threshold**: Output larger than threshold is compressed
- **Format**: ``.tgz`` compression
- **Preservation**: Original output preserved in workspace

Custom Artifacts
----------------

Add additional files via plugin hook:

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       """Add custom artifacts to CDash tests"""
       artifacts = []

       # Add debug logs for failed tests
       if case.status.is_failure():
           debug_log = f"/logs/{case.spec.family}.debug.log"
           if os.path.exists(debug_log):
               artifacts.append(debug_log)

       # Add performance data for performance tests
       if "perf" in case.spec.keywords:
           perf_file = f"/perf/{case.spec.family}.perf.json"
           if os.path.exists(perf_file):
               artifacts.append(perf_file)

       return artifacts

Artifact Handling
-----------------

Artifacts are:

1. **Copied**: Files are copied to CDash output directory
2. **Compressed**: Large files are compressed
3. **Referenced**: Added to CDash XML as attachments
4. **Uploaded**: Sent to CDash server with test results

Artifact Limitations
--------------------

- **Size Limits**: CDash may have file size limits
- **Type Restrictions**: Some file types may be blocked
- **Path Length**: Long paths may cause issues
- **Permissions**: Files must be readable by Canary process

Artifact Best Practices
-----------------------

1. **Relevance**: Only attach relevant files
2. **Size**: Keep artifacts reasonably sized
3. **Naming**: Use descriptive artifact names
4. **Organization**: Store artifacts in logical locations
5. **Cleanup**: Remove unnecessary artifacts after upload

Artifact Examples
-----------------

Debug Logs
~~~~~~~~~~

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       if case.status.is_failure():
           return [f"/debug/{case.spec.family}.log"]
       return []

Performance Data
~~~~~~~~~~~~~~~~

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       if "perf" in case.spec.keywords:
           return [f"/perf/{case.spec.family}.json"]
       return []

Test-Specific Files
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @canary.hookimpl
   def canary_cdash_artifacts(case):
       # Attach test-specific configuration files
       config_file = f"/config/{case.spec.family}.config"
       if os.path.exists(config_file):
           return [config_file]
       return []

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`reporter-plugin` - Plugin hooks
- :doc:`customization` - Customization examples