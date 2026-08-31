Canary Changelog for 2025-09
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on security, configuration management, and plugin architecture. Key changes involved hardening security in various components, improving configuration handling, and enhancing the overall codebase structure.

Highlights
----------
- Hardened security in ParameterExpression and ZIP extraction
- Improved configuration management
- Enhanced plugin architecture
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (50 commits)
- Anthony Garland <garland3@gmail.com> (5 commits)
- CI Bot <devnull@example.com> (1 commit)

Detailed Changes
----------------

Security
~~~~~~~~
- Hardened eval in ParameterExpression to prevent code execution
- Safe ZIP extraction for GitLab artifacts to prevent Zip Slip attacks
- Various security improvements

Features
~~~~~~~~
- Added canary_cdash_subproject_label hook
- Added canary_cdash_labels_for_subproject
- Added canary check command
- Added BatchExecutor and BatchConductor setup methods

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Added config documentation
- Various documentation improvements

Build and CI
~~~~~~~~~~~~
- Added security checking with bandit
- Updated CI/CD configuration
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed various security-related issues
- Fixed various configuration-related issues
- Fixed various plugin-related issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved configuration management
- Enhanced plugin architecture
- Various improvements to batch processing
- Various code cleanup and improvements
