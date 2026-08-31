Canary Changelog for 2025-04
============================

Synopsis
--------
This month included various improvements to the Canary project, with a focus on logging, error handling, and performance. Key changes involved adding stderr output to canary log, improving Markdown reports, and enhancing the overall codebase structure.

Highlights
----------
- Added stderr output to canary log
- Improved Markdown reports
- Enhanced error handling
- Various performance improvements

Authors
-------
- Matthew Mosby <mdmosby@sandia.gov> (15 commits)
- Tim Fuller <tjfulle@sandia.gov> (10 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (5 commits)
- Matthew Scot Swan <mswan@sandia.gov> (5 commits)
- Mario Vincent LoPrinzi <mvlopri@sandia.gov> (2 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added stderr output to canary log
- Improved Markdown reports with error output
- Added functionality to not split XML into chunks
- Added canary_addopts envar check

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Fixed various documentation issues
- Various documentation improvements

Performance
~~~~~~~~~~~
- Speed up canary location by not loading entire session
- Various performance improvements

Bug Fixes
~~~~~~~~~
- Fixed parsing issue as described in #80
- Fixed various error handling issues
- Fixed various logging issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved error handling for corrupt lock files
- Enhanced resource pool pinfo functionality
- Various improvements to batch processing
- Various code cleanup and improvements
