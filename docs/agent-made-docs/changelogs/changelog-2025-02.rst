Canary Changelog for 2025-02
============================

Synopsis
--------
This month included various improvements to the Canary project, with a focus on batching, documentation, and module handling. Key changes involved moving batching to a plugin, adding new module commands, and enhancing the overall codebase structure.

Highlights
----------
- Batching moved to a plugin
- Added purge and use module commands
- Enhanced documentation
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (15 commits)
- Mario Vincent LoPrinzi <mvlopri@sandia.gov> (4 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (2 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Batching moved to a plugin
- Added purge and use module commands
- Added logfile command for test instance
- Added configurable multiprocessing context

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Fixed various documentation issues
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Replaced variables config with environment modification config
- Various refactoring improvements

Bug Fixes
~~~~~~~~~
- Fixed CTest test files and project directories finding for symlinks
- Fixed gitlab report subparser setup
- Fixed various module-related issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Load multiple modules at a time
- Use default_factory for mutable config variable
- Various improvements to batch processing
- Various code cleanup and improvements
