.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.run:

canary run
==========

Find and run tests from a pathspec

.. code-block:: console

   usage: canary run [-w] [-f file] [-o option] [-k expression] [--owner OWNERS] [-p expression] [--regex regex]
                     [--tag TAG] [--only {all,changed,failed,not_pass,not_run}] [--fail-fast] [-P {permissive,pedantic}]
                     [--copy-all-resources] [--empty-ok] [-s CONSOLE_STYLE] [--view key=value] [--workers N]
                     [--timeout type=T] [--no-incremental] [-h] [-R] [-a] [-b option=value] [--hpc-backend BACKEND]
                     [--hpc-submit-arg ARGS] [--hpc-batch-spec SPEC] [--hpc-batch-workers WORKERS]
                     [--hpc-batch-timeout-strategy STRATEGY] [--hpc-batch-exact-estimate] [--ctest-config cfg]
                     [--ctest-resource-spec-file FILE] [--recurse-ctest] [--output-on-failure] [--show-excluded-tests]
                     [--oversubscribe TYPE=N] [--no-summary] [--durations N] [--teardown] [--show-capture [{o,e,oe,no}]]
                     [--repeat-until-pass N] [--repeat-after-timeout N] [--repeat-until-fail N] [--mail-to MAIL_TO]
                     [--mail-from MAIL_FROM] [--archive NAME] [--report {html,markdown,junit,json,none}]
                     ...
   
   Find and run tests from a pathspec
   
   positional arguments:
     pathspec [--] [user args...]
                           Test file[s] or directories to search. See 'canary help --pathspec' for help on the path specification
   
   options:
     -w                    Remove test execution directory, if it exists [default: None]
     -f file               Read test paths from a json or yaml file. See 'canary help --pathfile' for help on the file schema
     --only {all,changed,failed,not_pass,not_run}
                           Which tests to run after selection
                           all - run all selected tests, even if already passing
                           failed - run only previously failing tests
                           not_run - run tests that have never been executed
                           changed - run tests that whose specs have newer modification time
                           not_pass - run tests whose status is not 'SUCCESS' (default)
     --fail-fast           Stop after first failed test [default: None]
     -P, --parsing-policy {permissive,pedantic}
                           If pedantic (default), stop if file parsing errors occur, else ignore parsing errors
     --copy-all-resources  Do not link resources to the test directory, only copy [default: None]
     --empty-ok            Exit normally when the test set is empty. By default, an empty test set is an error (exit code 7)
     -s, --style CONSOLE_STYLE
                           Configure live console display style. Given as key=value pairs:
                           live={yes,no}[yes]: live console updating
                           name={short,long}[short]: print short (default) names or long
                           
   
     --view key=value      Configure the results view. Given as comma separated key=value pairs:
                           • mode={symlink,hardlink,copy,none}[symlink]: how to create the view
                           • only={all,failed,not_pass,passed}[all]: which tests to include
                           • when={on_success,on_failure,always,never}[always]: when to create the view
     -h, --help            Show this help message and exit.
   
   test spec generation:
     -o option             Turn option(s) on, such as '-o dbg' or '-o intel'
   
   test spec selection:
     -k expression         Restrict selection to tests matching expression. For example: `-k 'key1 and not key2'`. The keyword ``:all:`` matches all tests
     --owner OWNERS        Restrict selection to tests owned by 'owner'
     -p expression         Restrict selection to tests matching the paramter expression. For example: '-p cpus=8' or '-p cpus<8'
     --regex regex         Restrict selection to tests containing the regular expression regex in at least 1 of its file assets. regex is a python regular expression, see
                           https://docs.python.org/3/library/re.html
     --tag TAG             Name this selection 'tag'
   
   console reporting:
     --show-excluded-tests
                           Show names of tests that are excluded from the test session False
     --no-summary          Disable summary [default: False]
     --durations N         Show N slowest test durations (N<0 for all)
     --show-capture [{o,e,oe,no}]
                           Show captured stdout (o), stderr (e), or both (oe) for failed tests [default: no]
   
   resource control:
     --workers N           Execute the test session asynchronously using a pool of at most N workers
     --timeout type=T      Set the timeout for **type** (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s).
                           • type=**session**, the timeout T is applied to the entire test session.
                           • type=**multiplier**, the multiplier T is applied to each test's timeout.
                           • type=**all**, the timeout T is applied to all jobs.
                           Otherwise, a timeout of T is applied to tests having keyword **type**. Eg, **--timeout fast=2** would apply a timeout of 2 seconds to all tests having the 'fast' keyword;
                           common types are fast, long, default, and ctest.
     --no-incremental      Don't use the .canary_cache to infer job runtimes
     --oversubscribe TYPE=N
                           Apply the multiplier N to the number of slots available per resource instance of type TYPE
   
   vvtest options:
     -R                    Rerun tests. Normally tests are not run if they previously completed.
     -a, --analyze         Only run the analysis sections of each test. Note that a test must be written to support this option (using the vvtest_util.is_analysis_only flag) otherwise the whole test is
                           run.
   
   canary hpc:
     -b option=value       Short cut for setting batch options.
     --hpc-backend, --scheduler BACKEND
                           Submit batches to this HPC scheduler [alias: -b backend=BACKEND] [default: None]
     --hpc-submit-arg, --scheduler-args ARGS
                           Comma separated list of options to pass directly to the scheduler [alias: -b options=ARGS]
     --hpc-batch-spec SPEC
                           Comma separated list of options to partition jobs into batches. See canary batch help --spec for help on batch specification syntax [alias: -b spec=SPEC]
     --hpc-batch-workers WORKERS
                           Run jobs in batches using WORKERS workers [alias: -b workers=WORKERS]
     --hpc-batch-timeout-strategy STRATEGY
                           Estimate batch runtime (queue time) conservatively or aggressively [alias: -b timeout=STRATEGY] [default: aggressive]
     --hpc-batch-exact-estimate
                           After forming batches with cheap schedule estimates, run an exact scalar scheduler simulation once per final batch to refine the stored runtime estimate. This is slower for
                           very large suites.
   
   ctest options:
     --ctest-config cfg    Choose configuration to test
     --ctest-resource-spec-file FILE
                           Set the resource spec file to use.
     --recurse-ctest       Recurse CMake binary directory for test files. CTest tests can be detected from the root CTestTestfile.cmake, so this is option is not necessary unless there is a mix of
                           CTests and other test types in the binary directory
     --output-on-failure   Alias for --show-capture
   
   plugin options:
     --teardown, --post-clean
                           Clean up files created by a test if it finishes successfully [default: None]
     --mail-to MAIL_TO     Send a test session summary to the comma separated list of email addresses
     --mail-from MAIL_FROM
                           Send mail from this user
     --archive NAME        Archive job artifacts to a tgz archive by this name
     --report {html,markdown,junit,json,none}
                           Write final report in this format [default: none]
   
   repeat:
     --repeat-until-pass N
                           Allow each test to run up to N times in order to pass
     --repeat-after-timeout N
                           Allow each test to run up to N times if it times out
     --repeat-until-fail N
                           Require each test to run N times without failing in order to pass
   
   See canary help --pathspec for help on the path specification
