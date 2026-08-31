Canary Changelog for 2024-11
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on CTest integration, batching improvements, and various bug fixes. Key changes involved adding new batching schemes, improving CTest parsing, and enhancing the overall codebase structure.

Highlights
----------
- Added isolate batching scheme
- Improved CTest parsing and integration
- Added changelog command
- Enhanced documentation
- Various bug fixes and improvements

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (70 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (10 commits)
- Matthew Scot Swan <mswan@sandia.gov> (3 commits)
- Alegra, The Entity <alegra@sandia.gov> (1 commit)

Detailed Changes
----------------

Features
~~~~~~~~
- Added isolate batching scheme (use -l batch:scheme=isolate)
- Added changelog command
- Added email-after plugin
- Added measurements and info command
- Added dont-measure flag to nvtest run

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Added documentation for CTest features
- Added documentation for vvt include directive
- Added more usage docs
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- Replaced custom config dictionary with dataclasses.dataclass
- Moved test case filtering logic from generator to finder
- Converted Optional[type] to type | None
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Updated CI/CD configuration
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed CTest parsing errors with newline characters
- Fixed vvtest caching
- Fixed various CTest integration issues
- Fixed bug in generate_version
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Improved CTest parsing to read Trilinos tests
- Added support for more CTest properties
- Improved vvtest parameterize support
- Added include directive support
- Various improvements to batching and resource handling
- Various code cleanup and improvements
