Canary Changelog for 2025-08
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on configuration management, CDash integration, and various bug fixes. Key changes involved replacing dataclass configuration with dictionary-based configuration, improving CDash reporting, and enhancing the overall codebase structure.

Highlights
----------
- Replaced dataclass configuration with dictionary-based configuration
- Improved CDash integration
- Enhanced timeout handling
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (30 commits)
- Alex Knigge <amknigg@sandia.gov> (5 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Replaced dataclass configuration with dictionary-based configuration
- Added --subproject-labels switch to CDash report creation
- Added --done switch to cdash post
- Added canary check command

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Various documentation improvements

Build and CI
~~~~~~~~~~~~
- Added Dockerfile for dev container
- Updated CI/CD configuration
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed various configuration-related issues
- Fixed various CDash integration issues
- Fixed various timeout handling issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved configuration management
- Enhanced CDash reporting
- Various improvements to batch processing
- Various code cleanup and improvements
