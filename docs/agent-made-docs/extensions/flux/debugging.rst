.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging
=========

The ``canary_flux`` extension provides comprehensive debugging capabilities to help diagnose and resolve issues during Flux execution. These capabilities include logging, workspace inspection, environment capture, and metadata collection.

Debugging Artifacts
===================

The Flux extension creates several debugging artifacts during execution:

Environment Capture
-------------------

**File**: ``env.json``

**Location**: Job workspace

**Contents**:
- Full environment dictionary at job finish
- All environment variables and values
- Captured by ``canary_runtest_finish`` hook

**Purpose**:
- Debug environment-related issues
- Verify Flux environment variables
- Check resource assignment variables

**Example**:

.. code-block:: json

   {
     "FLUX_JOB_ID": "abc123",
     "FLUX_URI": "flux://localhost:8050",
     "CUDA_VISIBLE_DEVICES": "0,1",
     "CANARY_FLUX_DIRECT_JOB": "abc123def456",
     "CANARY_GPU_IDS": "0,1",
     "..."
   }

Process Info
------------

**File**: ``procinfo.json``

**Location**: Submit workspace (``<cache_dir>/canary-flux/<session>/jobs/<job-id>``)

**Contents**:
- Canary job ID and name
- Flux process information
- Scheduler metadata
- Job execution details

**Purpose**:
- Debug Flux execution issues
- Verify process information
- Check scheduler metadata

**Example**:

.. code-block:: json

   {
     "canary_job_id": "abc123def456",
     "canary_job_name": "test_example[cpus=4,gpus=2]",
     "flux_proc_info": {
       "jobid": "abc123",
       "exit_code": 0,
       "start_time": "2024-01-01T00:00:00Z",
       "end_time": "2024-01-01T00:01:00Z"
     }
   }

Flux Output Files
-----------------

**Files**: ``flux.out``, ``flux.err``

**Location**: Submit workspace

**Contents**:
- ``flux.out``: Flux job stdout
- ``flux.err``: Flux job stderr
- Output from ``canary flux exec`` execution

**Purpose**:
- Debug job output issues
- Verify command execution
- Check for errors during execution

Testcase Lock File
------------------

**File**: ``testcase.lock``

**Location**: Job workspace

**Contents**:
- Authoritative job status
- Job measurements
- Timing information
- Resource assignments

**Purpose**:
- Persist job status between parent and child
- Store authoritative results
- Enable status propagation

Debugging Commands
==================

The Flux extension supports several debugging commands and options:

Debug Mode
----------

**Option**: ``-d`` or ``--debug``

**Behavior**:
- Enables debug logging
- Disables live console updates
- Provides detailed execution information

**Example**:

.. code-block:: console

   python3 -m canary flux run -d ./basic

Verbose Logging
---------------

**Configuration**: Set logging level via environment or configuration

**Behavior**:
- Logs detailed execution information
- Shows timing metrics
- Records resource assignments

**Example**:

.. code-block:: console

   CANARY_LOG_LEVEL=DEBUG python3 -m canary flux run ./basic

Workspace Inspection
--------------------

**Command**: Manual inspection of workspace directories

**Behavior**:
- Inspect job workspaces for artifacts
- Check submit workspaces for Flux files
- Review environment and process info files

**Example**:

.. code-block:: console

   # Find workspace location
   python3 -m canary info workspace

   # Inspect job workspace
   ls <workspace>/sessions/<session>/jobs/<job-id>

   # Inspect submit workspace
   ls <workspace>/.cache/canary-flux/<session>/jobs/<job-id>

Debugging Techniques
====================

Environment Debugging
---------------------

**Check Flux Environment**:

.. code-block:: console

   # Verify Flux environment variables
   cat <job-workspace>/env.json | grep FLUX

   # Check GPU assignment
   cat <job-workspace>/env.json | grep CUDA_VISIBLE_DEVICES

   # Verify resource variables
   cat <job-workspace>/env.json | grep CANARY

**Common Issues**:
- Missing Flux environment variables
- Incorrect GPU device assignment
- Missing resource variables

Resource Debugging
------------------

**Check Resource Pool**:

.. code-block:: console

   # Review resource pool structure
   python3 -m canary info resources

   # Check job resource assignments
   cat <job-workspace>/testcase.lock | grep resources

**Common Issues**:
- Resource pool mismatch with backend
- Incorrect resource counts
- Missing resource types

Timeout Debugging
-----------------

**Check Timing Information**:

.. code-block:: console

   # Review timing measurements
   cat <job-workspace>/testcase.lock | grep flux.timing

   # Check allocation timing
   cat <job-workspace>/testcase.lock | grep allocation

**Common Issues**:
- Allocation wait time too long
- Job execution exceeding timeouts
- Incorrect timeout configuration

Submission Debugging
--------------------

**Check Submission Status**:

.. code-block:: console

   # Review Flux output
   cat <submit-workspace>/flux.out

   # Check Flux errors
   cat <submit-workspace>/flux.err

   # Verify process info
   cat <submit-workspace>/procinfo.json

**Common Issues**:
- Submission failures
- Flux job errors
- Incorrect command generation

Failure Debugging
-----------------

**Check Failure Status**:

.. code-block:: console

   # Review job status
   python3 -m canary status <job-id>

   # Check failure reason
   cat <job-workspace>/testcase.lock | grep status

**Common Issues**:
- Job submission failures
- Execution errors
- Timeout failures

Debugging Scenarios
====================

Allocation Failure
------------------

**Symptoms**:
- Allocation request times out
- Allocation not granted
- Queue wait exceeds timeout

**Debugging Steps**:

1. Check queue timeout setting
2. Review Flux system status
3. Verify node count request
4. Check allocation arguments

**Solution**:
- Increase queue timeout
- Reduce node count
- Check Flux configuration

Submission Failure
------------------

**Symptoms**:
- Jobs not submitted
- Submission errors logged
- Jobs stuck in pending state

**Debugging Steps**:

1. Check Flux output files
2. Review process info
3. Verify job requirements
4. Check resource pool

**Solution**:
- Fix job specifications
- Adjust resource requirements
- Check Flux submission limits

Execution Failure
-----------------

**Symptoms**:
- Jobs fail during execution
- Non-zero exit codes
- Execution errors logged

**Debugging Steps**:

1. Check Flux output/error files
2. Review environment capture
3. Verify resource assignments
4. Check job timeout settings

**Solution**:
- Fix job implementation
- Adjust resource requirements
- Increase job timeouts

Timeout Failure
---------------

**Symptoms**:
- Jobs timeout during execution
- Session time exceeded
- Allocation walltime reached

**Debugging Steps**:

1. Check timing measurements
2. Review timeout configuration
3. Verify actual runtimes
4. Check overhead metrics

**Solution**:
- Increase timeout settings
- Optimize job runtime
- Reduce job complexity

Resource Assignment Failure
---------------------------

**Symptoms**:
- Missing GPU assignments
- Incorrect CPU counts
- Resource mismatch errors

**Debugging Steps**:

1. Check environment capture
2. Review resource pool
3. Verify Flux environment variables
4. Check backend resource counts

**Solution**:
- Fix backend configuration
- Adjust job requirements
- Verify Flux resource allocation

Debugging Tools
===============

Logging
-------

The Flux extension provides detailed logging for debugging:

**Log Levels**:
- ``DEBUG``: Detailed execution information
- ``INFO``: High-level execution status
- ``WARNING``: Potential issues
- ``ERROR``: Execution errors

**Log Configuration**:

.. code-block:: console

   # Set log level via environment
   CANARY_LOG_LEVEL=DEBUG python3 -m canary flux run ./basic

   # Set log level via configuration
   python3 -m canary flux run -o log-level=debug ./basic

**Log Output**:
- Allocation timing and status
- Job submission and execution
- Resource assignment
- Timeout management

Status Commands
---------------

Use Canary status commands to monitor Flux execution:

**Job Status**:

.. code-block:: console

   # Check job status
   python3 -m canary status <job-id>

   # Check all jobs
   python3 -m canary status -rA

**Session Status**:

.. code-block:: console

   # Check session status
   python3 -m canary status -s <session>

   # Check session with details
   python3 -m canary status -s <session> -v

Workspace Commands
------------------

Use workspace commands to inspect Flux workspaces:

**Workspace Info**:

.. code-block:: console

   # Show workspace information
   python3 -m canary info workspace

   # Show session information
   python3 -m canary info sessions

**Job Inspection**:

.. code-block:: console

   # List jobs in session
   python3 -m canary info jobs -s <session>

   # Show job details
   python3 -m canary info job <job-id>

Debugging Best Practices
========================

1. **Enable Debug Logging**: Use ``-d`` or ``CANARY_LOG_LEVEL=DEBUG``
2. **Capture Environment**: Review ``env.json`` for environment issues
3. **Inspect Process Info**: Check ``procinfo.json`` for execution details
4. **Review Output Files**: Examine ``flux.out`` and ``flux.err``
5. **Check Timing**: Analyze timing metrics in job measurements
6. **Validate Resources**: Verify resource pool and assignments
7. **Monitor Status**: Use status commands to track execution
8. **Document Issues**: Record debugging findings and solutions

Debugging Configuration
=======================

Debug Configuration Example
---------------------------

.. code-block:: console

   # Run with debug logging and detailed output
   CANARY_LOG_LEVEL=DEBUG python3 -m canary flux run -d \
     --timeout queue=1h,allocation=4h \
     ./basic

Debug Environment Variables
---------------------------

**``CANARY_LOG_LEVEL``**: Set logging level

**``CANARY_DEBUG``**: Enable debug mode

**``CANARY_FLUX_DEBUG``**: Enable Flux-specific debugging

Debug Command Aliases
---------------------

Create command aliases for common debugging tasks:

.. code-block:: bash

   # Debug alias
   alias canary-flux-debug='CANARY_LOG_LEVEL=DEBUG python3 -m canary flux run -d'

   # Environment inspection
   alias flux-env='cat $(python3 -m canary info workspace)/sessions/*/jobs/*/env.json | jq .'

Debugging Comparison
====================

**Flux Extension (canary_flux)**:
- Direct Flux execution debugging
- Individual job inspection
- Fine-grained timing metrics
- Direct environment capture
- Lower overhead for debugging

**HPC Extension (canary_hpc)**:
- Batch-level debugging
- Batch workspace inspection
- Batch status aggregation
- Higher overhead due to batching
- More complex debugging flow

Use Flux extension for direct, fine-grained debugging. Use HPC extension for batch-level debugging.
