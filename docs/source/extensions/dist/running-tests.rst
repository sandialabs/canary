.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Running Tests with Distributed Execution
==========================================

The ``canary dist run`` command enables running Canary tests across a distributed pool of machines. This command integrates with Canary's test selection and execution framework while adding distributed-specific functionality.

Basic Usage
-----------

To run tests across a distributed pool:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 ./tests

This command:

1. Connects to the specified resource pool server
2. Discovers available machines and resources
3. Selects and filters test jobs
4. Creates batches based on resource requirements
5. Submits batches to remote machines
6. Collects and reports results

Command Line Options
--------------------

Server Configuration
~~~~~~~~~~~~~~~~~~~~

- ``--server-url URL``: Distributed pool server location
- ``CANARY_DIST_SERVER_URL`` environment variable can also be used

Machine Selection
~~~~~~~~~~~~~~~~~

- ``--tags TAGS``: Only run on machines matching all specified tags (comma-separated)

Batch Configuration
~~~~~~~~~~~~~~~~~~~~~~

- ``--batch-width N``: Width of job batches in CPUs (default: 8)
- ``--batch-count N``: Number of job batches (auto by default)
- ``--batch-duration T``: Approximate batch duration (default: 10m)
- ``--batch-exact-estimate``: Use exact scheduling estimates for batch formation

Environment Export
~~~~~~~~~~~~~~~~~~

- ``-E, --export <variables>|ALL``: Control environment variable propagation

Standard Canary Options
~~~~~~~~~~~~~~~~~~~~~~~

All standard Canary test selection and execution options are supported:

- Test selection: ``-k``, ``--owner``, ``-p``, ``--regex``, ``--tag``
- Execution control: ``--workers``, ``--timeout``, ``--fail-fast``
- Output control: ``--style``, ``--view``

Examples
--------

Basic Distributed Run
~~~~~~~~~~~~~~~~~~~~~

Run all tests in the ``./tests`` directory across the distributed pool:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 ./tests

Selective Machine Usage
~~~~~~~~~~~~~~~~~~~~~~~

Run tests only on machines with specific tags:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --tags gpu,fast ./tests

Batch Width Control
~~~~~~~~~~~~~~~~~~~

Control the CPU width of each batch:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 16 ./tests

Batch Count Control
~~~~~~~~~~~~~~~~~~~

Specify the exact number of batches to create:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-count 4 ./tests

Batch Duration Control
~~~~~~~~~~~~~~~~~~~~~~

Control batch duration (supports Go duration format):

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-duration 15m ./tests
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-duration 1h ./tests

Environment Variable Export
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Export specific environment variables to remote hosts:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=MYVAR,OTHER=value ./tests

Export all environment variables:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=ALL ./tests

Combined Options
~~~~~~~~~~~~~~~~

Combine multiple options for complex scenarios:

.. code-block:: console

   python3 -m canary dist run \
     --server-url http://pool.example:8000 \
     --tags gpu \
     --batch-width 8 \
     --batch-duration 30m \
     --export=MYVAR,LOADEDMODULES \
     --workers 4 \
     -k "fast and not broken" \
     ./tests

Test Selection
--------------

The distributed run command supports all standard Canary test selection mechanisms:

Keyword Selection
~~~~~~~~~~~~~~~~~

Use ``-k`` to select tests by keyword expression:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 -k "fast and not broken" ./tests

Owner Selection
~~~~~~~~~~~~~~~

Use ``--owner`` to select tests by owner:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --owner alice,bob ./tests

Parameter Selection
~~~~~~~~~~~~~~~~~~~

Use ``-p`` to select tests by parameter:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 -p "cpus>=8" ./tests

Regex Selection
~~~~~~~~~~~~~~~

Use ``--regex`` to select tests by regular expression:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --regex "test_.*" ./tests

Tag Selection
~~~~~~~~~~~~~

Use ``--tag`` to select tests by tag:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --tag nightly ./tests

Execution Control
-----------------

Worker Control
~~~~~~~~~~~~~~

Control the number of concurrent workers:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --workers 8 ./tests

Timeout Control
~~~~~~~~~~~~~~~

Set timeouts for different test types:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --timeout fast=2,long=30 ./tests

Fail-Fast Mode
~~~~~~~~~~~~~~

Stop after the first failure:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --fail-fast ./tests

Output Control
--------------

Console Style
~~~~~~~~~~~~~

Control console output style:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --style live=yes,name=long ./tests

View Configuration
~~~~~~~~~~~~~~~~~~

Configure result view creation:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --view mode=hardlink,only=failed ./tests

Job Selection Constraints
-------------------------

The distributed execution enforces several constraints on job selection:

Single-Node Constraint
~~~~~~~~~~~~~~~~~~~~~~

Multi-node jobs are automatically masked and excluded:

.. code-block:: console

   # This job would be excluded:
   # nodes: 2
   # cpus: 16

   # Only single-node jobs are eligible:
   # nodes: 1
   # cpus: 8

CPU Constraint
~~~~~~~~~~~~~~

Jobs requiring more CPUs than the batch width are masked:

.. code-block:: console

   # With --batch-width 8, this would be excluded:
   # cpus: 16

Resource Constraint
~~~~~~~~~~~~~~~~~~~

Jobs must fit within the resources available on a single machine in the pool.

Execution Process
-----------------

The distributed run process follows these steps:

1. **Server Connection**: Connect to resource pool server
2. **Resource Discovery**: Query server for available machines and resources
3. **Job Collection**: Collect and filter test jobs
4. **Job Selection**: Apply selection criteria and constraints
5. **Batch Formation**: Group jobs into batches
6. **Resource Checkout**: Reserve resources for each batch
7. **Batch Submission**: Submit batches to remote machines
8. **Remote Execution**: Run tests on remote machines
9. **Result Collection**: Gather results from remote execution
10. **Resource Checkin**: Release resources back to pool
11. **Result Reporting**: Report final results

Batch Formation Details
-----------------------

The batch formation process considers:

- Resource requirements of each job
- Batch width (CPU count)
- Batch count or duration limits
- Job dependencies and ordering constraints
- Resource availability across machines

Error Handling
--------------

The distributed run command handles various error conditions:

- **Server Unavailable**: Connection errors and timeouts
- **Insufficient Resources**: Not enough machines or resources available
- **Batch Formation Failure**: Unable to create valid batches
- **Remote Execution Failure**: Issues on remote machines
- **Resource Checkout Failure**: Unable to reserve resources
- **Result Collection Failure**: Issues gathering results from remote execution

Diagnostic Information
----------------------

When errors occur, the command provides diagnostic information including:

- Server connection details
- Resource availability information
- Batch formation details
- Remote execution logs
- Resource checkout/checkin status

This information helps users troubleshoot and resolve issues with distributed execution.