Canary Changelog for 2024-07
============================

Synopsis
--------
This month included various improvements to the Canary project, with a focus on resource management, scheduler integration, and documentation updates. Key changes involved adding support for PBS and Flux schedulers, improving GPU resource handling, and enhancing the overall codebase structure.

Highlights
----------
- Added support for PBS and Flux schedulers
- Improved GPU resource handling
- Added heartbeat file
- Enhanced documentation

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (20 commits)
- Dan Ibanez <daibane@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added support for PBS and Flux schedulers
- Added heartbeat file
- Added -e argument to run and pre-commit subcommand
- Added shell.source method to change environment
- Added howto:rerun documentation

Refactoring
~~~~~~~~~~~
- Generalized setting of environment variables
- Fixed how/when machine config variables are set
- Various refactoring improvements

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Added documentation on setting resources
- Made note about directives stand out more
- Various documentation improvements

Bug Fixes
~~~~~~~~~
- Fixed comparison of resources required to resources needed
- Fixed paths printed to screen for empty path case
- Fixed bug associated with sending arguments to batch scheduler
- Fixed typo in environ.rt
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Allow tests to request gpus=n:N
- Added cpu_ids and gpu_ids to test instance
- Put heartbeat file in log directory
- Include start and finish in summary and status
- Allow timeout <=0 to mean no timeout
- Various improvements and updates
