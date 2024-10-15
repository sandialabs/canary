# CHANGE LOG

## Oct 2024

- Move all plugins into `_nvtest/plugins`.  This includes commands, reporters, runners, etc.

## Sep 2024

- Minimum Python version is 3.10
- Removed `nvtest show` - use `nvtest describe`
- move report generators from plugin to their own subdir
- junit writer

## Aug 2024

- Lots of documentation updates
- `test:node_count` resource limit variable

## Jun 2024

- make `not_run` status consistent
- add `help` subcommand
- setting main config command line options before adding commands to the parser
- validating that the machine config set on the command line is consistent and setting default values for missing machine config vars.

## May 2024

- Send CPU and GPU ids to tests.  These are the nvtest internal IDs, not necessarily the hardware IDs
- Create gitlab issues from cdash summary
- Tile tests for optimal batch submission
- Various fixes to CDash generation and posting

## Apr 2024

- Switch to logging module from tty module
- Rerun in batched sessions using the same scheduler used to run
- Add `Database` class

## Mar 2024

- Parallelize test setup

## Jan 2024

- Added gitlab plugin that allows posting to gitlab MRs
- variable expansion in config reading/parsing
- Markdown report generator
- Ability to load plugins from entry points
- Added `nvtest log` and `nvtest location` subcommands
- Misc bug fixes in vvtest translator
- Hierarchical parallelism in batch submissions

## Dec 2023

- Added `-l scope:resource=value` flag to `nvtest run`
- Auto generate some documents and run commands from within documents and capture output
- Added `when=` directive
- Added `set_attribute` directive
- Add `nvtest -p` plugin flag and move builtin plugins to `nvtest/plugins`
- run batches with ^batch_no pathspec

## Nov 2023

- Added `html` reporter
- Letting all commands use `speclike`
- Re-run tests using test id
- Added `--analyze` flag
- `status` and `show-log` subcommands
- Updates to docs
- Adding `rebaseline` subcommand
- Bringing in diffing tools from `vvtk`
- Read tests from file

## Oct 2023

- Adding initial documentation
- Added `-p` parameter filter flag to `nvtest run`

## Sep 2023

- Use `mypy` to type check
- Commands are plugins
- Support for `vvtest` `.vvt` test files

## Aug 2023

- Added CDash integration
- Initial commit
