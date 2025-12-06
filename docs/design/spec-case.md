# From a Monolithic TestCase to the Canary Execution Model

## Overview

Canary's design evolved from a single, monolithic TestCase class into a small, layered hierarchy of immutable specification objects that describe what to run, and a single runtime class that defines how to run it.

`UnresolvedSpec` → `ResolvedSpec` → `TestSpec` → `TestCase`

This structure separates test definition, dependency resolution, and execution, making tests immutable, reproducible, and easy to parallelize.

## The Original TestCase

### Early Design

Initially, Canary used one large `TestCase` class to represent everything about a test:

* Parameters and dependencies
* Paths and file management
* Execution and result collection
* Status and timing

### Problems

* Conflated concerns: Test definition, dependency resolution, and execution logic were interwoven.
* Mutable state: The same object changed meaning across phases.
* Serialization difficulties: Hard to store and reload without cleanup.
* Limited scalability: Parallelization and process isolation were fragile.

## UnresolvedSpec — The Collected Blueprint

`UnresolvedSpec` is created when Canary scans the repository and collects tests.
It describes what might be run but does not yet have dependencies resolved or resources assigned.

Responsibilities

* Produced by test generators.
* Contains parameters, metadata, and dependency patterns.
* Has not yet resolved dependencies.

### ResolvedSpec — The Connected Graph Node

`ResolvedSpec` represents a `UnresolvedSpec` whose dependencies have been resolved into explicit references.

Responsibilities

* Expands dependency patterns into actual `ResolvedSpec` objects.
* Defines a node in the dependency DAG.
* Ready for scheduling but not execution.

Characteristics

* Mutable.
* Graph-aware: Knows its parents and children.
* Context-free: No runtime information.

### TestSpec — The Immutable Execution Recipe

`TestSpec` is the final, fully resolved specification describing what will be executed.
It defines identifiers, parameters, dependencies, and resources, but no execution behavior.

Responsibilities

* Serves as the interface between the planning phase and execution phase.
* Includes all static information needed to run.
* Can be serialized, stored, or distributed to remote sessions.

Characteristics

* Immutable Safe to cache or reuse.
* Declarative No side effects or runtime logic.
* Portable Transmissible across hosts or schedulers.

## TestCase — The Live Execution Context

`TestCase` is created by the session and represents a live, executable instance of a `TestSpec`.
It binds the immutable specification to a workspace, runtime policy, and tracking objects.

```python
from dataclasses import dataclass
from dataclasses import field

@dataclass
class TestCase:
    spec: TestSpec
    workspace: ExecutionSpace
    execution_policy: ExecutionPolicy = field(init=False)
    measurements: Measurements = field(init=False)
    status: Status = field(init=False)
    timekeeper: Timekeeper = field(init=False)

    def setup(self):
        self.workspace.create()
        # prepare inputs, environment, etc.

    def run(self):
        with self.workspace.enter(), self.timekeeper.timeit():
            self.execution_policy.execute(self)

    def teardown(self):
        # cleanup or finalize
        ...
```

Created in the Session

```python
dir = self.work_dir / spec.path
space = ExecutionSpace(dir)
case = TestCase(spec=spec, workspace=space)
```

Attributes

* `spec`: The immutable `TestSpec`.
* `workspace`: An ExecutionSpace that manages directories and artifacts.
* `execution_policy`: Runs the test case
* `measurements`: Tracks resource and performance metrics.
* `status`: Current lifecycle state.
* `timekeeper`: Measures total elapsed time

## Execution Flow

```console
Create workspace
   ↓
Generator collection
   ↓
Unresolved spec creation
   ↓
Unresolved spec resolution
   ↓
Resolved spec
   ↓
Mask / finalize
   ↓
Final spec
   ↓
Cache
   ↓
Done
```

```console
Load workspace
   ↓
Create session
   ↓
Load specs
   ↓
Final filtering of specs
   ↓
Create test cases
   ↓
Run test cases
   ↓
Update latest results
   ↓
Update View
   ↓
Done
```

## How to update existing generators and TestCase subclasses?

### Overview

- Generators should return a list of `UnresolvedSpec` or `ResolvedSpec`
- `TestCase` is no longer subclass-able
- Implement `canary_collectstart` to add test file patterns to search
- Implement `canary_collect_modifyitems` to modify the generator in any way
- Implement `canary_runtest_execution_policy` to define how to run a test
- Implement `canary_runteststart` (optional)
- Implement `canary_runtest_finish` (optional)
