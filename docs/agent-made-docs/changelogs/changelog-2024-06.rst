Canary Changelog for 2024-06
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on database integration, batch processing, and various bug fixes. Key changes involved adding SQLite database support, improving resource handling, and enhancing the overall codebase structure.

Highlights
----------
- Added SQLite database integration
- Improved batch processing and resource handling
- Enhanced CTest parsing
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (30 commits)
- Flexo, The Entity <flexo@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added SQLite database support
- Added database test
- Added cloudpickle.py
- Added support for ``*.nvtest.py`` files
- Added replace flag to db.put

Refactoring
~~~~~~~~~~~
- Removed batchsetter in favor of resourcesetter
- Cleaned up sqlite3 interfaces
- Abstracted out nvtest invocation line from batched tests
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Added ruff checking
- Precommit updates
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed typo in issue generator
- Fixed issue creator
- Fixed wrong argument in call to create_issues_from_cdash
- Fixed various batch processing issues
- Fixed CTest parsing
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved database handling with file locks
- Enhanced resource handling
- Better concurrency detection in SQLite connection
- Various improvements to batch processing
- Documentation updates
- Various code cleanup and improvements
