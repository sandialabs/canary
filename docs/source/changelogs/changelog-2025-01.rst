Canary Changelog for 2025-01
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on plugin architecture, resource management, and various bug fixes. Key changes involved transitioning to pluggy, improving test case masking, and enhancing the overall codebase structure.

Highlights
----------
- Transitioned from custom plugin manager to pluggy
- Improved test case masking and status handling
- Added resource pool functionality
- Enhanced CTest integration
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (60 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (10 commits)
- Mario Vincent LoPrinzi <mvlopri@sandia.gov> (2 commits)
- Stuart Baxley <smbaxle@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Transitioned from custom plugin manager to pluggy
- Added resource pool functionality
- Added Parameters class for parameter validation
- Added post_clean plugin and --post-clean flag
- Added case.defect property

Documentation
~~~~~~~~~~~~~
- Updated documentation for pluggy
- Updated resource_pool tutorial
- Updated various documentation
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Changed name from nvtest to canary
- Improved test case masking logic
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Added psutil to dependencies
- Updated pyproject.toml
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed test case masking when running specific stages
- Fixed various CTest integration issues
- Fixed exit code being returned > 255
- Fixed various plugin-related issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved resource management
- Enhanced test case status handling
- Various improvements to batch processing
- Various code cleanup and improvements
