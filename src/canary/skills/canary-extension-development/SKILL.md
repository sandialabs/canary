---
name: canary-extension-development
description: Use this skill when implementing or modifying Canary plugins, generators, hooks, launchers, reporters, resource integrations, or extension documentation.
---

# Developing Canary extensions

## What this skill is for

Use this skill when you need to extend Canary rather than simply write or run tests.

Extension tasks include:

- adding a new job generator;
- adding a CLI command;
- adding configuration or options;
- adding pre-test or post-test hooks;
- adding custom execution launchers;
- adding resource-pool behavior;
- adding reports;
- adding extension documentation.

## First action: query extension capabilities

Start narrowly:

```console
canary query -c plugins
canary query -c hooks
```

For specific tasks:

```console
canary query -c plugins.generators
canary query -c hooks.post
canary query -c hooks.resources
canary query -c plugins.reporters
```

Only use:

```console
canary query -c all
```

if you need broad architecture context.

## Plugin model

Canary uses pluggy. Runtime plugin discovery uses the existing `canary` entry point group.

Typical extension workflow:

1. Decide what kind of extension is needed.
2. Query the relevant capability topic.
3. Implement the hook or interface.
4. Add tests that exercise the extension through Canary behavior.
5. Add package-local docs under the extension package if appropriate.
6. Ensure packaging includes any data files or docs that must be installed.

## Choosing an extension point

Use this guide:

- New input file or job-definition format: implement a generator.
- New CLI operation: implement `CanarySubcommand` and register with `canary_addcommand`.
- Pre-test setup behavior: use `canary_runteststart`.
- Post-test processing: use `canary_runtest_finish`.
- Whole-session summary or reporting: use `canary_runtests_report` or `canary_sessionfinish`.
- Custom process execution: implement a `Launcher` and return it from `canary_runtest_launcher`.
- Resource discovery or mutation: use resource-pool hooks.
- Machine-readable output: implement or extend a reporter.

## Job generators

Before writing a generator, query:

```console
canary query -c plugins.generators
canary query -c apis.generators
```

A generator should emit `JobSpecIR` or `JobSpec` objects. If it emits unresolved dependency selectors, Canary will resolve them later.

Do not make the generator execute the jobs. Generation describes work; Canary executes `Job` objects.

## Hooks and post-processing

Before adding post-processing, query:

```console
canary query -c hooks.post
```

Use `case.add_measurement()` for structured job data. Use `session.add_measurement()` for structured session data.

Avoid storing agent-critical data only in logs.

## Extension documentation

Extension packages may provide docs at:

```text
src/canary_<name>/docs/index.rst
```

The core docs build discovers installed packages registered through the `canary` entry point group. If an extension has `docs/index.rst`, `conf.py` links that docs directory into:

```text
src/canary/docs/extensions/<extension module name>
```

The generated core `index.rst` is produced from `index.rst.in`.

If `src/canary/docs/extensions/` already exists, discovery is skipped.

Query:

```console
canary query -c plugins.documentation
```

## Common mistakes

- Executing work inside a generator instead of emitting specs.
- Adding hook logic that mutates job state without saving or using existing APIs.
- Writing post-processing data only to text logs.
- Registering a plugin but forgetting the `canary` entry point.
- Creating extension docs outside the installed package.
- Depending on symlink-based docs discovery on Windows; that mechanism is not intended to support Windows.

## Related skills

- Use `canary-test-authoring` when the task can be solved by writing a test.
- Use `canary-workflows-results` when the task is post-processing or workflow analysis.
- Use `canary-run-debug` when validating extension behavior through execution.
