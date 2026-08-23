---
name: canary-orientation
description: Use this skill when you need to understand what Canary is, when to use it, and how to discover detailed Canary capabilities without loading the full documentation.
---

# Canary orientation for coding agents

## What this skill is for

Use this skill when you are unfamiliar with Canary or need to decide whether Canary is the right execution layer for a coding, testing, simulation, or workflow task.

Canary is a workflow and test manager. It discovers job definitions through generators, resolves job dependencies, executes jobs in sessions, manages resource constraints, persists results, and exposes structured results for tools and agents.

## First action: query the capability overview

Do not load the full manual first. Query the compact machine-readable overview:

```console
canary query -c overview
```

If you need broad detailed information, use:

```console
canary query -c all
```

Only use `-c all` when broad knowledge is necessary. Prefer targeted topics.

## Core mental model

Use this model when reasoning about Canary:

1. A user writes or provides a job definition.
2. A Canary job generator interprets it.
3. The generator emits `JobSpecIR` or `JobSpec`.
4. Canary resolves dependencies into a spec graph.
5. A workspace creates a session.
6. The session constructs `Job` objects.
7. Canary schedules jobs with resource constraints.
8. Jobs write logs, lock files, measurements, artifacts, and result rows.
9. Agents inspect the result with `canary status`, `canary log`, and `canary query`.

Query more detail when needed:

```console
canary query -c concepts
canary query -c jobs
canary query -c sessions
canary query -c resources
```

## When to use Canary

Use Canary when the task involves:

- running tests or simulations with persistent results;
- parameterized test or workflow variants;
- dependency-aware execution;
- resource-aware scheduling;
- post-processing or measurement capture;
- CI or report generation;
- reproducible job/session inspection;
- plugin-based extension.

Do not use Canary when the task is just a one-off local shell command with no need for persistence, resources, dependency tracking, or structured results.

## Important principles

- Canary core does not define one universal job-definition format.
- Generators define input formats such as Python job definitions, VVTest files, CTest metadata, or extension-specific formats.
- `.pyt` files are a reference generator format, not the only Canary format.
- Structured measurements are better than log scraping.
- `canary query -c TOPIC` is the main way to retrieve detailed agent-oriented capability information.

## Common mistakes

- Assuming `.pyt` is the Canary core format.
- Querying `canary query -c all` when a narrower topic is enough.
- Scraping logs when a job or hook could record measurements.
- Assuming SQLite is the only persisted state; job and session lock files matter.
- Ignoring resource requirements when running workflows.

## Related skills

Use another Canary skill when you know your task:

- Author tests: `canary-test-authoring`
- Run, debug, and inspect tests: `canary-run-debug`
- Use workflows and analyze results: `canary-workflows-results`
- Implement hooks, plugins, or extensions: `canary-extension-development`
