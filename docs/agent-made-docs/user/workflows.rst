.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-workflows:

Workflows
=========

Canary supports diverse workflows for different use cases, from local development to large-scale distributed execution. This guide covers common manual workflows and best practices.

Local Developer Loop
--------------------

The basic development workflow:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./basic, python3 -m canary status -rA]
   :cwd: /examples

This example demonstrates:

1. **Run Tests**: Execute tests from the basic examples
2. **Inspect Results**: Check status of all jobs
3. **View Logs**: Examine output from the latest job

**Best Practices**:

- Use ``--workers=1`` for deterministic debugging
- Enable debug mode: ``canary -d run my_test.pyt``
- Use ``canary location JOB_ID`` to navigate to test directories

Persistent Workspace Loop
-------------------------

Maintain a persistent workspace across development sessions:

1. **Initialize Workspace**:

   .. code-block:: console

      $ canary workspace init

2. **Collect Tests**:

   .. code-block:: console

      $ canary collect .

3. **Run Tests**:

   .. code-block:: console

      $ canary run :all:

4. **Inspect and Iterate**:

   .. code-block:: console

      $ canary status -rf
      $ canary log FAILED_JOB_ID

**Best Practices**:

- Commit ``.canary/config.yaml`` to version control
- Use selections for common test groups
- Regularly clean old sessions

Run Only Changed Jobs
---------------------

Focus on recently modified tests:

.. code-block:: console

   $ git status  # Identify changed files
   $ canary run path/to/changed_test.pyt

Use selections to track changed jobs:

.. code-block:: console

   $ canary select --changed :all: @changed
   $ canary run @changed

**Best Practices**:

- Use version control to identify changes
- Create selections for common change patterns
- Combine with ``--only=notrun`` for efficiency

Rerun Failed Jobs
-----------------

Focus on failures for efficient debugging:

.. code-block:: console

   $ canary status -rf  # Identify failed jobs
   $ canary run --only=failed .

Rerun specific failed jobs:

.. code-block:: console

   $ canary run FAILED_JOB_ID

**Best Practices**:

- Inspect logs before rerunning: ``canary log FAILED_JOB_ID``
- Use ``--workers=1`` for deterministic reruns
- Check dependencies: ``canary describe FAILED_JOB_ID``

Inspect Failures
----------------

Comprehensive failure inspection workflow:

1. **List Failures**:

   .. code-block:: console

      $ canary status -rf

2. **Inspect Status**:

   .. code-block:: console

      $ canary query -j FAILED_JOB_ID .status

3. **View Logs**:

   .. code-block:: console

      $ canary log FAILED_JOB_ID
      $ canary log --error FAILED_JOB_ID

4. **Locate Execution**:

   .. code-block:: console

      $ cd $(canary location FAILED_JOB_ID)

5. **Examine Artifacts**:

   .. code-block:: console

      $ ls -la
      $ cat canary-out.txt

**Best Practices**:

- Capture full context before rerunning
- Document failure patterns
- Check resource allocation: ``canary query -j JOB_ID .resources``

Rebaseline Workflow
-------------------

Update baseline files when expected results change:

1. **Run Tests**:

   .. code-block:: console

      $ canary run .

2. **Identify Jobs Needing Rebaseline**:

   .. code-block:: console

      $ canary status -rd  # Show diffed jobs

3. **Rebaseline**:

   .. code-block:: console

      $ canary rebaseline .
      $ canary rebaseline DIFFED_JOB_ID

4. **Verify**:

   .. code-block:: console

      $ canary run .  # Should now pass

**Best Practices**:

- Rebaseline only when changes are intentional
- Review diffs before rebaselining
- Commit baseline updates with code changes

Reporting Workflow
------------------

Generate and analyze reports:

1. **Run Tests**:

   .. code-block:: console

      $ canary run .

2. **Generate Reports**:

   .. code-block:: console

      $ canary report junit > results.xml
      $ canary report json > results.json

3. **Analyze**:

   .. code-block:: console

      $ canary status --durations=10
      $ canary query -s latest measurements

**Best Practices**:

- Automate report generation in CI
- Archive reports for historical analysis
- Use structured formats (JSON, JUnit) for processing

CI Workflow
-----------

Continuous Integration workflow:

1. **Clean Workspace**:

   .. code-block:: console

      $ canary workspace clean

2. **Run Full Suite**:

   .. code-block:: console

      $ canary run --workers=8 .

3. **Generate Reports**:

   .. code-block:: console

      $ canary report junit > test-results.xml
      $ canary report json > test-results.json

4. **Exit with Status**:

   .. code-block:: console

      $ canary run --fail-fast .

**Best Practices**:

- Use ``--fail-fast`` for quick feedback
- Parallelize with appropriate ``--workers``
- Archive reports as build artifacts
- Clean workspace between runs for consistency

HPC Workflow
------------

High-Performance Computing workflow:

1. **Configure HPC Plugin**:

   .. code-block:: yaml

      canary:
        plugins:
          - canary_hpc
        hpc:
          scheduler: slurm
          partition: gpu

2. **Run with HPC Resources**:

   .. code-block:: console

      $ canary run --workers=32 -r gpus=8 .

3. **Monitor**:

   .. code-block:: console

      $ canary status --durations
      $ canary query -s latest .resources

**Best Practices**:

- Configure appropriate resource limits
- Use HPC-specific plugins
- Monitor resource utilization
- Optimize job distribution

Distributed Workflow
--------------------

Distributed execution across multiple nodes:

1. **Configure Multi-Node**:

   .. code-block:: yaml

      canary:
        resource_pool:
          allow_multinode: true
          nodes:
            - id: node1
              resources: {cpus: 32, gpus: 4}
            - id: node2
              resources: {cpus: 32, gpus: 4}

2. **Run Distributed**:

   .. code-block:: console

      $ canary run --distributed .

3. **Monitor**:

   .. code-block:: console

      $ canary status --sort-by=duration

**Best Practices**:

- Ensure network connectivity between nodes
- Configure shared filesystem for workspace
- Monitor cross-node communication
- Balance resource allocation

Migration Workflow
------------------

Migrating from existing test suites:

1. **Analyze Existing Suite**:

   .. code-block:: console

      $ ctest --help
      $ vvtest --help

2. **Create Canary Equivalents**:

   .. code-block:: console

      $ canary collect --vvtest path/to/vvtest/suite
      $ canary collect --ctest path/to/ctest/suite

3. **Run and Compare**:

   .. code-block:: console

      $ canary run --dry-run .
      $ canary run .

4. **Iterate and Refine**:

   .. code-block:: console

      $ canary status -ra
      $ canary log FAILED_JOB_ID

**Best Practices**:

- Start with small subsets for validation
- Map existing concepts to Canary equivalents
- Preserve existing test logic
- Gradually expand coverage

Workflow Best Practices
-----------------------

**Consistency**:

- Standardize workflow patterns across team
- Document common workflows
- Use consistent naming conventions

**Automation**:

- Script repetitive workflow steps
- Automate common sequences
- Use selections for frequent operations

**Documentation**:

- Document workflow decisions
- Capture troubleshooting steps
- Share insights with team

**Monitoring**:

- Track execution metrics
- Monitor resource usage
- Analyze performance trends

**Continuous Improvement**:

- Review and refine workflows regularly
- Incorporate lessons learned
- Optimize based on usage patterns

Workflow Troubleshooting
------------------------

**Stuck Workflow**:

.. code-block:: console

   $ canary status
   # Shows jobs not progressing

Solution: Check resource availability and worker status

**Inconsistent Results**:

.. code-block:: console

   $ canary run .
   # Different results on rerun

Solution: Use ``--workers=1`` for deterministic execution

**Slow Execution**:

.. code-block:: console

   $ time canary run .
   # Takes longer than expected

Solution: Check ``canary status --durations`` for bottlenecks

**Resource Contention**:

.. code-block:: console

   $ canary run .
   Error: insufficient resources

Solution: Adjust resource pool or reduce concurrency

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`running`: Execution configuration and strategies
- :doc:`selection`: Job selection and filtering
- :doc:`results`: Result inspection and analysis
- :doc:`debugging`: Debugging workflows and techniques
- :doc:`/reference/commands.run`: Run command reference
- :doc:`/reference/commands.status`: Status command reference
- :doc:`/reference/commands.rebaseline`: Rebaseline command reference
