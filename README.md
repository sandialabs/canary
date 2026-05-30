# CANARY

`canary` is a Python package for defining, scheduling, and executing jobs across a wide range of computing environments, from developer laptops to large-scale HPC systems.

- **Documentation:** https://canary-wm.readthedocs.io/en/production/


Originally developed for application testing, `canary` has evolved into a general-purpose workflow execution framework. Today it is used to automate software testing, manage analysis workflows, execute computational pipelines, and coordinate collections of dependent jobs.


`canary` is inspired by `vvtest` and retains its strengths in scalable test execution while providing a flexible foundation for broader workflow automation. Built on `pluggy`, `canary` uses a plugin-based architecture for job discovery and execution. Common plugins support Python-based job definitions in `.pyt` and `.vvt` files, while others provide integration with frameworks such as CMake/CTest. Given one or more filesystem paths, `canary` recursively discovers job definitions, constructs the execution graph, schedules work according to available resources and dependencies, executes jobs, and reports results.


Testing remains a primary use case, but it is no longer the defining purpose of the project. A `canary` job may represent a software test, simulation, data-processing stage, analysis task, validation check, or any other executable unit of work.


`canary` offers several advantages:


**Scalable Execution**: Hierarchical parallelism enables efficient utilization of available resources, allowing large collections of jobs to execute concurrently across diverse hardware platforms.


**Workflow and Testing**: The same framework supports both automated software testing and general workflow orchestration, reducing the need for separate tools.


**Python-Based Definitions**: Python-based plugins provide access to the full Python ecosystem while enabling concise and expressive workflow descriptions.


**Integration**: `canary` integrates with common development and automation tools such as CMake, CDash, and GitLab, simplifying testing and continuous integration workflows.


**Extensibility**: A plugin architecture allows users to customize discovery, scheduling, execution, reporting, job-definition formats, and other aspects of a `canary` session.


## Requirements

Python 3.10+


## Install

`canary` is distributed as a Python package and is most easily installed using `pip` (or another compatible package manager).


To install the latest production release:

```console
python3 -m pip install canary-wm
```


To install the latest development version:

```console
python3 -m pip install "canary-wm@git+ssh://git@github.com/sandialabs/canary"
```


> **NOTE:** Installing from the main development branch may depend on floating git references in one or more dependencies. For stable installations, use a published release.


## Developers

For developers wishing to modify or contribute to `canary`, install in editable mode:

```console
python3 -m pip install -e git+https://github.com/sandialabs/canary#egg=canary-wm[dev]
```


This places a working copy of the source in your Python distribution's `$prefix/src` directory, allowing changes to become immediately visible to the interpreter.


Alternatively:

```console
git clone git@github.com:sandialabs/canary
cd canary
python3 -m pip install --editable .[dev]
```


To format code and run `canary`'s internal test suite:

```console
canary check
```


## License

Canary is distributed under the terms of the MIT license. See `LICENSE` and `COPYRIGHT` for details.


SPDX-License-Identifier: MIT


SCR#:3170.0