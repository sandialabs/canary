---
name: canary-workflows-results
description: Use this skill when orchestrating Canary workflows, dependency chains, post-processing, structured measurements, reports, or agentic result-analysis loops.
---

# Canary workflows and result analysis

## What this skill is for

Use this skill when a task involves more than running one test: parameter sweeps, dependency workflows, structured measurements, post-processing, reports, or agent-driven analysis loops.

## First action: query workflow capabilities

Start with:

```console
canary query -c workflows
```

Then query the specific area:

```console
canary query -c dependencies
canary query -c hooks.post
canary query -c results
canary query -c agent_workflows
```

## Workflow model

A Canary workflow is a dependency-aware set of jobs executed in a session.

Common workflow elements:

- parameterized job variants;
- dependencies between generated jobs;
- composite analysis jobs;
- post-test hooks;
- session hooks;
- structured measurements;
- generated reports.

## Recommended workflow for agents

1. Identify the workflow definition or generator.
2. Query the relevant capability topic.
3. Run the smallest useful selection.
4. Inspect status and structured measurements.
5. Decide whether to refine inputs, rerun, report, or stop.
6. Avoid loading the entire capability database unless necessary.

Useful commands:

```console
canary run PATH_OR_TAG
canary status
canary query -s latest
canary query -j JOBID measurements.data
```

## Structured measurements

Prefer structured measurements over log scraping.

A job-level post-processing hook can record values:

```python
@canary.hookimpl
def canary_runtest_finish(case):
    case.add_measurement("max_stress", 1.23e8)
```

A session hook can record workflow metadata:

```python
@canary.hookimpl
def canary_sessionstart(session):
    session.add_measurement("campaign", "optimization-run-17")
```

Query them later:

```console
canary query -j JOBID measurements.data.max_stress
canary query -s latest measurements.campaign
```

For hook details:

```console
canary query -c hooks.post
```

## Post-processing strategies

Choose the least invasive strategy:

1. If post-processing is part of the scientific test itself, implement it in the test.
2. If post-processing needs all parameterized cases, use a composite analysis job where supported.
3. If post-processing should apply uniformly to jobs, use a post-test hook.
4. If post-processing summarizes a whole session, use a session finish hook or reporter.

Query:

```console
canary query -c workflows.post_processing
canary query -c hooks.post
canary query -c results.reports
```

## Reports

Canary can generate reports such as JSON, JUnit XML, HTML, and Markdown when reporter plugins are available.

Query:

```console
canary query -c results.reports
canary query -c commands.report
```

Use reports when a human or CI system needs a durable artifact. Use `canary query` when an agent needs a specific structured value.

## Common mistakes

- Treating a session as only console output instead of persisted structured state.
- Using post-processing logs instead of measurements.
- Running too broad a workflow before testing a small selection.
- Ignoring blocked jobs in dependency workflows.
- Assuming a view directory contains all persisted results.

## Related skills

- Use `canary-test-authoring` for defining jobs and dependencies.
- Use `canary-run-debug` for failure diagnosis.
- Use `canary-extension-development` when the workflow requires new hooks, generators, launchers, or reporters.
