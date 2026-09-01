.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

The ``canary_hpc`` extension provides several commands for HPC batch execution and management. These commands enable users to submit, monitor, and debug HPC batch executions.

Modern HPC Commands
-------------------

The ``canary hpc`` command provides subcommands for HPC operations:

.. code-block:: console

   python3 -m canary hpc [-h] [subcommand] ...

Subcommands
~~~~~~~~~~~

hpc run
^^^^^^^

**Purpose**: Batch jobs and submit to HPC scheduler

**Usage**:

.. code-block:: console

   python3 -m canary hpc run [options] [paths...]

**Description**:

The ``hpc run`` command collects jobs, forms batches, and submits them to the HPC scheduler. It replaces Canary's local execution with HPC batching and submission.

**Options**:

- ``--backend=BACKEND``: HPC backend to use (e.g., slurm, pbs, flux, shell)
- ``--batch-spec=SPEC``: Batch specification (e.g., "duration=30m,layout=flat")
- ``--timeout TYPE=T``: Timeout configuration (queue, run, or total)
- ``--submit-arg=ARG``: Scheduler-specific submit arguments
- ``--workers=N``: Number of workers for batch execution
- Standard Canary test selection and execution options

**Examples**:

.. code-block:: console

   # Run with Slurm backend
   python3 -m canary hpc run --backend=slurm ./basic

   # Run with batch specification
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=30m ./basic

   # Run with scheduler arguments
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./basic

   # Run with timeout configuration
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h ./basic

hpc exec
^^^^^^^^

**Purpose**: Execute (run) the batch

**Usage**:

.. code-block:: console

   python3 -m canary hpc exec [options]

**Description**:

The ``hpc exec`` command executes a batch within its workspace. This is typically called by the scheduler job script, not directly by users.

**Options**:

- ``--batch-id=ID``: Batch ID to execute
- ``--workers=N``: Number of workers for batch execution
- ``--backend=BACKEND``: HPC backend name
- ``--workspace=PATH``: Batch workspace path

**Examples**:

.. code-block:: console

   # Execute specific batch
   python3 -m canary hpc exec --batch-id=abc123 --backend=slurm

   # Execute with workers
   python3 -m canary hpc exec --batch-id=abc123 --workers=4

hpc info
^^^^^^^^

**Purpose**: Show HPC scheduler basic info

**Usage**:

.. code-block:: console

   python3 -m canary hpc info BACKEND

**Description**:

The ``hpc info`` command displays information about the specified HPC backend, including available resources and capabilities.

**Arguments**:

- ``BACKEND``: Backend name (e.g., slurm, pbs, flux, shell)

**Examples**:

.. code-block:: console

   # Show Slurm backend info
   python3 -m canary hpc info slurm

   # Show PBS backend info
   python3 -m canary hpc info pbs

   # Show shell backend info
   python3 -m canary hpc info shell

hpc log
^^^^^^^

**Purpose**: Print the batch log

**Usage**:

.. code-block:: console

   python3 -m canary hpc log [BATCH_ID]

**Description**:

The ``hpc log`` command displays the log for a specific batch or all batches if no ID is specified.

**Arguments**:

- ``BATCH_ID``: Optional batch ID to show log for

**Examples**:

.. code-block:: console

   # Show log for specific batch
   python3 -m canary hpc log abc123

   # Show logs for all batches
   python3 -m canary hpc log

hpc help
^^^^^^^^

**Purpose**: Additional canary_hpc help topics

**Usage**:

.. code-block:: console

   python3 -m canary hpc help [--spec]

**Description**:

The ``hpc help`` command provides additional help topics and information about HPC functionality.

**Options**:

- ``--spec``: Show batch specification help

**Examples**:

.. code-block:: console

   # Show HPC help
   python3 -m canary hpc help

   # Show batch specification help
   python3 -m canary hpc help --spec

Legacy Batch Options
--------------------

The HPC extension also supports legacy batch options for compatibility:

canary run with HPC backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Purpose**: Run with HPC backend using legacy options

**Usage**:

.. code-block:: console

   python3 -m canary run --hpc-backend=BACKEND [options] [paths...]

**Description**:

The ``--hpc-backend`` option enables HPC execution mode, which is internally rewritten to ``hpc run`` by the ``canary_cmdline_modifyargs`` hook.

**Options**:

- ``--hpc-backend=BACKEND``: HPC backend to use
- Standard Canary test selection and execution options

**Examples**:

.. code-block:: console

   # Run with HPC backend
   python3 -m canary run --hpc-backend=slurm ./tests

   # Run with backend and batch spec
   python3 -m canary run --hpc-backend=slurm -b spec=duration=30m ./tests

Legacy -b options
~~~~~~~~~~~~~~~~~

**Purpose**: Legacy batch specification options

**Usage**:

.. code-block:: console

   python3 -m canary run -b OPTION=VALUE [options] [paths...]

**Description**:

The ``-b`` option provides legacy batch specification syntax for compatibility with older Canary versions.

**Options**:

- ``-b backend=BACKEND``: HPC backend
- ``-b spec=SPEC``: Batch specification
- ``-b workers=N``: Number of workers
- ``-b option=VALUE``: Additional options

**Examples**:

.. code-block:: console

   # Legacy batch specification
   python3 -m canary run -b backend=slurm -b spec=duration=30m ./tests

   # Legacy with workers
   python3 -m canary run -b backend=slurm -b workers=4 ./tests

   # Legacy with options
   python3 -m canary run -b backend=slurm -b option=queue=debug ./tests

Command Integration
-------------------

The HPC commands integrate with Canary through several mechanisms:

**Command Rewriting**:

The ``canary_cmdline_modifyargs`` hook rewrites ``canary run --hpc-backend`` to ``canary hpc run``, providing backward compatibility while using the modern implementation.

**Option Normalization**:

Legacy ``-b`` options are normalized to modern batch specification format, ensuring consistent behavior across different invocation methods.

**Backend Selection**:

The ``--hpc-backend`` option can default from the ``CANARY_HPC_BACKEND`` environment variable, providing flexible backend configuration.

Command Examples
----------------

Basic HPC Execution
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Modern HPC command
   python3 -m canary hpc run --backend=slurm ./basic

   # Legacy HPC option
   python3 -m canary run --hpc-backend=slurm ./basic

Batch Specification
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Modern batch spec
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=30m ./basic

   # Legacy batch spec
   python3 -m canary run --hpc-backend=slurm -b spec=duration=30m ./basic

Scheduler Arguments
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Modern scheduler args
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./basic

   # Legacy scheduler args
   python3 -m canary run --hpc-backend=slurm -b option="-A myacct,-q debug" ./basic

Backend Information
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Show backend info
   python3 -m canary hpc info slurm

   # Show all backend info
   python3 -m canary hpc info pbs

Batch Monitoring
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Show batch log
   python3 -m canary hpc log abc123

   # Show all batch logs
   python3 -m canary hpc log

Command Selection Guide
-----------------------

**Use Modern Commands** when:

- Starting new HPC projects
- Preferring explicit command structure
- Needing full feature access
- Wanting better documentation

**Use Legacy Options** when:

- Maintaining existing scripts
- Needing backward compatibility
- Preferring concise syntax
- Working with legacy configurations

Both command styles provide the same functionality, with modern commands being the recommended approach for new development.

Command Best Practices
----------------------

1. **Backend Specification**: Always specify the backend explicitly
2. **Batch Configuration**: Use appropriate batch specification for workload
3. **Resource Management**: Configure resources in `hpc_connect`, not Canary
4. **Timeout Configuration**: Set appropriate queue and run timeouts
5. **Error Handling**: Monitor batch status and logs
6. **Debugging**: Use ``hpc log`` and workspace inspection
7. **Documentation**: Record command usage and configurations
