Canary Changelog for 2024-09
============================

Synopsis
--------
This month included significant improvements to the Canary project, with a focus on test case management, reporting, and documentation. Key changes involved adding JUnit report generation, improving test case handling, and enhancing the overall codebase structure.

Highlights
----------
- Added JUnit report writer
- Improved test case management with TestMultiCase
- Enhanced documentation
- Added session setup plugin

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (30 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added JUnit report writer
- Added TestMultiCase and MultiParameters
- Added implicit_keywords method
- Added session setup plugin
- Added execute method to analyze and verify pattern

Documentation
~~~~~~~~~~~~~
- Updated documentation
- Added test case documentation
- Reorganized docs
- Updated doc links
- Various documentation improvements

Refactoring
~~~~~~~~~~~
- AnalyzeTestCase -> TestMultiCase
- Moved report generators from plugin to their own subdir
- Reduced size of test state dumps
- Various refactoring improvements

Build and CI
~~~~~~~~~~~~
- Minimum version is now Python 3.10
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Fixed test generator factory to use __init_subclass__
- Fixed datetime UTC to work with older Python
- Fixed various test case handling issues
- Various other bug fixes

Other Changes
~~~~~~~~~~~~~
- Test case object can be loaded and updated from a dump
- Use testcase.lock for test cases
- Better checking if queued values should be skipped
- Remove pickles
- Save session after running
- Various improvements and updates
