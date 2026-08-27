Canary Changelog for 2024-12
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on resource management, batch processing, and documentation. Key changes involved adding resource pools, improving CTest/CDash integration, and enhancing the overall codebase structure.

Highlights
----------
- Added resource pool functionality
- Improved CTest/CDash integration
- Added resource pool tutorial
- Enhanced documentation
- Various performance improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (60 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (10 commits)
- Matthew Mosby <mdmosby@sandia.gov> (1 commit)
- Mario LoPrinzi <mvlopri@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added resource pool functionality
- Added resource limiter
- Added modify_env method to TestCase
- Added git@ and repo@ methods of file search
- Added resource pool tutorial

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added CTest/CDash documentation
- Added copy/link tutorial
- Added more examples and documentation
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Moved to more generalized resource queue
- Made resource_pool its own python module
- Cleaned up variable expansion in test case variables
- Various refactoring improvements

Performance
~~~~~~~~~~~
- Parallelized file search
- Lazily perform setup to speed startup
- Various performance improvements

Build and CI
~~~~~~~~~~~~
- Added -f flag to read config file from command line
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed bug in cdash/json parser
- Fixed various CTest integration issues
- Fixed false positive gitlab report
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Added resource pool configuration
- Improved batch processing
- Enhanced test case management
- Various improvements to CTest/CDash integration
- Various code cleanup and improvements
