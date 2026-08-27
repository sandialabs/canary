.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-query:

Query
=====

Canary provides different commands for different types of inspection:

- ``canary query``: Inspect job and session serialized data (lock files)
- ``canary learn capabilities``: Query static capability knowledge
- ``canary learn skills``: Query bundled agent skills

These commands enable detailed introspection of Canary's internal state and configuration.

Query Command
-------------

The ``canary query`` command inspects job and session data, while ``canary learn`` queries capabilities and skills:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./basic, python3 -m canary learn capabilities]
   :cwd: /examples

Query capabilities to understand Canary's configuration and available features.

Query Targets
--------------

**Job Lock Files**: Inspect individual test execution data

.. code-block:: console

   $ canary query -j JOB_ID
   {
     "id": "JOB_ID",
     "spec": {...},
     "status": {...},
     "measurements": {...}
   }

**Session Lock Files**: Examine session-level information

.. code-block:: console

   $ canary query -s SESSION_ID
   {
     "session": "SESSION_ID",
     "jobs": [...],
     "started_on": "...",
     "finished_on": "..."
   }

**Capabilities**: Query Canary's static capability database

.. code-block:: console

   $ canary learn capabilities
   {
     "overview": {...},
     "hooks": {...},
     "resources": {...}
   }

**Skills**: Query Canary's skills database

.. code-block:: console

   $ canary learn skills canary-orientation
   {
     "name": "canary-orientation",
     "description": "...",
     "body": "..."
   }

Query Syntax
------------

The query command supports path-based navigation through JSON data:

.. code-block:: console

   # Query specific field
   $ canary query -j JOB_ID .status.category
   "PASS"

   # Query nested structure
   $ canary query -j JOB_ID .spec.parameters
   {"cpus": 4, "gpus": 2}

   # Query array element
   $ canary query -j JOB_ID .dependencies[0]
   {"id": "DEP_ID", "status": "PASS"}

Query Features
--------------

**Path Navigation**: Use dot notation to navigate JSON structures

.. code-block:: console

   $ canary learn capabilities .hooks.post
   {
     "description": "Post-execution hooks",
     "available": [...]
   }

**Array Indexing**: Access specific array elements

.. code-block:: console

   $ canary query -j JOB_ID .dependencies[0].id
   "DEP_ID"

**Terse Output**: Compact single-line JSON format

.. code-block:: console

   $ canary query --terse -j JOB_ID .status.category
   "PASS"

**Markdown Export**: Write skill documentation as Markdown

.. code-block:: console

   $ canary learn skills canary-orientation --markdown skill.md

Common Query Patterns
---------------------

**Check Job Status**:

.. code-block:: console

   $ canary query -j JOB_ID .status.outcome
   "PASSED"

**Inspect Job Parameters**:

.. code-block:: console

   $ canary query -j JOB_ID .spec.parameters
   {"cpus": 4, "gpus": 2, "timeout": 300}

**View Session Jobs**:

.. code-block:: console

   $ canary query -s SESSION_ID .jobs
   ["JOB_1", "JOB_2", "JOB_3"]

**Check Capability Overview**:

.. code-block:: console

   $ canary learn capabilities .overview
   {
     "description": "Canary overview",
     "version": "..."
   }

**List Available Skills**:

.. code-block:: console

   $ canary learn skills --list
   ["canary-orientation", "canary-test-authoring", ...]

Query Use Cases
---------------

**Debugging**: Inspect job state and configuration

.. code-block:: console

   $ canary query -j FAILED_JOB_ID .status.reason
   "AssertionError: expected 42, got 24"

**Performance Analysis**: Examine execution metrics

.. code-block:: console

   $ canary query -j JOB_ID .measurements.duration
   42.5

**Dependency Analysis**: Understand job relationships

.. code-block:: console

   $ canary query -j JOB_ID .dependencies
   [{"id": "DEP_1", "status": "PASS"}, ...]

**Configuration Verification**: Check resource pool setup

.. code-block:: console

   $ canary learn capabilities .resources
   {"cpus": 32, "gpus": 8, "allow_multinode": true}

Query in Scripts
----------------

Use query in shell scripts for automation:

.. code-block:: bash

   # Get job status and take action
   STATUS=$(canary query -j $JOB_ID .status.outcome)
   if [ "$STATUS" = "FAILED" ]; then
       echo "Job failed, sending notification"
       # notification logic
   fi

   # Extract job parameters
   CPUS=$(canary query -j $JOB_ID .spec.parameters.cpus)
   echo "Job used $CPUS CPUs"

Query Best Practices
--------------------

- **Specific Queries**: Query only needed data to reduce output
- **Terse Format**: Use ``--terse`` for script consumption
- **Error Handling**: Check query results in scripts
- **Documentation**: Use query output for debugging documentation
- **Performance**: Avoid querying large datasets unnecessarily

Query Troubleshooting
---------------------

**Invalid Query Path**:

.. code-block:: console

   $ canary query -j JOB_ID .nonexistent.path
   Error: No such key: 'nonexistent'. Available keys: status, spec, ...

Solution: Check available keys and correct the query path.

**Missing Data**:

.. code-block:: console

   $ canary query -j INVALID_ID
   Error: FileNotFoundError: testcase.lock not found

Solution: Verify the job/session ID exists.

**Invalid JSON Path**:

.. code-block:: console

   $ canary query -j JOB_ID .dependencies[10]
   Error: No such index: 10. Array length is 3.

Solution: Check array bounds before indexing.

Query Reference
---------------

**Command Help**:

.. code-block:: console

   $ canary query -h

**Capability Reference**:

.. code-block:: console

   $ canary learn capabilities

**Skill Reference**:

.. code-block:: console

   $ canary learn skills --list

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`persistence`: Database structure and queries
- :doc:`results`: Result inspection and analysis
- :doc:`/reference/commands.query`: Query command reference