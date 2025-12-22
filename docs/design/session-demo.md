# Session workflow demo

This document outlines the "session" workflow in `canary`.  The idea behind this workflow is that the list of tests are set and associated with a "tag" that simplifies management of test results directories, re-execution, etc.

## Session Concepts

The latest version of `canary` introduces some new concepts to the execution workflow:

  1. initialization
  2. selection
  3. execution

### Initialization

<!-- canary init -h -->
```console
canary init [-h] [path]

Initialize a Canary session

positional arguments:
  path        Initialize session in this directory [default: $(pwd)]

options:
  -w          Wipe any existing session first
  -h, --help  Show this help message and exit.
```

The new initialization step establishes the working location for all subsequent `canary` commands and supports execution from anywhere below the specified `path`.

Once a session is initialized, tests can be added with `canary selection create` as described below:

<!-- canary add -h -->
```console
$ canary selection create -h
usage: canary selection create [-h] [-f file] [-r PATH] [-o option] [-k expression] [--owner OWNERS] [-p expression] [--search regex] tag

options:
  -h, --help            show this help message and exit
  -f file               Read test paths from a json or yaml file. See 'canary help --pathfile' for help on the file schema
  -r PATH               Recursively search PATH for test generators

test spec generation:
  -o option             Turn option(s) on, such as '-o dbg' or '-o intel'

test spec selection:
  -k expression         Only run tests matching given keyword expression. For example: `-k 'key1 and not key2'`. The keyword ``:all:`` matches all tests
  --owner OWNERS        Only run tests owned by 'owner'
  -p expression         Filter tests by parameter name and value, such as '-p cpus=8' or '-p cpus<8'
  --search regex, --regex regex
                        Include tests containing the regular expression regex in at least 1 of its file assets. regex is a python regular expression, see
                        https://docs.python.org/3/library/re.html
  tag                   Tag this test case selection for future runs [default: False]

```

`section create` finds test files, generates test specs, applies filters, and creates a named set of tests that can be run by the execution phase.

### Test Execution

```console
canary run [TAG]
```

Under the session workflow, test selection is intended to be done via `selection` and associated with named sets.

> **Request for feedback**: What other workflows need to be supported additionally?

Contrary to the current default behavior of `canary run` outside the session workflow, the full set of tests associated with the tag are executed on each invocation in separate work trees.  The `TestResults` directory is updated to point to the latest results directory in the internal datastore.

## End-to-end walkthrough

This section contains an end-to-end demonstration of the "session" workflow leveraging the `canary` tests/examples for input.

### A first example

We begin by initializing and inspecting a session.

```console
$ canary init
INFO: Initializing empty canary workspace at ...
$ canary info
Workspace:   ...
Version:     25.12.18+28f4bd50
Sessions:    0
Latest:      None
Tags:
$ canary status
```

The `init` subcommand creates a session in the current working directory and reports the path to the session.

`canary info` now reports the session information: location, number of generators, number of sessions/executions, the latest session/execution, and the list of tags.

As we can see, all of these values are zero/empty.  Finally `canary status` shows that there are no tests in the session.

Adding the `examples/basic` directory to the session adds generators, but does not yet generate tests as shown by the empty status.

```console
$ canary selection create -r ./examples/basdic basic
INFO: Collecting generator files from examples/basic... done (0.00s.)
INFO: Instantiating generators from collected files... done (0.81s.)
INFO: Generating test specs from generators... done (0.00s.)
INFO: Searching for duplicated tests
INFO: Resolving test spec dependencies... done (0.00s.)
INFO: Generated 2 test specs from 2 generators
INFO: Caching test specs... done (0.01s.)
INFO: Created selection 'basic'
INFO: To run this selection execute 'canary run basic'
```

Executing `canary run`:

```console
$ canary run basic
...
version: 25.12.18+6e139aa9-dirty
INFO: Running tests in tag basic
INFO: Selecting test cases based on runtime environment... done (0.00s.)
INFO: Starting session 2025-12-18T13-23-40.035876
INFO: Starting process pool with max 9 workers
INFO: 2/2 tests finished with status PASS
INFO: Finished session in 2.12 s. with returncode 0
INFO: Updating view at /opt/alegranevada/team/x/macos/src/canary/TestResults
```

Invoking `canary run` again, skips these steps and runs cases that did not previously finish.

```console
version: 25.12.18+6e139aa9-dirty
INFO: Running tests in default tag :all:
INFO: Selecting test cases based on runtime environment... done (0.00s.)
INFO: Excluded 2 test cases

  Reason                      Count
 ───────────────────────────────────
  previous result = SUCCESS       2

ERROR: no cases to run

```

We can now see some more details in the session's info:

```console
$ canary info
Workspace:   ...
Version:     25.12.18+28f4bd50
Sessions:    2
Latest:      2025-12-18T13-23-40
Tags:        basic
```

```console
$ canary status
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ ID          ┃ Name       ┃ Session                               ┃ Exit Code      ┃ Duration     ┃ Status               ┃ Details   ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 104bba2     │ FFO        │ 2025-12-18T13-23-40.035876            │ 0              │ 0.62         │ PASS (SUCCESS)       │           │
│ eaf76e3     │ second     │ 2025-12-18T13-23-40.035876            │ 0              │ 0.68         │ PASS (SUCCESS)       │           │
└─────────────┴────────────┴───────────────────────────────────────┴────────────────┴──────────────┴──────────────────────┴───────────
```

This status represents *all* test cases in the session, not only those included by the latest invocation of `canary run`, e.g., if a tag representing a subset was specified.

We've now demonstrated the workflow for starting a session, adding tests, and executing them. In the next section, we
demonstrate how to expand the test set and "stage" test cases.

### Expanding the test set

In this section, we add `pathspec`s to the session to increase the test of tests and demonstrate the re-generation of the test cases.

We add the `examples` directory (which includes the previous set of tests, but it could be different) and examine the info/status.

```console
$ canary selection create -r examples examples
INFO: Collecting generator files from examples... done (0.03s.)
INFO: Instantiating generators from collected files... done (0.72s.)
INFO: Generating test specs from generators... done (0.97s.)
INFO: Searching for duplicated tests
INFO: Resolving test spec dependencies... done (0.01s.)
INFO: Generated 84 test specs from 38 generators
INFO: Excluded 1 test spec during generation

  Reason                                             Count
 ──────────────────────────────────────────────────────────
  options=enable evaluated to False for options=[]       1

INFO: Caching test specs... done (0.01s.)
INFO: Created selection 'examples'
INFO: To run this selection execute 'canary run examples'

```

```console
$ canary run examples
...
```

```console
$ canary status
```

We've now demonstrated how an existing test session can be expanded and the behavior of the `stage` command. In the next
section, we demonstrate using `stage` to partition test cases into selection sets that can be executed via `canary run`.

### Refining test sets
Now let's consider the case where we'd like to partition tests into parallel vs. serial sets.
This is achieved by calling `stage` as follows:
```console
$ canary select -p 'cpus=1' -t serial
==> Generating test cases... done (0.18s.)
==> Generated 84 test cases from 38 generators
==> Resolving test case dependencies... done (0.00s.)
==> Masking test cases based on filtering criteria... done (0.12s.)
==> Selected 64 test cases based on filtering criteria
==> To run this collection of test cases, execute 'canary run serial'

$ canary select -p 'cpus>1' -t parallel
==> Generating test cases... done (0.07s.)
==> Generated 84 test cases from 38 generators
==> Resolving test case dependencies... done (0.00s.)
==> Masking test cases based on filtering criteria... done (0.04s.)
==> Selected 13 test cases based on filtering criteria
==> To run this collection of test cases, execute 'canary run parallel'
```
Then calling `canary info` shows that there are now three tags:
```console
$ canary info
...
Tags:          default parallel serial
```

We can now run the parallel tests only by
```console
$ canary run parallel
version: 25.11.3+4667fcaa
==> Running 13 jobs
...
💥💥 Session done -- 13 total, 13 pass in 00:00:02
```
Note that only the 13 parallel tests were executed, and there was no test case generation step.
The session status is also updated
```console
$ canary status
ID       Name                                    Session                     Exit Code  Duration  Status   Details
=======  ======================================  ==========================  =========  ========  =======  ==========================================
...
51c3025  copy_and_link                           2025-11-03T13-14-57.774557  0          4.0       success  
bc54752  ctest_test                              2025-11-03T13-14-57.774557  0          0.0       success  
109eeba  depends_on_a                            2025-11-03T13-14-57.774557  0          2.0       success
...
333d31e  parameterize4[a=1,b=100000,cpus=4]      2025-11-03T13-35-32.135241  0          2.0       success  
e3f786e  parameterize4[a=1,b=100000,cpus=8]      2025-11-03T13-35-32.135241  0          2.0       success  
b5fc32b  parameterize4[a=2,b=1e+06,cpus=4]       2025-11-03T13-35-32.135241  0          2.0       success 
...
```
Note the different session identifiers for the serial tests (first block) compared to the parallel tests (second block).
If new generators are included in the session via the `canary add` subcommand, then these test case selections apply to
that increased set. As mentioned before, the test case selection can be explicitly re-constructed by the `stage` subcommand
or automatically regenerated/cached via `canary run`.

## Summary
We've demonstrated the prototype workflow, and by following this the user should understand the following:
  * initialization of a Canary session
  * addition of test generators by pathspec
  * optional creation of test sets via selection criteria applied to the session's test generators
  * execution and inspection of test results

If we proceed with development of this workflow, we intend to maintain legacy behavior of `canary run [options] pathspecs`;
however, a warning message with instructions on how to convert to the new workflow may be emitted (what would you want?).

This prototype workflow is not yet feature complete, and we desire feedback to identify if we are headed in a useful direction
for the increasingly diverse Canary user community. Some potential areas for feedback/direction:
  * naming conventions -- is `Sessions` in the `canary info` the right name, or is there something more clear
  * how would you want to navigate between prior sessions? How important of a use-case is this for us to consider?
  * how should report generation behave (not functional in the prototype)? Should the report be generated for the complete set of latest results, or only the latest session?
  * anything else you can think of!

## Feedback

* jhniede: frequently run wrong thing, etc. and need to kill running jobs.  Sometimes [ctl-c]
  takes a long time to complete and doesn't always scancel jobs reliably.
* jbcarle: look for keyboard input and abort.
* jhniede: canary.kill file similar to alegra.cmd file
* jhniede: make sure documentation is up to date, reliable, and detailed.
* tjfulle: forcefully rerun if explicitly requests
* tjfulle: should also run all downstreams
* acrobin: restart-like capability to continue test that may have timed out
* acrobin: --only=changed should work in new session
