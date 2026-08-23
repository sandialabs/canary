---
name: canary-run-debug
description: Use this skill when running Canary tests or workflows, inspecting failures, querying job/session state, reproducing a job, or debugging resource and dependency problems.
---

# Running and debugging Canary jobs

## What this skill is for

Use this skill when you need to execute Canary jobs, inspect status, debug failures, or query persisted job/session state.

## First action: query execution and query capabilities

For running behavior:

```console
canary query -c execution.local
```

For result inspection:

```console
canary query -c query
canary query -c results
```

For resource failures:

```console
canary query -c resources
```

For dependency failures:

```console
canary query -c dependencies
```

## Basic execution workflow

1. Run jobs from a path, tag, or ID.

```console
canary run PATH
canary run TAG
canary run JOBID
```

2. Inspect status.

```console
canary status
```

3. Inspect logs for a job.

```console
canary log JOBID
```

4. Query structured state.

```console
canary query -j JOBID
canary query -j JOBID status
canary query -j JOBID measurements.data
canary query -s latest
```

5. Reproduce a single job if needed.

```console
canary exec JOBID
```

## Use query instead of scraping when possible

Canary persists JSON-like state in job and session lock files. Prefer:

```console
canary query -j JOBID measurements.data
canary query -s latest measurements
```

over parsing `canary-out.txt`.

Query syntax is lightweight, not jq. For details:

```console
canary query -c query
```

## Debugging failures

Use this order:

1. Check overall status.

```console
canary status
```

2. Open the failing job log.

```console
canary log JOBID
```

3. Query the job status reason.

```console
canary query -j JOBID status.reason
```

4. Query measurements.

```console
canary query -j JOBID measurements.data
```

5. Locate the working directory.

```console
canary location JOBID
```

6. Re-run the single job if appropriate.

```console
canary exec JOBID
```

## Debugging dependency problems

If a job did not run, inspect whether it was blocked:

```console
canary query -j JOBID status
canary query -c dependencies
```

A blocked job often means an upstream dependency completed but did not satisfy the dependency condition.

## Debugging resource problems

If jobs do not run or are masked due to resource capacity, inspect the resource pool and requirements:

```console
canary config show resource_pool
canary query -c resources
```

Common issues:

- The resource type is not defined in the resource pool.
- A job requests more slots than exist.
- A multi-node job cannot be accommodated.
- Oversubscription or slot counts are configured incorrectly.

## Rerun strategies

For rerunning selected jobs, query:

```console
canary query -c commands.run
canary query -c workflows.common_patterns
```

Common patterns:

```console
canary run TAG --only failed
canary run TAG --only not_pass
canary run TAG --only changed
```

## Common mistakes

- Running from the wrong workspace.
- Assuming the latest visible results are the only persisted state.
- Forgetting that `TestResults` is a view, not the entire workspace.
- Debugging only logs and ignoring `testcase.lock`.
- Querying `-c all` when `-c query`, `-c results`, or `-c resources` is enough.

## Related skills

- Use `canary-test-authoring` to modify tests.
- Use `canary-workflows-results` for workflow-level result analysis.
- Use `canary-extension-development` for hook or plugin changes.
