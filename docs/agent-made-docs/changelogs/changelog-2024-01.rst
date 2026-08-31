Canary Changelog for 2024-01
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on adding new features, improving documentation, and enhancing the overall functionality. Key changes involved adding GitLab integration, markdown reporting, analyze subcommand, and various bug fixes.

Highlights
----------
- Added GitLab plugin and integration
- Added markdown report generator
- Added analyze subcommand
- Added code coverage files
- Improved sorting and organization

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (50 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added GitLab plugin
- Added markdown report generator
- Added analyze subcommand
- Added code coverage files
- Added ability to load plugins from entry points
- Added separate log and location commands
- Added -l resource switch to nvtest run
- Added --build-stamp input
- Added console command instructions for analyze

Documentation
~~~~~~~~~~~~~
- Updated URLs in README
- Updated inline docs
- Various documentation improvements

Build and CI
~~~~~~~~~~~~
- Fixed CI/CD tags
- Entry points should also work for Python 3.9
- Fixed SCM versioning
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed loading builtin plugins
- Fixed CDash test
- Fixed posting of CDash files
- Fixed batch running
- Fixed some type checking
- Fixed when test for older Python
- Bug fix in vvtest translator
- Various other fixes

Refactoring
~~~~~~~~~~~
- Refactored `when` and added tests
- Consolidated session creation and initialization
- Separated session.create and setup functions
- Made keyboard interrupt work
- Various refactoring improvements

Other Changes
~~~~~~~~~~~~~
- Strip quotes when reading string variables from configuration
- Sort strings lower
- Sort by name in markdown report
- Make variables available for expansion in other config sections
- Ignore pip build directory
- Don't use JSON for reading vvt files
- Write out config like TOML
- Use ruff instead of black/flake8/isort
- Various other improvements and updates
