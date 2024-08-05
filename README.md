# NVTEST

`nvtest` is an application testing framework designed to test scientific applications. `nvtest` is inspired by [vvtest](https://github.com/sandialabs/vvtest) and designed to run tests on diverse hardware from laptops to super computing clusters.  `nvtest` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension `.pyt` or `.vvt`.  If the exit code upon executing the script is `0`, the test is considered to have passed, otherwise a non-passing status will be assigned.  `nvtest`'s methodology is simple: given a path on the filesystem, `nvtest` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

`nvtest` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.

**Python**: Test files are written in [Python](python.org), giving developers access to the full Python ecosystem.

**Integration**: `nvtest` integrates with popular developer tools like [CMake](cmake.org), [CDash](cdash.org) and [GitLab](gitlab.com), streamlining the testing and continuous integration (CI) processes.

**Extensibility**: `nvtest` can be extended through user plugins, allowing developers to customize their test sessions according to their specific needs.

## Requirements

Python 3.10+

## Install

### Default

```console
pip install "nvtest git+ssh://git@cee-gitlab.sandia.gov/alegra/tools/nvtest"
```

### Developers

```console
git clone git@cee-gitlab.sandia.gov:alegra/tools/nvtest
cd nvtest
pip install -e .[dev]
```

## Documentation

- [website](http://alegra.cee-gitlab.lan/tools/nvtest/)
- [documentation source](./docs/source/index.rst)
