Canary Changelog for 2023-08
============================

Synopsis
--------
This month included the initial commit and setup of the Canary project, along with various bug fixes and enhancements. Key changes involved adding plugins, fixing issues found during test suite execution, and setting up pre-commit hooks.

Highlights
----------
- Initial commit and project setup
- Added LLVM plugin
- Added CDash writer functionality
- Fixed bugs found running Alegra test suite
- Set up pre-commit hooks

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (13 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (2 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added LLVM plugin
- Added CDash writer functionality

Bug Fixes
~~~~~~~~~
- Fixed status printer
- Fixed when params are written to vvtest_util
- Fixed when blacklist plugin is called
- Fixed how vvtest params are written out
- Fixed bugs found running Alegra test suite

Other Changes
~~~~~~~~~~~~~
- Initial commit
- Pre-commit setup
- Juggled location of commands
- Added files that were ignored
