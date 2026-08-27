Canary Changelog for 2025-03
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on licensing, CI/CD integration, and various bug fixes. Key changes involved adding proper licensing to all source files, improving Flux integration, and enhancing the overall codebase structure.

Highlights
----------
- Added proper licensing to all source files
- Improved Flux integration
- Enhanced CI/CD configuration
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (50 commits)
- Matthew Mosby <mdmosby@sandia.gov> (15 commits)
- Mario Vincent LoPrinzi <mvlopri@sandia.gov> (10 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (5 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added proper licensing to all source files
- Added configurable multiprocessing context
- Added backdoor to hardcode number of nodes wanted
- Added functionality to not split XML into chunks

Documentation
~~~~~~~~~~~~~
- Updated documentation to mention Flux and PBS schedulers
- Updated release notes
- Various documentation improvements

Build and CI
~~~~~~~~~~~~
- Updated CI/CD configuration
- Updated CI to get resources from Flux backend
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed CTest test files and project directories finding
- Fixed various Flux integration issues
- Fixed CDash documentation
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Updated hpc-connect API interface
- Improved resource management
- Enhanced test case handling
- Various improvements to batch processing
- Various code cleanup and improvements
