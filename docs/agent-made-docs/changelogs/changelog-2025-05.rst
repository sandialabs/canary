Canary Changelog for 2025-05
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on GitHub integration, documentation, and various bug fixes. Key changes involved adding GitHub workflows, improving CDash integration, and enhancing the overall codebase structure.

Highlights
----------
- Added GitHub workflows
- Improved CDash integration
- Enhanced documentation
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (30 commits)
- Stuart Baxley <smbaxle@sandia.gov> (3 commits)
- Matthew Scot Swan <mswan@sandia.gov> (3 commits)
- Ben Wibking <ben@wibking.com> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added GitHub workflows
- Added --show-capture to print test stdout/stderr
- Added TestCase.format method
- Added cdash-link to test URL

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Added ReadTheDocs configuration
- Updated URLs to reflect GitHub
- Various documentation improvements

Build and CI
~~~~~~~~~~~~
- Added initial GitHub workflow
- Updated CI/CD configuration
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed bug in batch_view where cases were not run
- Fixed various CDash integration issues
- Fixed various GitHub integration issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Removed TestCase._mask and _defect attributes
- Improved test case status handling
- Enhanced CDash XML reporting
- Various improvements to batch processing
- Various code cleanup and improvements
