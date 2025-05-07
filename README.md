# CANARY

`canary` is a python package providing an application testing framework designed to test scientific applications.

- **Documentation:** https://canary-wm.readthedocs.io/en/production/

 `canary` is inspired by [vvtest](https://github.com/sandialabs/vvtest) and designed to run tests on diverse hardware from laptops to super computing clusters.  `canary` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension `.pyt` or `.vvt`.  If the exit code upon executing the script is `0`, the test is considered to have passed, otherwise a non-passing status will be assigned.  `canary`'s methodology is simple: given a path on the filesystem, `canary` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

`canary` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.

**Python**: Test files are written in [Python](python.org), giving developers access to the full Python ecosystem.

**Integration**: `canary` integrates with popular developer tools like [CMake](cmake.org), [CDash](cdash.org) and [GitLab](gitlab.com), streamlining the testing and continuous integration (CI) processes.

**Extensibility**: `canary` can be extended through user plugins, allowing developers to customize their test sessions according to their specific needs.

## Requirements

Python 3.10+

## Install

`canary` is distributed as a python library and is most easily installed via `pip` (or other compatible tool):

To install the latest development version, execute:

```console
python3 -m pip install "canary-wm git+ssh://git@github.com/sandialabs/canary"
```

To install the latest production version, execute:

```console
python3 -m pip install canary-wm
```

## Developers

For developers wanting to make modifications and/or contributions to `canary`, install in editable mode:

```console
python3 -m pip install -e git+https://github.com/sandialabs/canary#egg=canary-wm[dev]
```

which will leave a copy of `canary` in your Python distribution's `$prefix/src` directory.  Edits made to the source will be immediately visible by the Python interpreter.  Alternatively, the source can be cloned and then installed in editable mode:

```console
git clone git@github.com:sandialabs/canary
cd canary
python3 -m pip install --editable .[dev]
```

To format code and run `canary`'s internal tests, execute

```console
./bin/pre-commit
```

## License

https://github.com/matmodlab/matmodlab2/blob/master/LICENSE
Canary is distributed under the terms of the MIT license, see [LICENSE](https://github.com/sandialabs/canary/blob/main/LICENSE) and [COPYRIGHT](https://github.com/sandialabs/canary/blob/main/COPYRIGHT).

SPDX-License-Identifier: MIT

SCR#:3170.0
