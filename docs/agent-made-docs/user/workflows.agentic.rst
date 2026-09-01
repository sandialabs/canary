.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-workflows-agentic:

Agentic Workflows
=================

Canary provides a robust foundation for agent-based workflow automation. Agents can leverage Canary's structured execution model, comprehensive querying capabilities, and extensible plugin architecture to implement sophisticated workflow management.

Canary as Agent-Friendly Substrate
-----------------------------------

Canary offers several features that make it ideal for agent integration:

- **Structured Measurements**: Rich, queryable execution data
- **Comprehensive Query API**: Programmatic access to all execution state
- **Plugin Hooks**: Extensible integration points for custom logic
- **Persistent Workspace**: State management across agent sessions
- **Dependency Management**: Complex workflow orchestration

Structured Measurements
-----------------------

Agents should prefer structured measurements over log scraping:

.. code-block:: python

   from canary import get_instance

   def test_function():
       self = get_instance()
       # Add structured measurements
       self.add_measurement("accuracy", 0.95)
       self.add_measurement("loss", 0.05)
       self.add_measurement("iterations", 1000)

Query measurements programmatically:

.. code-block:: console

   $ canary query -j JOB_ID measurements.accuracy
   0.95

Agent Loop Pattern
------------------

The canonical agent loop using Canary:

1. **Create/Load Workspace**:

   .. code-block:: python

      from canary import Workspace

      # Load existing workspace
      workspace = Workspace.load()

      # Or create new workspace
      workspace = Workspace.create(".")

2. **Select Jobs**:

   .. code-block:: python

      # Select jobs based on criteria
      specs = workspace.collect(scanpaths={".": ["*.pyt"]})
      selected = [spec for spec in specs if "regression" in spec.keywords]

3. **Run Workflow**:

   .. code-block:: python

      # Execute selected jobs
      session = workspace.run(specs=selected, tag="agent-run-1")

4. **Inspect Status and Query Data**:

   .. code-block:: python

      # Query results programmatically
      results = workspace.db.get_results()

      for job_id, result in results.items():
          status = result["status"]
          measurements = result["measurements"]
          # Analyze results

5. **Decide Next Action**:

   .. code-block:: python

      # Implement decision logic
      if any(r["status"]["category"] == "FAIL" for r in results.values()):
          # Rerun failed jobs
          failed_jobs = [k for k, v in results.items() if v["status"]["category"] == "FAIL"]
          workspace.run(job_ids=failed_jobs)
      else:
          # All jobs passed, proceed to next phase
          proceed_to_next_phase()

Plugin Hooks for Agents
-----------------------

Use plugin hooks to integrate agent logic:

**Session Start Hook**:

.. code-block:: python

   from canary import hookimpl

   @hookimpl
   def canary_sessionstart(session):
       # Add agent-specific metadata
       session.add_measurement("agent_name", "optimization-agent")
       session.add_measurement("campaign", "run-2024-01-01")
       session.add_measurement("objective", "minimize_loss")

**Test Finish Hook**:

.. code-block:: python

   @hookimpl
   def canary_runtest_finish(job):
       # Add custom measurements based on job results
       if job.status.is_success():
           # Extract metrics from job output
           metrics = parse_job_output(job)
           for name, value in metrics.items():
               job.add_measurement(name, value)

**Session Finish Hook**:

.. code-block:: python

   @hookimpl
   def canary_sessionfinish(session):
       # Aggregate session-level metrics
       results = session.workspace.db.get_results()
       total_duration = sum(r["timekeeper"]["duration"] for r in results.values())
       session.add_measurement("total_duration", total_duration)

       # Implement agent decision logic
       if should_continue(results):
           session.add_measurement("next_action", "continue")
       else:
           session.add_measurement("next_action", "stop")

Querying with Agents
--------------------

Agents can query structured data programmatically:

.. code-block:: python

   from canary import Workspace

   workspace = Workspace.load()

   # Query latest session measurements
   results = workspace.db.get_results()

   for job_id, result in results.items():
       # Access structured data
       status = result["status"]
       measurements = result["measurements"]
       duration = result["timekeeper"]["duration"]

       # Implement agent logic
       if status["category"] == "PASS":
           if measurements.get("accuracy", 0) > 0.95:
               mark_as_high_quality(job_id)
           else:
               schedule_for_review(job_id)

Advanced Query Examples
-----------------------

**Query specific measurements**:

.. code-block:: console

   $ canary query -s latest measurements.campaign
   "optimization-run-17"

   $ canary query -j JOB_ID measurements.data.max_stress
   1.23e8

**Query nested structures**:

.. code-block:: console

   $ canary query -j JOB_ID .resources.cpus
   [{"node": "host1", "id": "0", "slots": 4}]

**Query status patterns**:

.. code-block:: console

   $ canary query -s latest .status.*
   {
     "category": "PASS",
     "outcome": "PASSED",
     "reason": null,
     "code": 0
   }

Agent Safety Guidance
---------------------

**Do Not Edit Lock Files**:

- Lock files are managed by Canary
- Direct editing can corrupt workspace state
- Use Canary APIs for all modifications

**Prefer Structured Data**:

- Use ``add_measurement()`` instead of log parsing
- Query structured data with ``canary query``
- Avoid scraping logs when structured data exists

**Use Bounded Runs**:

- Specify explicit job selections
- Use ``--only`` strategies for control
- Avoid unlimited ``:all:`` selections in agents

**Preserve Artifacts**:

- Maintain complete execution records
- Archive important results
- Document provenance and decision rationale

**Record Provenance**:

- Track agent decisions and rationale
- Document configuration and environment
- Maintain audit trail of actions

Agent Workflow Examples
-----------------------

**Optimization Agent**:

.. code-block:: python

   def optimization_loop():
       workspace = Workspace.load()
       iteration = 0
       best_loss = float('inf')

       while iteration < MAX_ITERATIONS:
           iteration += 1

           # Run parameterized tests
           specs = workspace.collect(scanpaths={".": ["optimization_*.pyt"]})
           session = workspace.run(specs=specs, tag=f"opt-{iteration}")

           # Query results
           results = workspace.db.get_results()

           # Find best result
           current_best = float('inf')
           for job_id, result in results.items():
               loss = result["measurements"].get("loss", float('inf'))
               if loss < current_best:
                   current_best = loss
                   best_job_id = job_id

           # Update parameters based on results
           if current_best < best_loss:
               best_loss = current_best
               update_parameters(best_job_id)
           else:
               adjust_strategy()

           # Check convergence
           if converged(current_best, best_loss):
               break

**Regression Testing Agent**:

.. code-block:: python

   def regression_agent():
       workspace = Workspace.load()

       # Load baseline results
       baseline_results = load_baseline()

       # Run current tests
       workspace.run(specs=workspace.collect(), tag="regression-run")
       current_results = workspace.db.get_results()

       # Compare results
       regressions = []
       for job_id in baseline_results:
           if job_id in current_results:
               baseline = baseline_results[job_id]
               current = current_results[job_id]

               if compare_results(baseline, current):
                   regressions.append(job_id)

       # Handle regressions
       if regressions:
           notify_regressions(regressions)
           rerun_and_analyze(regressions)
       else:
           mark_as_stable()

**CI Integration Agent**:

.. code-block:: python

   def ci_agent():
       workspace = Workspace.load()

       # Clean workspace
       workspace.clean()

       # Collect and run tests
       specs = workspace.collect(scanpaths={"tests/": ["*.pyt"]})
       session = workspace.run(specs=specs, tag="ci-run")

       # Generate reports
       junit_report = workspace.report("junit")
       json_report = workspace.report("json")

       # Analyze results
       results = workspace.db.get_results()

       if any(r["status"]["category"] == "FAIL" for r in results.values()):
           # Handle failures
           generate_failure_report()
           notify_ci_failure()
           return False
       else:
           # Success
           generate_success_report()
           notify_ci_success()
           return True

Agent Plugin Example
--------------------

Complete agent plugin with hooks:

.. code-block:: python

   # agent_plugin.py
   from canary import hookimpl
   import datetime

   @hookimpl
   def canary_addconfig(config):
       # Add agent-specific configuration
       config.data.setdefault("agent", {})
       config.data["agent"]["name"] = "default-agent"
       config.data["agent"]["max_iterations"] = 10

   @hookimpl
   def canary_sessionstart(session):
       # Initialize agent metadata
       timestamp = datetime.datetime.now().isoformat()
       session.add_measurement("agent_start", timestamp)
       session.add_measurement("agent_name", session.config.get("agent", {}).get("name", "unknown"))

   @hookimpl
   def canary_runtest_finish(job):
       # Add custom metrics to each job
       if job.status.is_success():
           # Parse and add metrics from job output
           output = job.workspace.joinpath(job.stdout).read_text()
           metrics = parse_custom_metrics(output)
           for name, value in metrics.items():
               job.add_measurement(f"custom_{name}", value)

   @hookimpl
   def canary_sessionfinish(session):
       # Aggregate agent results
       results = session.workspace.db.get_results()

       total_jobs = len(results)
       passed_jobs = sum(1 for r in results.values() if r["status"]["category"] == "PASS")
       failed_jobs = total_jobs - passed_jobs

       session.add_measurement("agent_jobs_total", total_jobs)
       session.add_measurement("agent_jobs_passed", passed_jobs)
       session.add_measurement("agent_jobs_failed", failed_jobs)
       session.add_measurement("agent_success_rate", passed_jobs / total_jobs if total_jobs > 0 else 0)

       # Determine next action
       if failed_jobs > 0:
           session.add_measurement("agent_next_action", "rerun_failed")
       else:
           session.add_measurement("agent_next_action", "complete")

Agent Best Practices
--------------------

**Idempotent Operations**:

- Design agents to handle reruns gracefully
- Use unique session tags for each run
- Avoid destructive operations without confirmation

**State Management**:

- Persist agent state in workspace
- Use measurements for agent metadata
- Document state transitions

**Error Handling**:

- Implement robust error recovery
- Use Canary's status system for error reporting
- Provide meaningful error messages

**Performance Monitoring**:

- Track execution metrics
- Monitor resource usage
- Optimize based on performance data

**Configuration Management**:

- Externalize agent configuration
- Use Canary's config system
- Document configuration requirements

Agent Troubleshooting
---------------------

**Agent Loop Not Progressing**:

.. code-block:: console

   $ canary query -s latest measurements.agent_next_action
   "rerun_failed"

Solution: Check for infinite loops in agent logic

**Missing Measurements**:

.. code-block:: console

   $ canary query -j JOB_ID measurements.custom_metric
   Error: No such key

Solution: Verify hook implementation and job execution

**Stale Agent State**:

.. code-block:: console

   $ canary query -s latest measurements.agent_iteration
   5  # But should be higher

Solution: Check workspace persistence and agent logic

**Resource Contention**:

.. code-block:: console

   $ canary run --workers=16 .
   Error: insufficient resources

Solution: Adjust worker count or resource allocation

Agent Integration Patterns
--------------------------

**GitHub Actions Integration**:

.. code-block:: yaml

   - name: Run Canary Agent
     run: |
       python agent.py
       canary query -s latest measurements.agent_success_rate > success_rate.txt
       if [ $(cat success_rate.txt) -lt 0.95 ]; then
         echo "Agent success rate too low"
         exit 1
       fi

**Continuous Optimization**:

.. code-block:: python

   def continuous_optimization():
       while True:
           # Run optimization cycle
           success = run_optimization_cycle()

           # Query results
           results = query_current_results()

           # Check for improvement
           if not improved(results):
               break

           # Sleep before next cycle
           time.sleep(3600)

**Multi-Agent Coordination**:

.. code-block:: python

   def coordinator_agent():
       # Launch specialized agents
       agents = [
           OptimizationAgent(),
           RegressionAgent(),
           ValidationAgent()
       ]

       # Run agents in sequence
       for agent in agents:
           agent.run()

           # Check agent results
           if not agent.successful():
               handle_agent_failure(agent)
               break

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`workspaces`: Workspace structure and management
- :doc:`query`: Advanced querying capabilities
- :doc:`workflows`: Common workflow patterns
- :doc:`/reference/commands.query`: Query command reference
- :doc:`/reference/commands.config`: Config command reference
