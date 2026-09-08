.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Timeouts
========

The ``canary_flux`` extension implements a comprehensive timeout management system that controls various phases of Flux execution. This system ensures that jobs complete within expected timeframes and provides mechanisms for handling timeout scenarios.

Timeout Types
=============

The Flux extension manages several types of timeouts:

Queue Timeout
-------------

**Purpose**: Limit time waiting for Flux allocation or job submission

**Configuration**:
- Command line: ``--timeout type=queue,T``
- Default: 1200 seconds (20 minutes)
- Environment: No direct environment variable

**Behavior**:
- Maximum time to wait for Flux allocation to be granted
- Also applies to individual job submission wait time
- Raises ``TimeoutError`` if exceeded
- Logs timeout event before raising error

**Examples**:

.. code-block:: console

   # Set queue timeout to 30 minutes
   python3 -m canary flux run --timeout queue=30m ./basic

   # Set queue timeout to 1 hour
   python3 -m canary flux run --timeout queue=1h ./basic

   # Set queue timeout to 300 seconds
   python3 -m canary flux run --timeout queue=300 ./basic

Allocation Timeout
------------------

**Purpose**: Set walltime for outer Flux allocation

**Configuration**:
- Command line: ``--timeout type=allocation,T``
- Default: 3600 seconds (1 hour)
- Can also use ``--alloc-arg="--time-limit=..."``
- Falls back to session timeout if not specified

**Behavior**:
- Converted to minutes for ``--time-limit`` argument to Flux
- Controls maximum runtime for Flux allocation
- Enforced by Flux scheduler
- Logs allocation time limit during setup

**Examples**:

.. code-block:: console

   # Set allocation timeout to 2 hours
   python3 -m canary flux run --timeout allocation=2h ./basic

   # Set allocation timeout to 30 minutes
   python3 -m canary flux run --timeout allocation=30m ./basic

   # Set allocation timeout via alloc-arg
   python3 -m canary flux run --alloc-arg="--time-limit=120" ./basic

Session Timeout
---------------

**Purpose**: Fallback timeout for allocation walltime

**Configuration**:
- Command line: ``--timeout type=session,T``
- Used only if allocation timeout not specified
- No default (only used as fallback)

**Behavior**:
- Used as allocation timeout if no explicit allocation timeout
- Provides safety net for allocation walltime
- Logs as allocation time limit when used

**Examples**:

.. code-block:: console

   # Set session timeout (used as allocation timeout fallback)
   python3 -m canary flux run --timeout session=4h ./basic

Job Timeout
-----------

**Purpose**: Limit runtime for individual jobs

**Configuration**:
- Job specification: ``timeout`` parameter
- Default: Job-specific or no timeout
- Not configured via ``--timeout`` option

**Behavior**:
- Each job's ``total_timeout()`` used for JobspecV1
- Controls maximum runtime for individual jobs
- Independent of allocation walltime
- Enforced by nested Canary execution

**Examples**:

.. code-block:: python

   # Job with 10-minute timeout
   @canary.test(timeout="10m")
   def test_example():
       pass

Timeout Configuration
=====================

The Flux extension supports flexible timeout configuration through command-line options.

Command-Line Syntax
-------------------

Timeouts are configured using the ``--timeout`` option with type-value pairs:

**Syntax**: ``--timeout type=T[type=T...]``

**Type Values**:
- ``queue``: Queue timeout in seconds or time string
- ``allocation``: Allocation timeout in seconds or time string
- ``session``: Session timeout in seconds or time string

**Time String Formats**:
- ``300``: Seconds
- ``30m``: Minutes
- ``2h``: Hours
- ``1h30m``: Combined hours and minutes

**Examples**:

.. code-block:: console

   # Single timeout
   python3 -m canary flux run --timeout queue=30m ./basic

   # Multiple timeouts (comma-separated)
   python3 -m canary flux run --timeout queue=30m,allocation=2h ./basic

   # Multiple timeouts (space-separated)
   python3 -m canary flux run --timeout queue=30m --timeout allocation=2h ./basic

Timeout Resolution
------------------

The Flux extension resolves timeouts through a priority-based system:

**Allocation Timeout Resolution**:
1. Explicit ``--timeout type=allocation,T`` (highest priority)
2. ``--alloc-arg="--time-limit=..."`` parsed for time limit
3. ``--timeout type=session,T`` (fallback)
4. Default: 3600 seconds (lowest priority)

**Queue Timeout Resolution**:
1. Explicit ``--timeout type=queue,T``
2. Default: 1200 seconds

**Job Timeout Resolution**:
1. Job specification timeout
2. No default timeout

Timeout Management Functions
============================

The Flux extension implements several functions for timeout management:

allocation_queue_timeout()
---------------------------

**Purpose**: Get queue timeout value

**Returns**: Queue timeout in seconds (float)

**Behavior**:
- Returns ``config.get_timeout_option("queue")`` if set
- Returns 1200.0 if not set
- Used for allocation request and job submission waits

allocation_time_limit()
------------------------

**Purpose**: Get allocation time limit value

**Returns**: Allocation time limit in seconds (float)

**Behavior**:
- Returns ``config.get_timeout_option("allocation")`` if set
- Parses ``--alloc-arg`` for ``--time-limit`` if available
- Returns ``config.get_timeout_option("session")`` as fallback
- Returns 3600.0 as final default
- Converts time strings to seconds

minutes(seconds)
-----------------

**Purpose**: Convert seconds to minutes (ceiling)

**Returns**: Minutes as float

**Behavior**:
- ``math.ceil(seconds / 60.0)``
- Used to convert allocation timeout to Flux ``--time-limit`` format

Timeout Enforcement
====================

The Flux extension enforces timeouts at various execution phases:

Allocation Phase
----------------

**Queue Timeout Enforcement**:
- Applied during ``allocation.open()`` call
- ``timeout=queue_timeout`` parameter
- Raises ``TimeoutError`` if allocation not granted in time

**Allocation Timeout Enforcement**:
- Converted to ``--time-limit`` argument for Flux
- Enforced by Flux scheduler itself
- Allocation cancelled if walltime exceeded

Job Submission Phase
--------------------

**Queue Timeout Enforcement**:
- Applied during job submission loop
- ``time.time()`` checked against submission start time
- Raises ``TimeoutError("Session time has expired")`` if exceeded

**Behavior**:
- Checked in main execution loop: ``if (time_limit > 0) and (started_on + time_limit < time.time()):``
- Cancels remaining jobs if timeout exceeded
- Closes allocation and exits

Job Execution Phase
-------------------

**Job Timeout Enforcement**:
- Enforced by nested ``canary flux exec`` execution
- Each job's ``total_timeout()`` passed to JobspecV1
- Enforced by inner Canary execution
- Independent of Flux allocation walltime

Timeout Scenarios
=================

The Flux extension handles various timeout scenarios gracefully:

Allocation Queue Timeout
------------------------

**Scenario**: Flux allocation not granted within queue timeout

**Behavior**:
- ``allocation.open()`` raises timeout exception
- Progress monitor marked as failed
- Logs allocation failure
- Returns error exit code

**Recovery**:
- Increase queue timeout
- Check Flux system status
- Reduce node count request

Allocation Walltime Timeout
----------------------------

**Scenario**: Flux allocation walltime exceeded

**Behavior**:
- Flux scheduler cancels allocation
- Running jobs terminated
- Partial results may be available
- Logs allocation cancellation

**Recovery**:
- Increase allocation timeout
- Reduce job count or complexity
- Optimize job runtime

Session Timeout
---------------

**Scenario**: Session time limit exceeded during execution

**Behavior**:
- Main loop detects timeout
- Cancels remaining Flux futures
- Finalizes in-flight jobs
- Closes allocation
- Logs session timeout

**Recovery**:
- Increase session timeout
- Reduce job count
- Use smaller test sets

Job Timeout
-----------

**Scenario**: Individual job exceeds its timeout

**Behavior**:
- Inner Canary execution terminates job
- Job marked with timeout status
- Flux job completes with error
- Logs job timeout

**Recovery**:
- Increase job-specific timeout
- Optimize job implementation
- Reduce job complexity

Timeout Best Practices
======================

1. **Queue Timeout**: Set based on expected Flux queue wait times
2. **Allocation Timeout**: Set based on total expected runtime + buffer
3. **Job Timeouts**: Set per-job based on individual requirements
4. **Buffer Time**: Add 10-20% buffer to account for overhead
5. **Monitoring**: Track actual runtimes and adjust timeouts accordingly
6. **Documentation**: Record timeout configurations and rationale
7. **Testing**: Test with conservative timeouts, then optimize

Timeout Configuration Examples
==============================

Basic Timeout Configuration
---------------------------

.. code-block:: console

   # Set queue and allocation timeouts
   python3 -m canary flux run \
     --timeout queue=30m,allocation=4h \
     ./basic

Advanced Timeout Configuration
------------------------------

.. code-block:: console

   # Set timeouts with alloc-arg fallback
   python3 -m canary flux run \
     --timeout queue=1h \
     --alloc-arg="--time-limit=240" \
     ./basic

Timeout for Different Workloads
--------------------------------

.. code-block:: console

   # Short timeouts for quick tests
   python3 -m canary flux run \
     --timeout queue=10m,allocation=1h \
     ./unit-tests

   # Long timeouts for integration tests
   python3 -m canary flux run \
     --timeout queue=1h,allocation=8h \
     ./integration-tests

Timeout Troubleshooting
=======================

**Queue Timeout Issues**:
- Symptom: Allocation request fails quickly
- Check: Flux system queue status
- Solution: Increase queue timeout or reduce request size

**Allocation Timeout Issues**:
- Symptom: Jobs terminated after fixed time
- Check: Actual runtime vs allocation timeout
- Solution: Increase allocation timeout or optimize jobs

**Session Timeout Issues**:
- Symptom: Execution stops with "Session time has expired"
- Check: Total runtime vs session timeout
- Solution: Increase session timeout or reduce job count

**Job Timeout Issues**:
- Symptom: Individual jobs fail with timeout
- Check: Job-specific timeout settings
- Solution: Increase job timeout or optimize job implementation

Timeout Monitoring
==================

Track timeout-related metrics through:

**Logs**:
- Allocation timing logged during setup
- Timeout events logged when detected
- Progress messages show timing information

**Measurements**:
- ``flux.timing`` contains allocation and job timing
- ``flux.overhead`` shows execution overheads
- Job measurements persisted to workspace

**Process Info**:
- ``procinfo.json`` contains Flux process timing
- Written to submit workspace after completion

Timeout Comparison
==================

**Flux Extension (canary_flux)**:
- Direct timeout management for Flux allocation
- Queue timeout for allocation request
- Allocation timeout for walltime
- Session timeout as fallback
- Individual job timeouts via job specs

**HPC Extension (canary_hpc)**:
- Timeout management for batch submission
- Queue timeout for batch submission
- Run timeout for batch execution
- Batch-level timeout handling
- Different timeout semantics

Use Flux extension for direct Flux timeout management. Use HPC extension for batch-level timeout handling.
