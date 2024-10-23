# NVTEST

`nvtest` is a python package providing an application testing framework designed to test scientific applications.

- **Documentation:** http://ascic-test-infra.cee-gitlab.lan/nvtest/

 `nvtest` is inspired by [vvtest](https://github.com/sandialabs/vvtest) and designed to run tests on diverse hardware from laptops to super computing clusters.  `nvtest` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension `.pyt` or `.vvt`.  If the exit code upon executing the script is `0`, the test is considered to have passed, otherwise a non-passing status will be assigned.  `nvtest`'s methodology is simple: given a path on the filesystem, `nvtest` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

`nvtest` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.

**Python**: Test files are written in [Python](python.org), giving developers access to the full Python ecosystem.

**Integration**: `nvtest` integrates with popular developer tools like [CMake](cmake.org), [CDash](cdash.org) and [GitLab](gitlab.com), streamlining the testing and continuous integration (CI) processes.

**Extensibility**: `nvtest` can be extended through user plugins, allowing developers to customize their test sessions according to their specific needs.

## Requirements

Python 3.10+

## Install

`nvtest` is distributed as a python library and is most easily installed via `pip` (or other compatible tool):

```console
python3 -m pip install "nvtest git+ssh://git@cee-gitlab.sandia.gov/ascic-test-infra/nvtest"
```

## Developers

For developers wanting to make modifications and/or contributions to `nvtest`, install in editable mode:

```console
python3 -m pip install --editable git+ssh://git@cee-gitlab.sandia.gov/ascic-test-infra/nvtest#egg=nvtest
```

which will leave a copy of `nvtest` in your Python distribution's `$prefix/src` directory.  Edits made to the source will be immediately visible by the Python interpreter.  Alternatively, the source can be cloned and then installed in editable mode:

```console
git clone git@cee-gitlab.sandia.gov:ascic-test-infra/nvtest
cd nvtest
python3 -m pip install --editable .[dev]
```

To run `nvtest`'s internal tests, execute

```console
nvtest self check
```
