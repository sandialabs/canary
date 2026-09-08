.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

The ``canary_hpc`` extension provides powerful HPC scheduling capabilities but has several important limitations that users should understand when planning and executing HPC test workloads.

Architectural Limitations
-------------------------

hpc_connect Dependency
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: HPC extension depends on ``hpc_connect`` external package

**Impact**:

- Requires ``hpc_connect`` installation and configuration
- Backend availability depends on ``hpc_connect`` support
- Scheduler-specific behavior delegated to ``hpc_connect``
- No control over ``hpc_connect`` implementation

**Workaround**:

- Install and configure ``hpc_connect`` properly
- Use supported backends (Slurm, PBS, Flux, shell)
- Document backend requirements
- Test backend availability before execution

Resource Pool Override Rejection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Canary resource pool overrides rejected in HPC mode

**Impact**:

- ``-r`` / resource pool modifiers rejected
- ``--resource-pool-file`` rejected
- ``--oversubscribe`` rejected
- Local resource configuration not available

**Workaround**:

- Configure resources through ``hpc_connect`` backend
- Use backend-specific resource configuration
- Document resource configuration requirements
- Test resource allocation before execution

Backend-Specific Behavior
~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Behavior depends on ``hpc_connect`` backend capabilities

**Impact**:

- Different behavior across backends
- Backend-specific constraints and limitations
- Scheduler policy variations
- Resource allocation differences

**Workaround**:

- Test with specific backend before production
- Document backend-specific behavior
- Understand scheduler policies
- Configure for target backend

Execution Model Complexity
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: HPC execution more complex than local execution

**Impact**:

- Multiple execution phases
- Nested execution model
- Batch workspace management
- Status propagation complexity

**Workaround**:

- Start with simple HPC configurations
- Gradually increase complexity
- Use verbose logging for debugging
- Document execution flow

Batching Limitations
--------------------

Batch Specification Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Not all batch specification combinations are valid

**Impact**:

- ``layout=atomic`` requires ``nodes=any``
- ``count=auto`` no longer supported
- Duration-targeted atomic batching unsupported
- Invalid combinations cause errors

**Workaround**:

- Use valid batch specification combinations
- Test batch specifications before execution
- Document valid combinations
- Use ``hpc help --spec`` for guidance

Layout Constraints
~~~~~~~~~~~~~~~~~~

**Limitation**: Layout options have specific constraints

**Impact**:

- Flat layout: Flexible but no intra-batch dependencies
- Atomic layout: Preserves dependencies but requires ``nodes=any``
- Layout selection affects batching efficiency

**Workaround**:

- Choose layout based on job dependencies
- Test layout behavior with verbose logging
- Document layout decisions
- Monitor layout performance

Count Targeting Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Count targeting has constraints

**Impact**:

- ``count=N`` subject to DAG and resource constraints
- ``count=max`` may create many small batches
- Count targeting affects resource utilization

**Workaround**:

- Use appropriate count for workload
- Test count targeting with different values
- Monitor batch formation
- Adjust based on performance

Duration Targeting Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Duration targeting uses estimates

**Impact**:

- Cheap makespan estimates may be inaccurate
- Actual runtime may differ from estimates
- Duration targeting affects batch composition

**Workaround**:

- Use realistic duration estimates
- Test duration targeting with workload
- Monitor actual runtime vs estimates
- Adjust duration as needed

Resource Management Limitations
-------------------------------

Resource Allocation Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Resource allocation constrained by backend

**Impact**:

- Limited by backend resource availability
- Resource preflight validation required
- Resource allocation may fail
- Backend constraints affect allocation

**Workaround**:

- Check backend resource availability
- Test resource requirements before execution
- Use realistic resource requests
- Monitor resource allocation

Preflight Validation Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Preflight validation has constraints

**Impact**:

- Validates before submission but not during execution
- May not catch all resource issues
- Validation errors mark jobs ``BROKEN``

**Workaround**:

- Test resource requirements thoroughly
- Monitor execution for resource issues
- Review preflight validation logs
- Document validation behavior

GPU Resource Limitations
~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: GPU resources have specific handling

**Impact**:

- GPU resources get vendor property ``UNKNOWN``
- Vendor-agnostic GPU handling
- Vendor extensions needed for specific GPU support

**Workaround**:

- Use vendor extensions for GPU-specific needs
- Document GPU resource handling
- Test GPU allocation with verbose logging
- Configure GPU resources in backend

Timeout Limitations
-------------------

Queue Timeout Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Queue timeout depends on scheduler state

**Impact**:

- Queue wait times may vary
- Timeout may occur before job starts
- Scheduler load affects queue time

**Workaround**:

- Set realistic queue timeouts
- Monitor queue wait times
- Adjust based on scheduler load
- Document queue timeout behavior

Run Timeout Constraints
~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Run timeout depends on job execution

**Impact**:

- Execution times may vary
- Timeout may occur during execution
- Job complexity affects runtime

**Workaround**:

- Set realistic run timeouts
- Monitor execution duration
- Adjust based on job complexity
- Document run timeout behavior

Total Timeout Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Total timeout enforces maximum duration

**Impact**:

- Maximum job duration enforced
- Timeout may interrupt execution
- Includes both queue and run time

**Workaround**:

- Set appropriate total timeouts
- Monitor overall job duration
- Adjust based on workload
- Document total timeout behavior

Status and Failure Limitations
------------------------------

Status Aggregation Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Status aggregation has complexity

**Impact**:

- Batch status derived from child jobs
- Status propagation may be delayed
- Complex failure scenarios possible

**Workaround**:

- Monitor batch status regularly
- Check individual job status
- Review status aggregation logs
- Document status behavior

Failure Handling Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Failure handling has constraints

**Impact**:

- Incomplete jobs marked ``BROKEN``
- Failure reasons may be limited
- Complex failure scenarios difficult to diagnose

**Workaround**:

- Use verbose logging for failure diagnosis
- Inspect batch workspaces for failures
- Review failure handling documentation
- Test failure scenarios

Nested Execution Limitations
----------------------------

Nested Execution Complexity
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Nested execution adds complexity

**Impact**:

- Debugging more complex than local execution
- Workspace management required
- Configuration must match batch requirements

**Workaround**:

- Inspect batch workspaces regularly
- Use verbose logging for nested execution
- Test nested execution with simple batches
- Document nested execution behavior

Workspace Management Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Batch workspace management has constraints

**Impact**:

- Workspace retention policy needed
- Manual cleanup may be required
- Workspace size may grow large

**Workaround**:

- Configure appropriate retention policies
- Monitor workspace usage
- Clean up old workspaces regularly
- Document workspace management

Debugging Limitations
---------------------

Debugging Complexity
~~~~~~~~~~~~~~~~~~~~

**Limitation**: HPC debugging more complex than local

**Impact**:

- Multiple components to debug
- Backend-specific issues
- Scheduler interaction complexity

**Workaround**:

- Use systematic debugging approach
- Start with simple configurations
- Use verbose logging
- Document debugging findings

Environment Variability
~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Environment variability affects debugging

**Impact**:

- Behavior may vary across environments
- Scheduler state affects execution
- Resource availability may change

**Workaround**:

- Test in target environment
- Document environment requirements
- Monitor environment changes
- Use consistent testing environments

Performance Limitations
-----------------------

Batching Overhead
~~~~~~~~~~~~~~~~~

**Limitation**: Batch formation adds overhead

**Impact**:

- Batch formation time
- Submission overhead
- Resource allocation time

**Workaround**:

- Optimize batch size
- Monitor batch formation time
- Adjust batching parameters
- Document performance characteristics

Resource Utilization
~~~~~~~~~~~~~~~~~~~~

**Limitation**: Resource utilization affected by batching

**Impact**:

- Batch size affects utilization
- Resource fragmentation possible
- Load balancing challenges

**Workaround**:

- Monitor resource utilization
- Optimize batch parameters
- Adjust based on workload
- Document utilization patterns

Scalability Limitations
-----------------------

Large-Scale Execution
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Large-scale execution has challenges

**Impact**:

- Scheduler limits may be reached
- Resource contention possible
- Performance degradation at scale

**Workaround**:

- Test at scale before production
- Monitor scheduler limits
- Optimize resource usage
- Document scalability constraints

Complex Workloads
~~~~~~~~~~~~~~~~~

**Limitation**: Complex workloads may have issues

**Impact**:

- Complex dependencies difficult to batch
- Resource-intensive jobs may fail
- Mixed workloads challenging

**Workaround**:

- Simplify complex dependencies
- Test resource-intensive jobs
- Document workload constraints
- Monitor complex workload execution

Compatibility Limitations
-------------------------

Backend Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Backend compatibility varies

**Impact**:

- Not all backends support all features
- Backend version differences
- Scheduler policy variations

**Workaround**:

- Test with target backend
- Document backend requirements
- Monitor backend compatibility
- Update backend configurations

Version Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Version compatibility requirements

**Impact**:

- Canary version compatibility
- hpc_connect version compatibility
- Backend version compatibility

**Workaround**:

- Maintain consistent versions
- Test version compatibility
- Document version requirements
- Plan for version upgrades

Working Within Limitations
--------------------------

To work effectively within these limitations:

1. **Understand Constraints**: Be aware of all limitations
2. **Plan Accordingly**: Design tests and workflows appropriately
3. **Test Thoroughly**: Validate behavior in target environment
4. **Monitor Performance**: Track execution and resource utilization
5. **Document Solutions**: Record successful approaches and workarounds
6. **Provide Feedback**: Share experiences and suggestions for improvement
7. **Stay Informed**: Keep up with new features and changes

Limitations Summary
-------------------

The ``canary_hpc`` extension provides essential HPC scheduling capabilities but has important limitations that require careful consideration in test design and execution planning. Understanding these limitations helps users make informed decisions about when and how to use HPC execution effectively.
