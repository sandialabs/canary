.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Distributed Execution Overview
===============================

The ``canary_dist`` extension is a **distributed execution backend** for Canary that enables running tests across a pool of remote machines. It provides commands and infrastructure for distributed resource management, batch execution, and remote job submission.

Extension Type
--------------

- **Distributed Execution Backend**: Manages execution across remote machines
- **Resource-Pool Adapter**: Translates between Canary's resource model and distributed server resources
- **Command Provider**: Adds ``canary dist`` subcommands for distributed operations

Key Features
------------

1. **Distributed Resource Pool**: Connects to a resource-pool server to discover and manage remote machines
2. **Batch Execution**: Groups tests into batches for efficient remote execution
3. **Remote Job Submission**: Submits test batches to remote machines using hpc_connect
4. **Resource Management**: Handles resource checkout/checkin with transaction tracking
5. **Environment Export**: Controls which environment variables are propagated to remote hosts
6. **Machine Selection**: Filters machines by tags and groups
7. **Status Monitoring**: Provides visibility into pool state and resource availability

Architecture
------------

The distributed execution system consists of several key components:

1. **Resource Pool Server**: External server that tracks available machines and their resources
2. **Distributed Resource Pool Adapter**: Client-side component that translates server state to Canary's resource model
3. **Distributed Pool Conductor**: Orchestrates batch creation and remote execution
4. **Distributed Pool Executor**: Handles local execution of distributed batches
5. **HPC Connect Backend**: Provides remote subprocess execution capabilities

Commands
--------

The extension provides three main commands:

- ``canary dist status``: Show the status of machines in the distributed pool
- ``canary dist run``: Run test cases across the distributed pool
- ``canary dist exec``: Execute a batch on a remote machine (internal use)

Basic Usage
-----------

To run tests across a distributed pool:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 ./tests

To check pool status:

.. code-block:: console

   python3 -m canary dist status --server-url http://pool.example:8000

Relationship to Canary
----------------------

The ``canary_dist`` extension builds on Canary's core functionality:

- Uses Canary's job selection and filtering mechanisms
- Integrates with Canary's resource management system
- Leverages Canary's batching and scheduling infrastructure
- Extends Canary's execution framework for remote operations

The extension does not replace Canary's local execution model but provides an additional execution mode for selected jobs.

The ``canary_dist`` extension uses `hpc-connect <https://github.com/sandialabs/hpc-connect>`_ for distributed execution across remote machines.