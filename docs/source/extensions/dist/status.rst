.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Status and Diagnostics
=======================

The ``canary_dist`` extension provides status and diagnostic capabilities to help users monitor the distributed resource pool and troubleshoot execution issues.

Status Command
--------------

The ``canary dist status`` command shows the current state of the distributed resource pool:

.. code-block:: console

   python3 -m canary dist status --server-url http://pool.example:8000

Command Options
~~~~~~~~~~~~~~~

- ``--server-url URL``: Distributed pool server location
- ``CANARY_DIST_SERVER_URL`` environment variable can also be used

Status Output
-------------

The status command provides comprehensive information about the pool:

Pool Information
~~~~~~~~~~~~~~~~

- Server URL and connection status
- Total number of machines in pool
- Number of eligible machines
- Resource pool summary

Machine Information
~~~~~~~~~~~~~~~~~~~

For each machine, the status shows:

- Hostname
- State (online/offline)
- Tags
- Groups
- Available resources (CPUs, GPUs, etc.)
- Resource counts and slots

Resource Information
~~~~~~~~~~~~~~~~~~~~

- Total available resources by type
- Maximum capacity per resource type
- Resource distribution across machines

Example Status Output
---------------------

.. code-block:: text

   Distributed Resource Pool Status
   =================================

   Server: http://pool.example:8000
   Total Machines: 8
   Eligible Machines: 5

   Machines:

   host-a (online) [gpu, fast]
     CPUs: 8 slots (4 cores × 2)
     GPUs: 1 slot (1 GPU)
     Groups: production

   host-b (online) [fast]
     CPUs: 16 slots (8 cores × 2)
     Groups: production, development

   host-c (offline) [gpu]
     CPUs: 4 slots (2 cores × 2)
     GPUs: 2 slots (2 GPUs)
     Groups: development

   Resource Summary:
     CPUs: 28 slots max (host-b)
     GPUs: 2 slots max (host-c)

Status Interpretation
---------------------

Understanding status output helps diagnose pool issues:

Machine States
~~~~~~~~~~~~~~

- **online**: Machine available for execution
- **offline**: Machine unavailable for execution
- **eligible**: Machine passes filtering criteria

Resource Availability
~~~~~~~~~~~~~~~~~~~~~

- **Total Machines**: All machines in pool
- **Eligible Machines**: Machines available for current execution
- **Resource Summary**: Maximum available capacity

Tag and Group Information
~~~~~~~~~~~~~~~~~~~~~~~~~

- **Tags**: Machine capabilities and characteristics
- **Groups**: Machine organizational groups

Diagnostic Information
----------------------

The status command helps diagnose common issues:

No Eligible Machines
~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Eligible Machines = 0

**Causes**:

- All machines offline
- Tag filtering too restrictive
- Group filtering issues
- Server communication problems

**Solutions**:

- Check machine states
- Review tag requirements
- Verify server connectivity
- Contact pool administrator

Insufficient Resources
~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Low resource counts, small maximum capacity

**Causes**:

- Small pool size
- Resource-intensive workloads
- Machine filtering too restrictive
- Resource fragmentation

**Solutions**:

- Add more machines to pool
- Adjust batch requirements
- Review machine filtering
- Optimize resource utilization

Connection Issues
~~~~~~~~~~~~~~~~~

**Symptoms**: Connection errors, timeouts, no status output

**Causes**:

- Server unavailable
- Network connectivity issues
- Authentication problems
- Server configuration errors

**Solutions**:

- Verify server URL
- Check network connectivity
- Review authentication credentials
- Contact server administrator

Status Command Errors
---------------------

Common status command errors:

Server Unavailable
~~~~~~~~~~~~~~~~~~

**Error**: Connection refused, timeout, network errors

**Diagnosis**:

- Verify server URL is correct
- Check server is running
- Test network connectivity
- Review authentication requirements

Malformed Server Response
~~~~~~~~~~~~~~~~~~~~~~~~~

**Error**: JSON parse errors, invalid data format

**Diagnosis**:

- Check server version compatibility
- Review server response format
- Contact server administrator
- Test with different server if available

Authentication Errors
~~~~~~~~~~~~~~~~~~~~~

**Error**: Authentication failed, permission denied

**Diagnosis**:

- Verify authentication credentials
- Check user permissions
- Review server authentication requirements
- Contact server administrator

Status Command Usage
--------------------

Regular Status Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~

Regularly check pool status to monitor health:

.. code-block:: console

   # Check status before running tests
   python3 -m canary dist status --server-url http://pool.example:8000

   # Monitor status during long runs
   watch -n 60 "python3 -m canary dist status --server-url http://pool.example:8000"

Status-Based Decision Making
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use status information to make execution decisions:

.. code-block:: console

   # Check if sufficient resources available
   python3 -m canary dist status --server-url http://pool.example:8000

   # Adjust batch parameters based on available capacity
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 8 ./tests

Status Troubleshooting
----------------------

Troubleshoot status issues:

.. code-block:: console

   # Test server connectivity
   curl -v http://pool.example:8000/status

   # Check server logs
   # (Server-specific logging location)

   # Test with verbose output
   python3 -m canary dist status --server-url http://pool.example:8000 --verbose

   # Contact server administrator for assistance

Status Command Limitations
--------------------------

The status command has several limitations:

- No historical data or trends
- No detailed error diagnostics
- Limited server information
- No user-specific views
- Basic formatting only

Advanced Diagnostics
--------------------

For advanced diagnostics, consider:

Server Logs
~~~~~~~~~~~

Review server logs for detailed information:

- Connection logs
- Resource allocation logs
- Error and warning logs
- Performance metrics

Client-Side Logging
~~~~~~~~~~~~~~~~~~~

Enable verbose client-side logging:

.. code-block:: console

   python3 -m canary dist status --server-url http://pool.example:8000 --verbose

Network Diagnostics
~~~~~~~~~~~~~~~~~~~

Use network diagnostic tools:

.. code-block:: console

   # Test connectivity
   ping pool.example

   # Test HTTP connectivity
   curl -v http://pool.example:8000/status

   # Test specific endpoints
   curl -v http://pool.example:8000/accommodates

Resource Monitoring
~~~~~~~~~~~~~~~~~~~

Monitor resource utilization over time:

.. code-block:: console

   # Regular status checks
   while true; do
     python3 -m canary dist status --server-url http://pool.example:8000
     sleep 60
   done

Performance Monitoring
~~~~~~~~~~~~~~~~~~~~~~

Monitor performance metrics:

- Status command execution time
- Server response time
- Resource allocation patterns
- Pool utilization trends

Status Command Best Practices
-----------------------------

Regular Monitoring
~~~~~~~~~~~~~~~~~~

- Check status before important runs
- Monitor status during long executions
- Review status after failures
- Establish baseline status patterns

Status-Based Planning
~~~~~~~~~~~~~~~~~~~~~

- Plan test execution based on available resources
- Adjust batch parameters to match pool capacity
- Schedule runs during high-availability periods
- Avoid overloading the pool

Status Documentation
~~~~~~~~~~~~~~~~~~~~

- Document normal status patterns
- Record status during issues
- Share status with support teams
- Use status for capacity planning

Status Command Integration
---------------------------

Integrate status checking into workflows:

.. code-block:: bash

   # Pre-run status check
   STATUS=$(python3 -m canary dist status --server-url http://pool.example:8000)
   if [[ $STATUS == *"Eligible Machines: 0"* ]]; then
     echo "No eligible machines - aborting run"
     exit 1
   fi

   # Run tests
   python3 -m canary dist run --server-url http://pool.example:8000 ./tests

Status Command Future
---------------------

Potential future enhancements:

- Historical status tracking
- Trend analysis and visualization
- User-specific status views
- Enhanced error diagnostics
- Performance metrics integration
- Alerting and notification support