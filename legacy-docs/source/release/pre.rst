.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

nvtest 0.0.0 Changelog
======================

.. contents::

Changelog of initial, pre-release, versions of ``nvtest``

October 2024
------------

- Move main repo to https://cee-gitlab.sandia.gov/ascic-test-infra/canary
- Move all plugins into ``_nvtest/plugins``.  This includes commands, reporters, runners, etc.

September 2024
--------------

- Minimum Python version is 3.10
- Removed ``nvtest show`` - use ``nvtest describe``
- move report generators from plugin to their own subdir
- junit writer

August 2024
-----------

- Lots of documentation updates
- ``test:node_count`` resource limit variable

June 2024
---------

- make ``not_run`` status consistent
- add ``help`` subcommand
- setting main config command line options before adding commands to the parser
- validating that the machine config set on the command line is consistent and setting default values for missing machine config vars.

May 2024
--------

- Send CPU and GPU ids to tests.  These are the nvtest internal IDs, not necessarily the hardware IDs
- Create gitlab issues from cdash summary
- Tile tests for optimal batch submission
- Various fixes to CDash generation and posting

April 2024
----------

- Switch to logging module from tty module
- Rerun in batched sessions using the same scheduler used to run
- Add ``Database`` class

March 2024
----------

- Parallelize test setup

January 2024
------------

- Added gitlab plugin that allows posting to gitlab MRs
- variable expansion in config reading/parsing
- Markdown report generator
- Ability to load plugins from entry points
- Added ``nvtest log`` and ``nvtest location`` subcommands
- Misc bug fixes in vvtest translator
- Hierarchical parallelism in batch submissions

December 2023
-------------

- Added ``-l scope:resource=value`` flag to ``nvtest run``
- Auto generate some documents and run commands from within documents and capture output
- Added ``when=`` directive
- Added ``set_attribute`` directive
- Add ``nvtest -p`` plugin flag and move builtin plugins to ``nvtest/plugins``
- run batches with ^batch_no pathspec

November 2023
-------------

- Added ``html`` reporter
- Letting all commands use ``speclike``
- Re-run tests using test id
- Added ``--analyze`` flag
- ``status`` and ``show-log`` subcommands
- Updates to docs
- Adding ``rebaseline`` subcommand
- Bringing in diffing tools from ``vvtk``
- Read tests from file

October 2023
------------

- Adding initial documentation
- Added ``-p`` parameter filter flag to ``nvtest run``

September 2023
--------------

- Use ``mypy`` to type check
- Commands are plugins
- Support for ``vvtest`` ``.vvt`` test files

August 2023
-----------

- Added CDash integration
- Initial commit
