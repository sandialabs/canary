Canary Changelog for 2023-11
============================

Synopsis
--------
This month included extensive documentation updates, new features like HTML reporter and rebaseline command, and various improvements to the Canary project. Key changes involved adding new commands, improving configuration handling, and enhancing documentation.

Highlights
----------
- Added HTML reporter functionality
- Added rebaseline command
- Added parallel nvtest support
- Added --analyze flag
- Extensive documentation updates

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (50 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added HTML reporter
- Added rebaseline command
- Added parallel nvtest support
- Added --analyze flag
- Added python subcommand
- Added max-cores-per-test argument

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added CMake instructions
- Updated README
- Updated getting_started documentation
- Various doc fixes and improvements

Refactoring
~~~~~~~~~~~
- Made config a singleton
- Moved vendored libraries to src/_nvtest/third_party
- Changed batch running to launch shell script directly
- Use set instead of list in Finder tree

Build and CI
~~~~~~~~~~~~
- Added build configuration
- New mypy updates
- Pre-commit updates

Bug Fixes
~~~~~~~~~
- Fixed HTML reporter
- Fixed regex issues
- Fixed how paths are read from path file
- Fixed case where trying to rerun in exec directory
- Various other fixes

Other Changes
~~~~~~~~~~~~~
- Added more color to console output
- Updated console output formatting
- Added new status and show-log commands
- Various updates and improvements
