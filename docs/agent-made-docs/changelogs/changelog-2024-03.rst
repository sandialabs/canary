Canary Changelog for 2024-03
============================

Synopsis
--------
This month included performance improvements and various fixes to the Canary project. Key changes involved parallelizing operations, optimizing file parsing, and improving SLURM integration.

Highlights
----------
- Parallelized freeze and file loading operations
- Improved performance through caching and profiling
- Fixed SLURM option parsing
- Better printing of run status

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (12 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (1 commit)

Detailed Changes
----------------

Performance
~~~~~~~~~~~
- Parallelized freeze operation
- Parallelized file loading
- Caching evaluation results to speed up file parsing
- Profiled code and removed some hotspots

Features
~~~~~~~~
- Install NVTest.cmake
- Better parsing of baseline type

Build and CI
~~~~~~~~~~~~
- Fixed .gitlab-ci.yml
- Updated .gitlab-ci.yml
- Moved tests to root directory

Bug Fixes
~~~~~~~~~
- Fixed which tests are printed with find
- Fixed SLURM option parsing
- Removed empty batches
- Don't delete session directory if it already exists

Other Changes
~~~~~~~~~~~~~
- Simplified when expression parsing
- Better printing of run status
- Various improvements and fixes
