.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Scheduler Arguments
===================

The ``canary_hpc`` extension supports scheduler-specific arguments that are passed to ``hpc_connect`` for job submission. These arguments enable backend-specific configuration and control.

Scheduler Argument Options
--------------------------

**Modern Argument Options**:

- ``--submit-arg=ARG``: Scheduler-specific submit arguments
- ``--scheduler-args=ARGS``: Alternative scheduler arguments

**Legacy Argument Options**:

- ``-b option=VALUE``: Legacy option syntax
- ``-b args=VALUE``: Legacy args syntax
- ``-b options=VALUE``: Legacy options syntax
- ``-b with=VALUE``: Legacy with syntax

**Environment Variables**:

- ``CANARY_HPC_SUBMIT_ARGS``: Submit arguments from environment
- ``CANARY_HPC_SCHEDULER_ARGS``: Scheduler arguments from environment

Scheduler Argument Syntax
-------------------------

**Modern Syntax**:

.. code-block:: console

   --submit-arg="ARG1,ARG2,..."
   --scheduler-args="ARG1,ARG2,..."

**Legacy Syntax**:

.. code-block:: console

   -b option="ARG1,ARG2,..."
   -b args="ARG1,ARG2,..."

**Argument Parsing**:

- Comma-separated argument lists
- Shell splitting for complex arguments
- Environment variable expansion
- Backend-specific validation

Scheduler Argument Examples
---------------------------

Slurm Arguments
~~~~~~~~~~~~~~~

**Account and Queue**:

.. code-block:: console

   # Modern syntax
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./basic

   # Legacy syntax
   python3 -m canary hpc run --backend=slurm -b option="-A myacct,-q debug" ./basic

**Time Limits**:

.. code-block:: console

   # 2 hour time limit
   python3 -m canary hpc run --backend=slurm --submit-arg="-t 2:00:00" ./basic

   # 30 minute time limit
   python3 -m canary hpc run --backend=slurm --submit-arg="-t 30" ./basic

**Node and CPU Requests**:

.. code-block:: console

   # 4 nodes, 8 CPUs per node
   python3 -m canary hpc run --backend=slurm --submit-arg="-N 4 --ntasks-per-node=8" ./basic

   # 2 nodes, 16 CPUs total
   python3 -m canary hpc run --backend=slurm --submit-arg="-N 2 -n 16" ./basic

**Memory Requests**:

.. code-block:: console

   # 16GB memory per node
   python3 -m canary hpc run --backend=slurm --submit-arg="--mem=16G" ./basic

   # 32GB memory total
   python3 -m canary hpc run --backend=slurm --submit-arg="--mem=32000" ./basic

**GPU Requests**:

.. code-block:: console

   # 2 GPUs per node
   python3 -m canary hpc run --backend=slurm --submit-arg="--gres=gpu:2" ./basic

   # Specific GPU type
   python3 -m canary hpc run --backend=slurm --submit-arg="--gres=gpu:v100:2" ./basic

PBS Arguments
~~~~~~~~~~~~~

**Queue Selection**:

.. code-block:: console

   # Select work queue
   python3 -m canary hpc run --backend=pbs --submit-arg="-q workq" ./basic

   # Select debug queue
   python3 -m canary hpc run --backend=pbs --submit-arg="-q debug" ./basic

**Walltime**:

.. code-block:: console

   # 2 hour walltime
   python3 -m canary hpc run --backend=pbs --submit-arg="-l walltime=2:00:00" ./basic

   # 30 minute walltime
   python3 -m canary hpc run --backend=pbs --submit-arg="-l walltime=00:30:00" ./basic

**Resource Requests**:

.. code-block:: console

   # 4 nodes, 8 CPUs per node
   python3 -m canary hpc run --backend=pbs --submit-arg="-l nodes=4:ppn=8" ./basic

   # 16GB memory
   python3 -m canary hpc run --backend=pbs --submit-arg="-l mem=16gb" ./basic

Flux Arguments
~~~~~~~~~~~~~~

**Flags**:

.. code-block:: console

   # Debug flags
   python3 -m canary hpc run --backend=flux --submit-arg="--flags=debug" ./basic

   # Specific flags
   python3 -m canary hpc run --backend=flux --submit-arg="--flags=debug,verbose" ./basic

**Resource Requests**:

.. code-block:: console

   # 4 nodes
   python3 -m canary hpc run --backend=flux --submit-arg="-N 4" ./basic

   # 8 CPUs per task
   python3 -m canary hpc run --backend=flux --submit-arg="-n 8" ./basic

Shell Arguments
~~~~~~~~~~~~~~~

**Shell backend typically doesn't need arguments**:

.. code-block:: console

   # Simple shell execution
   python3 -m canary hpc run --backend=shell ./basic

   # Shell with batch specification
   python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic

Environment Variable Arguments
------------------------------

**CANARY_HPC_SUBMIT_ARGS**:

.. code-block:: console

   # Set environment variable
   export CANARY_HPC_SUBMIT_ARGS="-A myacct,-q debug"

   # Use environment variable
   python3 -m canary hpc run --backend=slurm ./basic

**CANARY_HPC_SCHEDULER_ARGS**:

.. code-block:: console

   # Set environment variable
   export CANARY_HPC_SCHEDULER_ARGS="-l walltime=2:00:00"

   # Use environment variable
   python3 -m canary hpc run --backend=pbs ./basic

Per-Batch Scheduler Arguments
-----------------------------

The scheduler arguments described above (``--submit-arg`` / ``-b option=`` and
the environment variable) apply globally to every batch.  To vary scheduler
arguments *per batch* — for example to send small single-node batches to a
different partition or with a shorter wall time than large multi-node batches —
implement the ``canary_hpc_batch_setup`` plugin hook.

The hook is called once for each batch after batching is complete and before the
batch is submitted.  Implementations inspect the batch and attach raw scheduler
options with :meth:`TestBatch.add_submit_option`:

.. code-block:: python

   import canary


   @canary.hookimpl
   def canary_hpc_batch_setup(batch) -> None:
       # batch.spec.node_count is the number of nodes this batch will request.
       if batch.spec.node_count <= 1:
           batch.add_submit_option("--time=5m", "--partition=short,batch")
       else:
           batch.add_submit_option("--time=10:00:00", "--partition=batch")

The option strings are passed through to the scheduler unmodified; canary_hpc
does not interpret them (the sole exception is ``--time`` / ``--time-limit``,
which canary reads to size the batch wall time and to warn when a requested wall
limit is shorter than the estimated runtime).

.. note::

   The hook attaches options to an *already-formed* batch; it does not change how
   jobs are grouped into batches.  Because a single scheduler allocation cannot
   span multiple partitions, if you need different partitions per problem, first
   arrange for those jobs to land in separate batches — for example by giving
   them different node counts via ``parameterize("nodes", ...)`` together with
   ``-b spec=count:max``.

Precedence
~~~~~~~~~~

Per-batch options are combined with the global submit arguments.  The global
(command-line) options are applied **last**, so they take precedence on
conflicting flags.  For example, if a plugin sets ``--time=5m`` on a batch and
the user also runs with ``--submit-arg="--time=30m"``, the batch is submitted
with a 30-minute wall time.

Argument Passing Mechanism
--------------------------

**Argument Flow**:

1. User specifies scheduler arguments
2. Arguments parsed and validated
3. Arguments passed to ``hpc_connect.JobSpec(..., submit_args=...)``
4. ``hpc_connect`` backend handles submission with arguments

**Argument Processing**:

.. code-block:: python

   # Argument parsing from argparsing.py
   def parse_scheduler_args(args):
       # Parse comma-separated arguments
       # Handle shell splitting
       # Validate backend compatibility
       # Return processed arguments

**Job Specification**:

.. code-block:: python

   # Create job specification with arguments
   job_spec = hpc_connect.JobSpec(
       name="canary-batch",
       command=["python", "-m", "canary", "hpc", "exec"],
       submit_args=["-A", "myacct", "-q", "debug"],
       resources={"cpus": 8, "nodes": 2}
   )

Scheduler Argument Debugging
----------------------------

**Argument Validation**:

.. code-block:: console

   # Test argument parsing
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct" --verbose ./basic

   # Check backend compatibility
   python3 -m canary hpc info slurm

**Argument Inspection**:

.. code-block:: console

   # Show backend information
   python3 -m canary hpc info slurm

   # Test with different arguments
   python3 -m canary hpc run --backend=slurm --submit-arg="-q debug" --verbose ./basic

Scheduler Argument Limitations
------------------------------

1. **Backend-Specific**: Arguments depend on backend capabilities
2. **Validation**: Backend validates arguments before submission
3. **Parsing**: Complex arguments may require proper quoting
4. **Compatibility**: Arguments must match backend expectations
5. **Environment**: Environment variables override command-line arguments
6. **Legacy Syntax**: Legacy options maintained for compatibility

Scheduler Argument Best Practices
---------------------------------

1. **Backend Documentation**: Consult backend documentation for valid arguments
2. **Testing**: Test arguments with verbose logging
3. **Quoting**: Use proper quoting for complex arguments
4. **Validation**: Validate arguments before production use
5. **Environment**: Use environment variables for common configurations
6. **Documentation**: Record working argument configurations
7. **Compatibility**: Prefer modern syntax for new configurations