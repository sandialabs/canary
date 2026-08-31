.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging
=========

Debugging HPC execution issues requires understanding the complex interaction between Canary, the HPC extension, scheduler backends, and batch workspaces. This guide provides systematic approaches to diagnosing and resolving common HPC problems.

Debugging Approach
------------------

**Systematic Debugging Process**:

1. **Problem Identification**: Clearly define the issue
2. **Information Gathering**: Collect relevant diagnostic data
3. **Root Cause Analysis**: Identify underlying causes
4. **Solution Testing**: Verify proposed solutions
5. **Prevention Planning**: Implement preventive measures

Common Debugging Scenarios
--------------------------

Batch Submission Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Batch submission fails
- Jobs not submitted to scheduler
- Submission errors or timeouts

**Diagnosis Steps**:

1. Check backend availability
2. Verify backend configuration
3. Test batch formation
4. Review submission logs

**Debugging Commands**:

.. code-block:: console

   # Check backend detection
   python3 -m canary hpc info slurm

   # Test batch formation
   python3 -m canary hpc run --backend=slurm --verbose ./basic

   # Check submission logs
   python3 -m canary hpc log

Batch Execution Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Batch execution fails
- Jobs not running in batch
- Execution errors or crashes

**Diagnosis Steps**:

1. Inspect batch workspace
2. Check nested execution logs
3. Verify resource allocation
4. Review job requirements

**Debugging Commands**:

.. code-block:: console

   # Inspect batch workspace
   ls .canary/cache/canary-hpc/batches/abc1234/

   # Check nested execution output
   cat .canary/cache/canary-hpc/batches/abc1234/canary-out.txt

   # Review batch status
   python3 -m canary hpc log abc1234

Resource Allocation Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Insufficient resources
- Resource allocation failures
- Preflight validation errors

**Diagnosis Steps**:

1. Check HPC resource pool
2. Verify job resource requirements
3. Review backend resource configuration
4. Test with simpler resource requirements

**Debugging Commands**:

.. code-block:: console

   # Check HPC resource pool
   python3 -m canary config show resource-pool --backend=slurm

   # Test with minimal resources
   python3 -m canary hpc run --backend=slurm -p "cpus=1" ./basic

   # Verify resource requirements
   python3 -m canary show --resources ./tests

Timeout Issues
~~~~~~~~~~~~~~~~

**Symptoms**:

- Queue timeout exceeded
- Run timeout exceeded
- Job cancellation due to timeout

**Diagnosis Steps**:

1. Review timeout configuration
2. Check queue wait times
3. Monitor execution duration
4. Adjust timeout settings

**Debugging Commands**:

.. code-block:: console

   # Test with shorter timeouts
   python3 -m canary hpc run --backend=slurm --timeout queue=5m,run=10m ./basic

   # Monitor timeout behavior
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h --verbose ./basic

Status and Failure Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Incorrect batch status
- Job failures not reflected
- Status propagation issues

**Diagnosis Steps**:

1. Check batch status logs
2. Inspect job status in workspace
3. Verify status aggregation
4. Review failure handling

**Debugging Commands**:

.. code-block:: console

   # Check batch status
   python3 -m canary hpc log abc1234

   # Inspect job status
   cat .canary/cache/canary-hpc/batches/abc1234/batch.lock | jq .status

   # Review status aggregation
   python3 -m canary hpc run --backend=slurm --verbose ./basic

Debugging Tools
---------------

Verbose Logging
~~~~~~~~~~~~~~~~~~

**Enable verbose logging**:

.. code-block:: console

   # Verbose HPC execution
   python3 -m canary hpc run --backend=slurm --verbose ./basic

   # Verbose batch execution
   python3 -m canary hpc exec --batch-id=abc1234 --verbose

   # Verbose status checking
   python3 -m canary hpc log --verbose

Log Analysis
~~~~~~~~~~~~~~~~

**Analyze logs**:

.. code-block:: console

   # Check Canary logs
   tail -f ~/.canary/logs/hpc.log

   # Filter HPC messages
   grep -i "hpc\|batch\|scheduler" ~/.canary/logs/canary.log

   # Review batch logs
   python3 -m canary hpc log abc1234

Workspace Inspection
~~~~~~~~~~~~~~~~~~~~~~~~

**Inspect batch workspaces**:

.. code-block:: console

   # List batch workspaces
   ls .canary/cache/canary-hpc/batches/

   # Inspect specific workspace
   tree .canary/cache/canary-hpc/batches/abc1234/

   # Read batch metadata
   cat .canary/cache/canary-hpc/batches/abc1234/batch.lock | jq .

   # Check resource pool
   cat .canary/cache/canary-hpc/batches/abc1234/resource_pool.json | jq .

Backend Testing
~~~~~~~~~~~~~~~~~~

**Test backend functionality**:

.. code-block:: console

   # Check backend availability
   python3 -m canary hpc info slurm

   # Test backend configuration
   python3 -c "import hpc_connect; print(hpc_connect.get_backend('slurm'))"

   # Verify backend resources
   python3 -m canary config show resource-pool --backend=slurm

Debugging Workflow
------------------

Step-by-Step Debugging
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Identify Issue**: Clearly define the problem
2. **Gather Information**: Collect logs, status, configuration
3. **Isolate Problem**: Narrow down to specific component
4. **Test Hypotheses**: Verify potential causes
5. **Implement Fix**: Apply solution
6. **Verify Resolution**: Confirm issue resolved
7. **Document Findings**: Record solution

Debugging Checklist
~~~~~~~~~~~~~~~~~~~

- [ ] Verify backend availability and configuration
- [ ] Check HPC resource pool population
- [ ] Review batch formation and specification
- [ ] Inspect batch workspace contents
- [ ] Test nested execution behavior
- [ ] Validate resource allocation
- [ ] Monitor timeout behavior
- [ ] Review status aggregation
- [ ] Test with verbose logging
- [ ] Analyze log files
- [ ] Check backend compatibility
- [ ] Verify scheduler integration
- [ ] Test with simpler configurations

Debugging Examples
------------------

Slurm Debugging
~~~~~~~~~~~~~~~

.. code-block:: console

   # Check Slurm backend
   python3 -m canary hpc info slurm

   # Test Slurm submission
   python3 -m canary hpc run --backend=slurm --verbose ./basic

   # Inspect Slurm batch
   ls .canary/cache/canary-hpc/batches/abc1234/

   # Check Slurm logs
   python3 -m canary hpc log abc1234

PBS Debugging
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check PBS backend
   python3 -m canary hpc info pbs

   # Test PBS submission
   python3 -m canary hpc run --backend=pbs --verbose ./basic

   # Review PBS configuration
   python3 -m canary config show resource-pool --backend=pbs

Shell Debugging
~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Test shell backend
   python3 -m canary hpc run --backend=shell --verbose ./basic

   # Simple shell execution
   python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic

   # Inspect shell workspace
   cat .canary/cache/canary-hpc/batches/abc1234/canary-out.txt

Advanced Debugging Techniques
------------------------------

Manual Workspace Inspection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Find batch workspaces
   find .canary/cache/canary-hpc/batches/ -type d

   # Check workspace structure
   tree .canary/cache/canary-hpc/batches/abc1234/

   # Read batch lock file
   jq . .canary/cache/canary-hpc/batches/abc1234/batch.lock

   # Review resource pool
   jq . .canary/cache/canary-hpc/batches/abc1234/resource_pool.json

Configuration Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Test different batch specifications
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat ./basic
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any ./basic

   # Test resource requirements
   python3 -m canary hpc run --backend=slurm -p "nodes=1,cpus=1" ./basic
   python3 -m canary hpc run --backend=slurm -p "nodes=2,cpus=8" ./basic

Environment Variable Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Test environment variables
   export CANARY_HPC_BACKEND=slurm
   python3 -m canary hpc run ./basic

   # Test scheduler arguments
   export CANARY_HPC_SUBMIT_ARGS="-A myacct,-q debug"
   python3 -m canary hpc run --backend=slurm ./basic

Debugging Best Practices
------------------------

1. **Start Simple**: Test with minimal configuration
2. **Isolate Components**: Test backend, batching, execution separately
3. **Use Verbose Logging**: Enable verbose mode for detailed information
4. **Inspect Workspaces**: Regularly check batch workspace contents
5. **Validate Configuration**: Test configuration before production use
6. **Monitor Performance**: Track execution times and resource usage
7. **Document Solutions**: Record debugging findings and solutions
8. **Test Incrementally**: Gradually increase complexity

Debugging Limitations
---------------------

1. **Complexity**: HPC execution involves multiple components
2. **Backend Dependency**: Debugging requires backend availability
3. **Scheduler Variability**: Behavior depends on scheduler state
4. **Resource Constraints**: Limited by available resources
5. **Timeout Risks**: Debugging may be interrupted by timeouts
6. **Permission Issues**: May require scheduler access
7. **Environment Differences**: Behavior may vary across environments

Debugging Resources
-------------------

- Canary HPC extension documentation
- Backend-specific documentation (Slurm, PBS, Flux)
- Canary core documentation
- hpc_connect documentation
- Community forums and support channels
- Scheduler administrator guides