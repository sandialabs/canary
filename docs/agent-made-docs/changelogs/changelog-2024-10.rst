Canary Changelog for 2024-10
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on plugin architecture, documentation, and CI/CD integration. Key changes involved implementing hpc-connect, refactoring the plugin system, adding extensive documentation, and improving the overall codebase structure.

Highlights
----------
- Implemented hpc-connect integration
- Refactored plugin system (commands, reporters, schedulers as plugins)
- Added extensive documentation and examples
- Improved CI/CD configuration
- Added coverage reporting

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (70 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (10 commits)
- Matthew Scot Swan <mswan@sandia.gov> (1 commit)
- Alegra, The Entity <alegra@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Implemented hpc-connect integration
- Added plugin architecture for commands, reporters, and schedulers
- Added coverage MR report
- Added JUnit report generation
- Added source shell script functionality
- Added module loading capability

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added release notes
- Added program flow documentation
- Added design documentation with SVG images
- Added documentation for writing custom reports and commands
- Updated README
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Refactored plugin system (commands, reporters, schedulers as plugins)
- Moved builtin plugins to subdirectories
- Cleaned up plugin interfaces
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Updated CI/CD configuration
- Added linting rules to CI
- Added ruff checking and formatting
- Fixed CI/CD issues
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed vvtest caching
- Fixed CMake environment variable splitting
- Fixed missing vvtest_util objects
- Fixed various plugin-related issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Added -v run argument
- Added nvtest edit functionality
- Improved error handling
- Various improvements to test discovery and execution
- Various code cleanup and improvements
