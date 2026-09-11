# canary

`canary` is an application testing framework and workflow engine for scientific
software. It finds your tests, figures out how they depend on each other and
what resources they need, then runs them as fast as your hardware allows and
tells you what happened. The same machinery scales from a quick run on a laptop
to thousands of jobs spread across an HPC allocation.

- **Documentation:** https://canary-wm.readthedocs.io
- **Source:** https://github.com/sandialabs/canary

```console
python3 -m pip install canary-wm
canary run ./tests
```

## Heritage

`canary` grows out of [vvtest](https://github.com/sandialabs/vvtest), the test
harness that Sandia teams have relied on for years to test large scientific
codes. vvtest proved out the ideas that matter most: tests are ordinary
scripts, a passing test is one that exits `0`, and a test harness has to
understand real HPC resources instead of pretending every machine is a single
box.

`canary` keeps those ideas and rebuilds around them. It reads vvtest's `.vvt`
files directly, so existing test suites keep working, and it adds a native
Python test format (`.pyt`), a plugin system, a persistent results database,
and first class support for batch schedulers. If you are coming from vvtest, the
mental model is the same and your tests come along with you.

## What it does

Point `canary` at a directory and it will:

1. **Discover** test and job definitions by walking the filesystem.
2. **Generate** concrete jobs from those definitions, expanding parameterized
   tests into the full set of cases.
3. **Resolve** dependencies into an execution graph and match each job against
   the resources it asks for (CPUs, GPUs, nodes).
4. **Schedule and run** the graph with hierarchical parallelism, so independent
   work runs concurrently and dependent work waits only for what it needs.
5. **Record** everything to a queryable results database and render reports.

A "job" does not have to be a test. It can be a simulation, an analysis step, a
data-processing stage, or any other executable unit of work, which is why the
same tool that runs a test suite can also drive an analysis pipeline.

## Why people use it

**It understands HPC.** `canary` models CPUs, GPUs, and nodes as real resources
and packs work onto them accordingly. It can run directly, or submit and manage
batches through Slurm, Flux, and PBS, or fan work out across a distributed pool
of machines.

**Tests are just Python.** A `.pyt` test is a small Python script with a few
directives. You get the entire Python ecosystem for setup, checking, and
analysis, and there is no bespoke DSL to learn.

```python
import canary_pyt

canary_pyt.directives.keywords("fast", "regression")
canary_pyt.directives.parameterize("cpus", [1, 2, 4])


def test():
    # your check here; return nonzero to fail
    return 0
```

**Results stick around and answer questions.** Every run is written to a
persistent workspace and database. You can ask things like "what failed in the
last session," "which jobs ran longer than a minute," or run SQL directly:

```console
canary status
canary query jobs --where status.category==FAIL
canary query session latest --expand-jobs --watch
```

**It fits your toolchain.** Built-in integrations cover CMake/CTest, CDash, and
GitLab CI, so `canary` slots into existing build and continuous-integration
setups instead of replacing them.

**It is extensible.** `canary` is built on [pluggy](https://pluggy.readthedocs.io).
Discovery, generation, scheduling, execution, reporting, and even the
job-definition format are all plugin points. The bundled schedulers and
integrations are themselves plugins and double as worked examples.

## A quick tour

```console
canary run ./tests                 # discover and run everything under ./tests
canary run -k fast ./tests         # only tests tagged "fast"
canary status                      # summarize the most recent run
canary log <job-id>                # show a job's output
canary run -b scheduler=slurm ./tests   # submit as Slurm batches
canary fetch examples && canary run ./examples   # grab the bundled examples
```

See the [user's guide](https://canary-wm.readthedocs.io/en/latest/) for the
full command reference, the directive catalog, resource configuration, and the
plugin API.

## Requirements

Python 3.10 or newer.

## Install

Latest release from PyPI:

```console
python3 -m pip install canary-wm
```

Latest development version from git:

```console
python3 -m pip install "canary-wm@git+https://github.com/sandialabs/canary"
```

Note that the development branch may depend on unreleased versions of its own
dependencies. For reproducible installs, use a published release.

## Developing

Install in editable mode with the development extras:

```console
git clone git@github.com:sandialabs/canary
cd canary
python3 -m pip install --editable .[dev]
```

Before committing, run the internal checks:

```console
canary check
```

`canary check` adds any missing license headers, formats and lints the tree,
type-checks, runs bandit, runs the test suite, and, if everything passes,
stamps `pyproject.toml` with today's date-based version (`YY.M.D`).

### Cutting a release

`main` always depends on `hpc-connect` from git, because `canary` and
`hpc-connect` are developed together. A PyPI release instead pins a published
`hpc-connect` version. `bin/release` prepares a release without touching `main`:

```console
bin/release --hpc-connect 26.9.11
```

It creates a throwaway `releases/<date>` branch, stamps the date-based version,
pins `hpc-connect==<version>`, then validates by running the tests, building the
wheel, installing it into a fresh virtual environment, and running the fetched
examples. On success it commits on the branch and tags `release/<date>`, leaving
`main` untouched. Review, then publish:

```console
git push origin releases/<date> release/<date>
```

Pushing the `release/*` tag triggers the GitHub workflow that uploads to PyPI.

## License

`canary` is distributed under the terms of the MIT license. See `LICENSE` and
`COPYRIGHT` for details.

SPDX-License-Identifier: MIT

SCR#:3170.0
