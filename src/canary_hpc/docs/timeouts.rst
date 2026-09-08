.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Timeouts
========

The ``canary_hpc`` extension supports multiple timeout mechanisms to control job execution duration and prevent indefinite waiting. Understanding these timeout types is essential for effective HPC job management.

Timeout Types
-------------

Queue Timeout
~~~~~~~~~~~~~

**Description**: Maximum time to wait in the scheduler queue before treating the job as timed out.

**Option**: ``--timeout queue=T``

**Behavior**:

- Starts when job is submitted to scheduler
- Ends when job starts execution
- Prevents indefinite queue waiting
- Configurable per backend

**Examples**:

.. code-block:: console

   # 30 minute queue timeout
   python3 -m canary hpc run --backend=slurm --timeout queue=30m ./basic

   # 2 hour queue timeout
   python3 -m canary hpc run --backend=slurm --timeout queue=2h ./basic

Run Timeout
~~~~~~~~~~~

**Description**: Maximum time for job execution after scheduler job starts.

**Option**: ``--timeout run=T``

**Behavior**:

- Starts when job begins execution
- Ends when job completes or times out
- Prevents indefinite job execution
- Configurable per backend

**Examples**:

.. code-block:: console

   # 1 hour run timeout
   python3 -m canary hpc run --backend=slurm --timeout run=1h ./basic

   # 30 minute run timeout
   python3 -m canary hpc run --backend=slurm --timeout run=30m ./basic

Total Timeout
~~~~~~~~~~~~~

**Description**: Total timeout combining queue and run time.

**Behavior**:

- Queue timeout + run timeout
- Maximum total job duration
- Prevents overall job overrun

**Examples**:

.. code-block:: console

   # 30m queue + 2h run = 2h30m total
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h ./basic

Per-Test Timeout Multiplier
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**: Multiplier affecting batch runtime via ``timeout_multiplier``.

**Option**: ``--timeout TYPE=T`` (where TYPE is a test keyword)

**Behavior**:

- Multiplies individual test timeouts
- Affects overall batch duration
- Configurable per test type

**Examples**:

.. code-block:: console

   # 2x multiplier for fast tests
   python3 -m canary hpc run --backend=slurm --timeout fast=2 ./basic

   # 3x multiplier for long tests
   python3 -m canary hpc run --backend=slurm --timeout long=3 ./basic

Scheduler Time Limits
---------------------

**Description**: Scheduler-specific time limits passed in submit arguments.

**Behavior**:

- ``--time`` or ``--time-limit`` in scheduler submit args
- Influences estimated runtime
- Backend-specific syntax

**Examples**:

.. code-block:: console

   # Slurm time limit
   python3 -m canary hpc run --backend=slurm --submit-arg="-t 2:00:00" ./basic

   # PBS walltime
   python3 -m canary hpc run --backend=pbs --submit-arg="-l walltime=2:00:00" ./basic

   # Flux time limit
   python3 -m canary hpc run --backend=flux --submit-arg="--time=2h" ./basic

Timeout Configuration
---------------------

**Combined Timeout Configuration**:

.. code-block:: console

   # Queue, run, and test timeouts
   python3 -m canary hpc run --backend=slurm \
     --timeout queue=30m,run=2h,fast=2,long=3 \
     --submit-arg="-t 2:30:00" \
     ./tests

**Default Timeout Behavior**:

- Queue timeout: Backend-specific default
- Run timeout: Backend-specific default
- Test multipliers: No multiplier (1x)
- Scheduler limits: No explicit limit

Timeout Behavior
----------------

**Queue Timeout Behavior**:

- Job submitted to scheduler queue
- Queue timeout starts
- If timeout exceeded before job starts: Job marked as timed out
- If job starts before timeout: Queue timeout ends, run timeout starts

**Run Timeout Behavior**:

- Job starts execution
- Run timeout starts
- If timeout exceeded during execution: Job cancelled
- If job completes before timeout: Run timeout ends successfully

**Total Timeout Behavior**:

- Job submitted to scheduler
- Total timeout starts (queue + run)
- If total timeout exceeded: Job cancelled regardless of phase
- Ensures maximum job duration

Timeout Examples
----------------

Basic Timeout Examples
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # 30 minute queue timeout
   python3 -m canary hpc run --backend=slurm --timeout queue=30m ./basic

   # 1 hour run timeout
   python3 -m canary hpc run --backend=slurm --timeout run=1h ./basic

   # Combined queue and run timeouts
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h ./basic

Advanced Timeout Examples
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Queue, run, and test multipliers
   python3 -m canary hpc run --backend=slurm \
     --timeout queue=30m,run=2h,fast=2,long=3 \
     ./tests

   # With scheduler time limit
   python3 -m canary hpc run --backend=slurm \
     --timeout queue=30m,run=2h \
     --submit-arg="-t 2:30:00" \
     ./tests

Backend-Specific Timeout Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Slurm**:

.. code-block:: console

   # Slurm with time limits
   python3 -m canary hpc run --backend=slurm \
     --timeout queue=30m,run=2h \
     --submit-arg="-t 2:30:00" \
     ./tests

**PBS**:

.. code-block:: console

   # PBS with walltime
   python3 -m canary hpc run --backend=pbs \
     --timeout queue=30m,run=2h \
     --submit-arg="-l walltime=2:30:00" \
     ./tests

**Flux**:

.. code-block:: console

   # Flux with time limit
   python3 -m canary hpc run --backend=flux \
     --timeout queue=30m,run=2h \
     --submit-arg="--time=2h30m" \
     ./tests

Timeout Debugging
-----------------

**Timeout Inspection**:

.. code-block:: console

   # Check timeout configuration
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h --verbose ./basic

   # Monitor timeout behavior
   python3 -m canary hpc run --backend=slurm --timeout queue=5m,run=10m --verbose ./basic

**Timeout Validation**:

.. code-block:: console

   # Test short timeouts
   python3 -m canary hpc run --backend=slurm --timeout queue=1m,run=1m --verbose ./basic

   # Check scheduler time limits
   python3 -m canary hpc run --backend=slurm --submit-arg="-t 5m" --verbose ./basic

Timeout Limitations
-------------------

1. **Backend Dependency**: Timeout behavior depends on backend capabilities
2. **Scheduler Constraints**: Limited by scheduler time limit policies
3. **Queue Variability**: Queue wait times may vary
4. **Run Variability**: Execution times may vary
5. **Total Timeout**: Maximum job duration enforced
6. **Multiplier Impact**: Test multipliers affect overall duration

Timeout Best Practices
----------------------

1. **Realistic Timeouts**: Set timeouts based on expected job duration
2. **Queue Monitoring**: Monitor queue wait times
3. **Run Monitoring**: Monitor execution times
4. **Total Limits**: Set maximum total duration
5. **Test Multipliers**: Use multipliers for variable test durations
6. **Scheduler Limits**: Align with scheduler time limit policies
7. **Testing**: Test timeout configurations
8. **Documentation**: Record timeout configurations