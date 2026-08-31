Canary Changelog for 2024-04
============================

Synopsis
--------
This month included extensive improvements to the Canary project, with a focus on refactoring, performance improvements, and documentation updates. Key changes involved removing the tty module, adding parallel processing capabilities, improving SLURM integration, and enhancing error handling.

Highlights
----------
- Removed tty module and replaced with logging
- Added parallel processing module
- Improved SLURM interface
- Added Database class for better data management
- Extensive documentation updates and fixes

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (60 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (6 commits)
- Dan Ibanez <daibane@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added parallel processing module
- Added Database class
- Can now rerun batched tests
- Added active cases property
- Added art package

Refactoring
~~~~~~~~~~~
- Removed tty module and replaced with logging
- Redid SLURM interface
- Moved session code from run and status to session
- Plugins -> builtin_plugins
- Replaced queue with queues.py
- Ready -> buffer
- Cleaned up partition creation
- Finished removal of tty

Performance
~~~~~~~~~~~
- Parallelized freeze operation
- Parallelized file loading
- Caching evaluation results to speed up file parsing
- Profiled code and removed some hotspots

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added more how-to docs
- Fixed typos in docs
- Updated help messages
- Added examples

Build and CI
~~~~~~~~~~~~
- Fixed .gitlab-ci.yml
- Updated project.toml to use version_file instead of write_to
- Changed line length to 99
- Fixed CI/CD tags

Bug Fixes
~~~~~~~~~
- Fixed bug in vvt parsing
- Fixed case error that passes on Darwin but not Linux
- Fixed mypy error
- Fixed some example tests
- Fixed cmake integration tests
- Fixed errors in call to executable from rprobe
- Various other fixes

Other Changes
~~~~~~~~~~~~~
- Dynamic version handling
- Better error messages
- Improved logging
- Removed unused variables
- Cleaned up to_seconds function
- Added vvtest parsing test
- Removed python 3.10 syntax
- Various improvements and updates
