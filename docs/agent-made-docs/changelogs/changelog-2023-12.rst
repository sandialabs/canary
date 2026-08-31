Canary Changelog for 2023-12
============================

Synopsis
--------
This month included extensive improvements to the Canary project, with a focus on documentation, bug fixes, and new features. Key changes involved adding CHANGELOG, improving CI/CD configuration, adding new directives, and enhancing the overall codebase structure.

Highlights
----------
- Added CHANGELOG
- Extensive documentation updates and auto-generation
- Added new directives (when, set_attribute)
- Improved CI/CD configuration
- Added coverage plugin
- Added CDash summary reporter

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (60 commits)
- Timothy Jesse Fuller <tjfulle@sandia.gov> (3 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added CHANGELOG
- Added coverage plugin (still doesn't fully work)
- Added CDash summary reporter
- Added commands subcommand
- Added set_attribute callback
- Added when= directive
- Added separate directive files
- Added inline documentation
- Added -l resource switch to nvtest run
- Added --build-stamp input

Documentation
~~~~~~~~~~~~~
- Extensive documentation updates
- Auto generate docs
- Move more docs to source for autogeneration
- Better autogenerate
- Update config docs
- Update getting_started documentation
- Various doc fixes and improvements

Refactoring
~~~~~~~~~~~
- Move structures.py to parameter_set.py
- Remove abstractparameterset
- Remove directives.match
- Replace try/except with if
- Remove self argument from devices directive
- Bug fix in preload directive
- Move from skip/result to status

Build and CI
~~~~~~~~~~~~
- Update CI settings
- Update .gitlab-ci.yml
- Add pytest to test packages
- Test each push
- Fix rst file generation
- Update help
- Various CI/CD improvements

Bug Fixes
~~~~~~~~~
- Lots of bug fixes
- Fixes to running with slurm
- Fixes to run some alegra tests
- Fix batch running
- Fixing unit tests
- Fix how keyword expressions are used when freezing the test session
- Fix nvtest run command
- Various other fixes

Other Changes
~~~~~~~~~~~~~
- Remove cpu_count in favor of avail_cpus
- Be sure to not load local config in session
- Update setup.cfg
- Add stub cdash doc
- Add build/source directories to build config schema
- Add plugin argparsing
- Update nvtest.cmake for allowing different mpiexec
- Add -p plugin command line and move builtin plugins
- Run batches with ^batch_no pathspec
- Centered parameter space
- Clean up function order
- Change mark -> directive
- Fixup nvtest.cmake
- Cleanup report interface
- Remove debug print
- Update batch.py
- Remove unneeded paths.py
- Only use yaml if needed
- Update ignores
- Move more docs to autogen
- Ignore generated
- Fix pre-commit issues
- Cleanup some docs
- Misc fixups
