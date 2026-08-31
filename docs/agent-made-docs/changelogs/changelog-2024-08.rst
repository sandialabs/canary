Canary Changelog for 2024-08
============================

Synopsis
--------
This month included various improvements to the Canary project, with a focus on documentation, configuration updates, and new features. Key changes involved adding contributing guidelines, improving output level handling, and enhancing the overall codebase structure.

Highlights
----------
- Added CONTRIBUTING.md
- Added self subcommand
- Added help subcommand
- Improved documentation
- Enhanced configuration handling

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (25 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added CONTRIBUTING.md
- Added self subcommand
- Added help subcommand
- Added outputlevel enum
- Added test:node_count resource limit variable

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Added documentation for testcase and baseline
- Added more inline docs
- Updated testfile and session to include images
- Cleanup testfile graphic
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Made outputlevel a class
- Consistent use of cpus/gpus/processors
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Updated .gitlab-ci to build docs when images change
- Cleaning up pyproject.toml
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed nvtest find to properly filter tests
- Fixed ctest test
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Batch scheduler can be path to sbatch, qsub, etc.
- Added dependency parameters to analyze test instances
- Added instance test
- Set min cpu_count to 1 when parsing from command line
- Treat nnode parameter as number of nodes
- Various improvements and updates
