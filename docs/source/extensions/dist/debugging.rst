.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging
=========

Debugging distributed execution issues requires understanding the complex interaction between Canary, the distributed resource pool, and remote execution environments. This guide provides systematic approaches to diagnosing and resolving common problems.

Debugging Approach
------------------

Systematic debugging involves:

1. **Problem Identification**: Clearly define the issue
2. **Information Gathering**: Collect relevant diagnostic data
3. **Root Cause Analysis**: Identify underlying causes
4. **Solution Testing**: Verify proposed solutions
5. **Prevention Planning**: Implement preventive measures

Common Debugging Scenarios
---------------------------

Connection Issues
~~~~~~~~~~~~~~~~~

**Symptoms**: Connection refused, timeouts, network errors

**Diagnosis Steps**:

1. Verify server URL and connectivity
2. Check network configuration and firewalls
3. Test server availability with curl
4. Review authentication credentials

**Debugging Commands**:

.. code-block:: console

   # Test basic connectivity
   ping pool.example

   # Test HTTP connectivity
   curl -v http://pool.example:8000/status

   # Test with authentication
   curl -v -H "X-User: $(whoami)" -H "X-Host: $(hostname)" http://pool.example:8000/status

   # Test Canary connection
   python3 -m canary dist status --server-url http://pool.example:8000 --verbose

Resource Allocation Issues
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Checkout failures, insufficient resources, allocation errors

**Diagnosis Steps**:

1. Check pool status and available resources
2. Review batch resource requirements
3. Verify machine eligibility and filtering
4. Examine resource accommodation checks

**Debugging Commands**:

.. code-block:: console

   # Check pool status
   python3 -m canary dist status --server-url http://pool.example:8000

   # Test with smaller batch requirements
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 4 ./tests

   # Test with different machine tags
   python3 -m canary dist run --server-url http://pool.example:8000 --tags fast ./tests

   # Review resource requirements
   python3 -m canary show --resources ./tests

Remote Execution Issues
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Remote command failures, process errors, result transfer issues

**Diagnosis Steps**:

1. Verify remote host availability
2. Check hpc_connect configuration
3. Test remote command execution
4. Review remote execution logs

**Debugging Commands**:

.. code-block:: console

   # Test remote host connectivity
   ssh host-a

   # Test hpc_connect backend
   python3 -c "import hpc_connect; print(hpc_connect.get_backend('remote_subprocess'))"

   # Test remote Canary execution
   ssh host-a "python3 -m canary --version"

   # Test workspace manually
   python3 -m canary dist exec --workspace /path/to/batch/workspace --verbose

Environment Export Issues
~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Missing environment variables, module loading failures, environment mismatches

**Diagnosis Steps**:

1. Verify environment export configuration
2. Check variable availability on remote host
3. Test module environment reconstruction
4. Review environment propagation logs

**Debugging Commands**:

.. code-block:: console

   # Check current environment
   env | grep -E "(VAR1|VAR2)"

   # Test environment export
   python3 -m canary dist run --server-url http://pool.example:8000 --export=VAR1 --verbose ./tests

   # Check remote environment
   ssh host-a env | grep -E "(VAR1|VAR2)"

   # Test module export
   python3 -m canary dist run --server-url http://pool.example:8000 --export=LOADEDMODULES ./tests

Batch Formation Issues
~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No batches formed, batching algorithm errors, poor batch composition

**Diagnosis Steps**:

1. Review job resource requirements
2. Check batch configuration parameters
3. Verify dependency constraints
4. Examine batching algorithm logs

**Debugging Commands**:

.. code-block:: console

   # Check job requirements
   python3 -m canary show --resources ./tests

   # Test with different batch parameters
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 8 --batch-count 2 ./tests

   # Test with verbose batching
   python3 -m canary dist run --server-url http://pool.example:8000 --verbose ./tests

   # Review dependency constraints
   python3 -m canary show --dependencies ./tests

Debugging Tools
---------------

Verbose Logging
~~~~~~~~~~~~~~~

Enable verbose logging for detailed diagnostic information:

.. code-block:: console

   # Verbose status check
   python3 -m canary dist status --server-url http://pool.example:8000 --verbose

   # Verbose test run
   python3 -m canary dist run --server-url http://pool.example:8000 --verbose ./tests

   # Verbose remote execution
   python3 -m canary dist exec --workspace /path/to/batch/workspace --verbose

Log Analysis
~~~~~~~~~~~~

Analyze logs for error patterns and diagnostic information:

.. code-block:: console

   # Check Canary logs
   tail -f ~/.canary/logs/dist.log

   # Check server logs
   # (Server-specific logging location)

   # Check remote execution logs
   tail -f /path/to/batch/workspace/logs/execution.log

Network Diagnostics
~~~~~~~~~~~~~~~~~~~

Use network tools to diagnose connectivity issues:

.. code-block:: console

   # Test connectivity
   ping pool.example
   traceroute pool.example

   # Test port availability
   nc -zv pool.example 8000
   telnet pool.example 8000

   # Test HTTP endpoints
   curl -v http://pool.example:8000/status
   curl -v http://pool.example:8000/accommodates

Resource Monitoring
~~~~~~~~~~~~~~~~~~~

Monitor resource utilization and availability:

.. code-block:: console

   # Regular status checks
   watch -n 10 "python3 -m canary dist status --server-url http://pool.example:8000"

   # Resource utilization tracking
   while true; do
     echo "=== $(date) ==="
     python3 -m canary dist status --server-url http://pool.example:8000
     sleep 60
   done

Debugging Workflow
------------------

Step-by-Step Debugging
~~~~~~~~~~~~~~~~~~~~~~

1. **Reproduce the Issue**: Create consistent reproduction steps
2. **Isolate the Problem**: Narrow down the specific component
3. **Gather Diagnostics**: Collect logs, status, and configuration
4. **Analyze Data**: Identify patterns and root causes
5. **Test Hypotheses**: Verify potential causes
6. **Implement Fix**: Apply the solution
7. **Verify Resolution**: Confirm the issue is resolved
8. **Document Findings**: Record the solution for future reference

Debugging Checklist
~~~~~~~~~~~~~~~~~~~

- [ ] Verify server connectivity and availability
- [ ] Check pool status and resource availability
- [ ] Review batch configuration and requirements
- [ ] Test remote execution capabilities
- [ ] Validate environment export configuration
- [ ] Examine dependency constraints
- [ ] Review authentication and permissions
- [ ] Check network configuration and firewalls
- [ ] Analyze logs for error patterns
- [ ] Test with minimal configuration
- [ ] Gradually increase complexity

Common Error Patterns
---------------------

Connection Error Patterns
~~~~~~~~~~~~~~~~~~~~~~~~~

- **"Connection refused"**: Server not running or wrong port
- **"Timeout"**: Network issues or server unresponsive
- **"Authentication failed"**: Invalid credentials or permissions
- **"SSL errors"**: Certificate or protocol issues

Resource Error Patterns
~~~~~~~~~~~~~~~~~~~~~~~

- **"Insufficient resources"**: Not enough machines or capacity
- **"Resource unavailable"**: Specific resource type missing
- **"Checkout failed"**: Transaction or allocation issues
- **"Checkin failed"**: Transaction validation problems

Execution Error Patterns
~~~~~~~~~~~~~~~~~~~~~~~~

- **"Command not found"**: Canary not installed on remote host
- **"Permission denied"**: File access or execution permissions
- **"Module not found"**: Module environment issues
- **"Environment variable missing"**: Export configuration problems

Batch Error Patterns
~~~~~~~~~~~~~~~~~~~~

- **"No batches formed"**: Batching algorithm issues
- **"Dependency conflicts"**: Circular or complex dependencies
- **"Resource constraints"**: Jobs don't fit batch requirements
- **"Configuration errors"**: Invalid batch parameters

Debugging Best Practices
-------------------------

Isolation Technique
~~~~~~~~~~~~~~~~~~~

Isolate problems by testing components individually:

.. code-block:: console

   # Test server connectivity separately
   curl http://pool.example:8000/status

   # Test resource pool separately
   python3 -c "from canary_dist.adapter import DistributedResourcePoolAdapter; print(Adapter('http://pool.example:8000').current_state())"

   # Test batching separately
   python3 -m canary show --batches ./tests

Divide and Conquer
~~~~~~~~~~~~~~~~~~

Break down complex issues into smaller components:

1. Test server connectivity
2. Test resource discovery
3. Test batch formation
4. Test remote execution
5. Test result collection

Minimal Reproduction
~~~~~~~~~~~~~~~~~~~~

Create minimal test cases to reproduce issues:

.. code-block:: console

   # Test with minimal test set
   python3 -m canary dist run --server-url http://pool.example:8000 tests/simple_test.py

   # Test with minimal configuration
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 1 tests/simple_test.py

Gradual Complexity Increase
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Gradually increase complexity to identify breaking points:

.. code-block:: console

   # Start simple
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 1 tests/simple.py

   # Add complexity
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 2 tests/simple.py tests/medium.py

   # Full complexity
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 8 tests/

Debugging Configuration
-----------------------

Debugging configuration involves setting up appropriate logging and diagnostic tools:

Logging Configuration
~~~~~~~~~~~~~~~~~~~~~

Configure appropriate logging levels:

.. code-block:: console

   # Set logging level
   export CANARY_LOG_LEVEL=DEBUG

   # Enable specific loggers
   export CANARY_LOG_DIST=DEBUG
   export CANARY_LOG_RESOURCE=DEBUG

Diagnostic Tools Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set up diagnostic tools and monitoring:

.. code-block:: console

   # Enable verbose output
   alias canary-dist-verbose='python3 -m canary dist --verbose'

   # Set up log monitoring
   tail -f ~/.canary/logs/dist.log | grep -E "(ERROR|WARN)"

   # Configure network monitoring
   tcpdump -i eth0 port 8000

Debugging Environment Setup
---------------------------

Set up a consistent debugging environment:

.. code-block:: console

   # Create debugging workspace
   mkdir -p ~/canary-debug
   cd ~/canary-debug

   # Set up environment variables
   export CANARY_DIST_SERVER_URL=http://pool.example:8000
   export CANARY_LOG_LEVEL=DEBUG

   # Create test configuration
   cat > debug-config.py << EOF
   # Debugging configuration
   DEBUG = True
   LOG_LEVEL = "DEBUG"
   EOF

Debugging Scripts
-----------------

Create reusable debugging scripts:

.. code-block:: bash

   #!/bin/bash
   # debug-dist.sh - Distributed execution debugging script

   set -e

   echo "=== Distributed Execution Debug Script ==="
   echo "Server: $CANARY_DIST_SERVER_URL"
   echo "Date: $(date)"
   echo

   # Test server connectivity
   echo "=== Testing Server Connectivity ==="
   curl -v "$CANARY_DIST_SERVER_URL/status" || echo "Server connectivity failed"
   echo

   # Test pool status
   echo "=== Testing Pool Status ==="
   python3 -m canary dist status --verbose || echo "Pool status failed"
   echo

   # Test simple execution
   echo "=== Testing Simple Execution ==="
   python3 -m canary dist run --batch-width 1 --verbose tests/simple.py || echo "Simple execution failed"
   echo

   echo "=== Debug Script Complete ==="

Advanced Debugging Techniques
-----------------------------

Remote Debugging
~~~~~~~~~~~~~~~~

Debug remote execution issues:

.. code-block:: console

   # Connect to remote host
   ssh host-a

   # Check remote Canary installation
   python3 -m canary --version

   # Test remote execution manually
   python3 -m canary dist exec --workspace /path/to/batch/workspace --verbose

   # Check remote logs
   tail -f /path/to/batch/workspace/logs/execution.log

   # Check remote environment
   env | grep -E "(CANARY|DIST)"

Server-Side Debugging
~~~~~~~~~~~~~~~~~~~~~

Debug server-side issues (requires server access):

.. code-block:: console

   # Check server logs
   tail -f /var/log/canary-dist/server.log

   # Check server status
   systemctl status canary-dist-server

   # Test server endpoints
   curl -v http://localhost:8000/status
   curl -v http://localhost:8000/accommodates

   # Check server configuration
   cat /etc/canary-dist/config.yaml

Dependency Debugging
~~~~~~~~~~~~~~~~~~~~

Debug dependency-related issues:

.. code-block:: console

   # Show job dependencies
   python3 -m canary show --dependencies ./tests

   # Test with dependency visualization
   python3 -m canary show --dependencies --graph ./tests | dot -Tpng > deps.png

   # Test dependency-heavy workloads
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 1 tests/dependent_tests/

Performance Debugging
~~~~~~~~~~~~~~~~~~~~~

Debug performance issues:

.. code-block:: console

   # Time different operations
   time python3 -m canary dist status --server-url http://pool.example:8000
   time python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 1 tests/simple.py

   # Profile execution
   python3 -m cProfile -o profile.prof python3 -m canary dist run --server-url http://pool.example:8000 tests/simple.py

   # Analyze profile
   python3 -m pstats profile.prof

Debugging Documentation
-----------------------

Document debugging findings and solutions:

.. code-block:: markdown

   # Debugging Issue: Connection Timeout

   ## Symptoms
   - Connection timeout when running `canary dist status`
   - Intermittent connectivity issues

   ## Root Cause
   - Network firewall blocking port 8000
   - Server load balancing issues

   ## Solution
   - Configure firewall to allow port 8000
   - Adjust server load balancing configuration
   - Increase connection timeout settings

   ## Verification
   - Test connectivity with `curl -v http://pool.example:8000/status`
   - Monitor connection stability over time
   - Verify firewall rules are persistent

Debugging Resources
-------------------

Additional resources for debugging:

- Canary documentation and user guides
- Distributed execution architecture documentation
- Server administration guides
- Network troubleshooting resources
- Performance optimization guides
- Community forums and support channels

Debugging Limitations
---------------------

Debugging has several limitations:

- Limited visibility into server internals
- Complex distributed system interactions
- Environment differences between hosts
- Timing and race condition issues
- Limited cross-platform debugging tools

These limitations should be considered when approaching debugging challenges.