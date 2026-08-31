Canary Changelog for 2023-09
============================

Synopsis
--------
This month included significant refactoring and reorganization of the Canary project, with a focus on improving code structure, adding new features, and enhancing type checking. Key changes involved moving commands to session subclasses, adding TOML configuration, and implementing schema validation.

Highlights
----------
- Refactored commands to be subclasses of session
- Added TOML configuration support
- Added schema validation
- Improved type checking with mypy
- Added unit tests

Authors
-------
- Tim Fuller <tjfulle@sandia.gov> (24 commits)

Detailed Changes
----------------

Features
~~~~~~~~
- Added TOML configuration support
- Added schema validation
- Added unit tests

Refactoring
~~~~~~~~~~~
- Moved commands to session subclasses
- Removed several test sessions in favor of single "run"
- Removed unused io directory
- Environment -> finder refactoring

Build and CI
~~~~~~~~~~~~
- Improved type checking with mypy
- Various mypy fixes and improvements

Other Changes
~~~~~~~~~~~~~
- Some reorganization and fixes
- Updated console logging
- Removed llvm profile plugin
- Removed timeit option
- Run batch dumps its own session.json.n.i
- Use name results.json
