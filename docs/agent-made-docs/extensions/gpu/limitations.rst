.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

The GPU vendor extensions have several important limitations that users should be aware of when working with GPU resources in Canary.

Architectural Limitations
-------------------------

Tool Dependency
~~~~~~~~~~~~~~~

**Limitation**: GPU extensions depend on vendor-specific command-line tools

**Impact**:

- Requires ``nvidia-smi`` for NVIDIA support
- Requires ``amd-smi`` or ``rocm-smi`` for AMD support
- Extensions fail silently if tools are not available
- No fallback to alternative discovery methods

**Workaround**:

- Install required vendor tools
- Ensure tools are in system PATH
- Use manual resource definition when tools unavailable
- Document tool requirements for users

Local Node Only
~~~~~~~~~~~~~~~

**Limitation**: GPU discovery only works for local node

**Impact**:

- Does not discover GPUs on remote nodes
- Multi-node systems require manual resource definition
- HPC environments may need custom resource pool configuration
- ``canary_fill_gpu`` only populates first node

**Workaround**:

- Use manual resource definition for remote nodes
- Configure resource pool for multi-node environments
- Use HPC scheduler integration for remote GPU discovery

Format Sensitivity
~~~~~~~~~~~~~~~~~~

**Limitation**: Parsing depends on specific tool output formats

**Impact**:

- Tool version changes may break parsing
- Unexpected output formats cause failures
- No validation of tool output structure
- Parsing errors result in no GPU resources

**Workaround**:

- Test with specific tool versions
- Update parsing logic for new formats
- Use manual resource definition for problematic formats
- Document supported tool versions

Resource Management Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Basic resource management capabilities

**Impact**:

- No dynamic GPU resource adjustment
- No GPU resource overcommitment
- Limited multi-resource coordination
- No GPU resource priority or preemption
- Basic resource type support only

**Workaround**:

- Design tests for fixed resource requirements
- Use appropriate resource allocation
- Monitor resource utilization
- Plan resource allocation in advance

Environment Configuration Limitations
--------------------------------------

User Override Priority
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: User-set environment variables always take precedence

**Impact**:

- Extensions cannot override user configurations
- May prevent automatic environment setup
- User errors in environment variables persist
- No validation of user-set variables

**Workaround**:

- Document environment variable behavior
- Provide guidance on proper variable usage
- Test with clean environment when debugging
- Use explicit variable configuration

Vendor Compatibility Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Strict vendor compatibility requirements

**Impact**:

- NVIDIA: Only accepts NVIDIA, UNKNOWN, or empty vendor values
- AMD: Only accepts AMD or ROCM vendor values
- Mixed vendor systems require careful configuration
- UNKNOWN devices fall through to NVIDIA only

**Workaround**:

- Set correct vendor properties in resource pool
- Use explicit vendor specification in job requirements
- Test vendor compatibility in mixed environments
- Document vendor property requirements

Multi-Node Limitations
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Limited multi-node GPU support

**Impact**:

- Local GPU ID deduplication only
- No global GPU ID coordination
- Multi-node allocations may have duplicate local IDs
- No cross-node GPU resource management

**Workaround**:

- Use manual resource definition for multi-node
- Configure unique local IDs across nodes
- Document multi-node GPU behavior
- Test multi-node scenarios thoroughly

Performance Limitations
-----------------------

Discovery Overhead
~~~~~~~~~~~~~~~~~~

**Limitation**: GPU discovery adds configuration overhead

**Impact**:

- Tool execution adds startup time
- Parsing adds configuration overhead
- Multiple tool executions increase overhead
- Discovery runs on every Canary invocation

**Workaround**:

- Cache discovery results where possible
- Use manual resource definition for static environments
- Minimize tool executions
- Optimize parsing logic

Resource Utilization
~~~~~~~~~~~~~~~~~~~~

**Limitation**: Basic resource utilization tracking

**Impact**:

- No GPU utilization monitoring
- No performance metrics collection
- Limited resource usage tracking
- No historical utilization data

**Workaround**:

- Use external monitoring tools
- Implement custom utilization tracking
- Monitor GPU usage separately
- Document resource utilization patterns

Compatibility Limitations
-------------------------

Platform Compatibility
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Platform-specific behavior differences

**Impact**:

- Tool availability varies by platform
- Tool output format may differ
- Permission requirements vary
- Environment variable behavior differs

**Workaround**:

- Test across target platforms
- Document platform requirements
- Use platform-independent constructs
- Provide platform-specific guidance

Version Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Version-specific tool requirements

**Impact**:

- Tool version changes may break compatibility
- New tool versions may have different output
- Old tool versions may lack features
- Version mismatches cause issues

**Workaround**:

- Document supported tool versions
- Test with multiple tool versions
- Update parsing for new versions
- Provide version compatibility guidance

Feature Limitations
-------------------

Missing Features
~~~~~~~~~~~~~~~~

**Limitation**: Some advanced features not implemented

**Impact**:

- No GPU health monitoring
- No GPU temperature monitoring
- No GPU power management
- No advanced scheduling features
- Basic error handling only

**Workaround**:

- Use external tools for advanced features
- Implement custom monitoring
- Document feature limitations
- Provide feedback for future enhancements

Error Handling Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Basic error handling capabilities

**Impact**:

- Limited automatic error recovery
- Silent failure modes
- Basic error reporting
- No comprehensive error validation

**Workaround**:

- Implement robust error handling in tests
- Monitor for error conditions
- Document error handling behavior
- Test error scenarios thoroughly

Usage Limitations
-----------------

Configuration Complexity
~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Configuration can be complex

**Impact**:

- Multiple configuration parameters
- Complex vendor interactions
- Environment variable management
- Resource pool configuration

**Workaround**:

- Start with simple configurations
- Gradually increase complexity
- Document working configurations
- Use configuration management tools

Learning Curve
~~~~~~~~~~~~~~

**Limitation**: GPU support has learning curve

**Impact**:

- Complex GPU system concepts
- Multiple components to understand
- Vendor-specific behaviors
- Debugging challenges

**Workaround**:

- Start with basic usage
- Review documentation thoroughly
- Experiment with different scenarios
- Seek community support when needed

Operational Limitations
-----------------------

Monitoring Limitations
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Basic monitoring capabilities

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

**Limitation**: Limited management features

**Impact**:

- No centralized management interface
- Limited pool management capabilities
- Basic administrative features only
- No user management capabilities

**Workaround**:

- Use available management tools
- Develop custom management scripts
- Document management procedures
- Implement manual management processes

Security Limitations
--------------------

Security Considerations
~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Basic security features

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

Working Within Limitations
--------------------------

To work effectively within these limitations:

1. **Understand Constraints**: Be aware of all limitations
2. **Plan Accordingly**: Design tests and workflows appropriately
3. **Use Workarounds**: Implement effective workarounds
4. **Monitor Performance**: Track execution and resource utilization
5. **Provide Feedback**: Share experiences and suggestions
6. **Stay Informed**: Keep up with new features and improvements
7. **Document Solutions**: Record successful approaches
8. **Test Thoroughly**: Verify behavior in your environment

Limitations Summary
-------------------

The GPU vendor extensions provide essential GPU support for Canary but have important limitations that require careful consideration in test design and execution planning. Understanding these limitations helps users make informed decisions about when and how to use GPU resources effectively.