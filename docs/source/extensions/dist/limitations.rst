.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

The ``canary_dist`` extension has several important limitations that users should be aware of when planning distributed test execution strategies.

Architectural Limitations
-------------------------

Single-Node Constraint
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Distributed execution only supports single-node jobs

**Impact**:

- Multi-node jobs are automatically excluded
- ``allow_multinode = False`` in resource pool
- No support for distributed multi-node workloads
- Jobs requiring multiple nodes cannot use distributed execution

**Workaround**:

- Redesign multi-node jobs as single-node jobs
- Use local execution for multi-node workloads
- Consider alternative execution strategies

Resource Management Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Resource management has several constraints

**Impact**:

- No dynamic resource adjustment during execution
- No resource overcommitment support
- Limited multi-resource type coordination
- No resource priority or preemption
- Basic resource type support only

**Workaround**:

- Design tests for fixed resource requirements
- Use appropriate batch sizing
- Monitor resource utilization carefully
- Plan resource allocation in advance

Batching Limitations
~~~~~~~~~~~~~~~~~~~~

**Limitation**: Batching algorithm has constraints

**Impact**:

- Complex dependency graphs may limit efficiency
- Circular dependencies can prevent batch formation
- Batch count and duration are mutually exclusive
- Exact estimation slower for very large suites

**Workaround**:

- Simplify complex dependency structures
- Use smaller batches for dependency-heavy workloads
- Choose appropriate batching parameters
- Balance accuracy and performance needs

Environment Export Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Environment export has several constraints

**Impact**:

- No automatic environment detection
- Limited module system support
- No environment validation
- Platform-specific behavior differences
- No environment variable transformation

**Workaround**:

- Explicitly specify required environment variables
- Test environment compatibility across platforms
- Use explicit values for critical variables
- Document environment requirements

Remote Execution Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Remote execution has constraints

**Impact**:

- Remote execution environment may differ
- No access to full distributed pool during execution
- Results must be transferred back to submission host
- Remote host must have Canary installed

**Workaround**:

- Ensure consistent environments across hosts
- Test remote execution capabilities
- Monitor result transfer performance
- Verify Canary installation on all hosts

Server Dependency Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Dependence on external resource pool server

**Impact**:

- Server availability affects distributed execution
- Server version compatibility requirements
- Server configuration constraints
- Limited control over server behavior

**Workaround**:

- Monitor server health and availability
- Test server compatibility
- Work with server administrators
- Have fallback execution strategies

Performance Limitations
-----------------------

Network Overhead
~~~~~~~~~~~~~~~~

**Limitation**: Network communication adds overhead

**Impact**:

- Network latency affects execution time
- Result transfer consumes bandwidth
- Remote process startup has cost
- Server communication adds latency

**Workaround**:

- Optimize batch size to reduce remote invocations
- Use appropriate network configurations
- Monitor network performance
- Consider local execution for small workloads

Resource Utilization
~~~~~~~~~~~~~~~~~~~~

**Limitation**: Resource utilization has constraints

**Impact**:

- Batch size affects resource utilization
- Resource fragmentation can occur
- Load balancing may be uneven
- Resource contention possible

**Workaround**:

- Monitor resource utilization patterns
- Adjust batch parameters for optimal utilization
- Balance batch count with available machines
- Consider resource diversity across pool

Scalability Limitations
~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Scalability has practical limits

**Impact**:

- Large pools may have management overhead
- Many small batches increase overhead
- Complex dependencies limit parallelism
- Server capacity may be limiting factor

**Workaround**:

- Design appropriate pool sizes
- Optimize batch configuration
- Simplify dependency structures
- Monitor server performance

Reliability Limitations
-----------------------

Error Handling
~~~~~~~~~~~~~~

**Limitation**: Error handling has constraints

**Impact**:

- Limited automatic recovery from failures
- Error propagation across distributed components
- Complex failure modes possible
- Limited transaction rollback capabilities

**Workaround**:

- Implement robust error handling in tests
- Monitor execution progress
- Have manual recovery procedures
- Test failure scenarios

Fault Tolerance
~~~~~~~~~~~~~~~

**Limitation**: Limited fault tolerance capabilities

**Impact**:

- No automatic retry for failed batches
- Limited resource recovery from failures
- No automatic failover to other machines
- Limited handling of partial failures

**Workaround**:

- Design tests to handle failures gracefully
- Implement manual retry procedures
- Monitor for partial failures
- Have backup execution strategies

Compatibility Limitations
-------------------------

Platform Compatibility
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Platform compatibility constraints

**Impact**:

- Environment variables may behave differently
- Module systems may have limitations
- Remote execution environment differences
- Platform-specific resource behaviors

**Workaround**:

- Test across target platforms
- Use platform-independent constructs
- Document platform requirements
- Consider platform-specific configurations

Version Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Version compatibility requirements

**Impact**:

- Canary version compatibility across hosts
- Server version compatibility
- hpc_connect version compatibility
- Dependency version constraints

**Workaround**:

- Maintain consistent versions across environment
- Test version compatibility
- Document version requirements
- Plan for version upgrades

Feature Limitations
-------------------

Missing Features
~~~~~~~~~~~~~~~~

**Limitation**: Some advanced features are not implemented

**Impact**:

- No resource priority or preemption
- Limited multi-resource coordination
- No advanced scheduling features
- Basic monitoring capabilities only

**Workaround**:

- Use available features effectively
- Implement workarounds where possible
- Consider alternative approaches
- Provide feedback for future enhancements

Documentation Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Documentation has constraints

**Impact**:

- Limited advanced usage examples
- Basic troubleshooting guidance only
- No comprehensive performance tuning guide
- Limited architectural deep dives

**Workaround**:

- Experiment with different configurations
- Share findings with community
- Provide feedback for documentation improvements
- Consult source code for advanced details

Usage Limitations
-----------------

Configuration Complexity
~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Configuration can be complex

**Impact**:

- Multiple configuration parameters
- Complex interactions between options
- Environment variable management
- Server configuration requirements

**Workaround**:

- Start with simple configurations
- Gradually increase complexity
- Document working configurations
- Use configuration management tools

Learning Curve
~~~~~~~~~~~~~~

**Limitation**: Distributed execution has learning curve

**Impact**:

- Complex distributed system concepts
- Multiple components to understand
- Advanced configuration options
- Debugging distributed issues

**Workaround**:

- Start with basic usage
- Review documentation thoroughly
- Experiment with different scenarios
- Seek community support when needed

Operational Limitations
-----------------------

Monitoring Limitations
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Monitoring capabilities are basic

**Impact**:

- No comprehensive monitoring dashboard
- Limited historical data
- Basic status information only
- No alerting capabilities

**Workaround**:

- Implement custom monitoring solutions
- Use external monitoring tools
- Develop status tracking scripts
- Monitor key metrics manually

Management Limitations
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Management features are limited

**Impact**:

- No centralized management interface
- Limited pool management capabilities
- Basic administrative features only
- No user management capabilities

**Workaround**:

- Use available management tools
- Develop custom management scripts
- Work with server administrators
- Implement manual management procedures

Security Limitations
--------------------

Security Considerations
~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Security features have constraints

**Impact**:

- Limited authentication options
- Basic authorization capabilities
- No comprehensive audit logging
- Limited security configuration

**Workaround**:

- Use available security features
- Implement network-level security
- Follow security best practices
- Work with security teams

Future Enhancements
-------------------

Potential future improvements to address limitations:

- Multi-node distributed execution support
- Advanced resource management features
- Enhanced batching algorithms
- Improved environment export capabilities
- Better error handling and recovery
- Enhanced monitoring and management
- Advanced scheduling features
- Comprehensive documentation
- Improved compatibility and portability

Working Within Limitations
--------------------------

To work effectively within these limitations:

1. **Understand Constraints**: Be aware of all limitations
2. **Plan Accordingly**: Design tests and workflows appropriately
3. **Use Workarounds**: Implement effective workarounds
4. **Monitor Performance**: Track execution and resource utilization
5. **Provide Feedback**: Share experiences and suggestions
6. **Stay Informed**: Keep up with new features and improvements

Limitations Summary
-------------------

The ``canary_dist`` extension provides powerful distributed execution capabilities but has important limitations that require careful consideration in test design and execution planning. Understanding these limitations helps users make informed decisions about when and how to use distributed execution effectively.