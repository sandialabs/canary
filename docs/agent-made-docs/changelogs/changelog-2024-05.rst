Canary Changelog for 2024-05
============================

Synopsis
--------
This month included extensive improvements to the Canary project, with a focus on resource management, batch processing, and documentation updates. Key changes involved adding new features like JSON report generation, improving SLURM and PBS integration, and enhancing the overall codebase structure.

Highlights
----------
- Added JSON report generator
- Improved resource management with ResourceHandler
- Enhanced batch processing and partitioning
- Added support for GPU resources
- Extensive documentation updates

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (100 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (4 commits)
- Alegra, The Entity <alegra@sandia.gov> (6 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added JSON report generator
- Added ResourceHandler for streamlined resource handling
- Added support for GPU resources (device -> gpu)
- Added tiling algorithm for partition creation
- Added separate AnalyzeTestCase
- Added nvtest.module.loaded contextmanager
- Added pip proxies support
- Added url property to test case
- Added scalar class for parameter representation
- Added no_cache config setting

Refactoring
~~~~~~~~~~~
- Streamlined resource handling to single ResourceHandler object
- Reworked batch interface
- Moved reporters to builtin plugins
- Completed moving pyt,vvt,ctest to plugins
- Removed unused code and simplified various components
- Updated test:setup API
- Removed case.masked and status.masked in favor of case.mask

Performance
~~~~~~~~~~~
- More optimal batch packing
- Better estimate on queue times
- Improved partitioning algorithms
- Various performance optimizations

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added page on resource usage
- Updated tutorial documentation
- Fixed various docs and typos
- Added more how-to docs

Build and CI
~~~~~~~~~~~~
- Fixed gitlab-ci
- Added sphinx as explicit dependency
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed bug in vvt parsing
- Fixed various batch processing issues
- Fixed resource parsing and handling
- Fixed CDash reporting
- Fixed CTest parsing
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Added support for PBS
- Improved SLURM integration
- Enhanced error handling and logging
- Various improvements to batch processing
- Updated configuration handling
- Various code cleanup and improvements
