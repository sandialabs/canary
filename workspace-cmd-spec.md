This document was written as Matt's midnight musings after the initial demo of canary "sessions".
This is a DRAFT refinement of the proposed command spec and usage.

### Overall thoughts
- canary "workspace" is a better name than "session" and internal "repo"
- we need some more concepts to support more general workflows
- I'm not sure how we can sustainably support change-based assignment unless a "tag" can also be associated with generator
  list in addition to or instead of filter sets
  - change-based assignment is not a core feature of canary (yet), so maybe we let plugins figure that out for now...

### Thoughts about commands
- `canary add` --> `canary search-path add`
- `canary stage` --> `canary selection` (I initially thought `select`, but it read funny to me)

### Things that need more thought
- management of "sessions" i.e., executions of `canary run`
  - How to inspect results for a prior session, e.g., for comparison?
  - "sessions" --> "results"


### Brief pseudo-walkthrough
```console
$ canary init
$ canary search-path add foo:git@/path/to/foo foo:/path/to/another_foo bar:/path/to/bar /path/to/unnamed /path/to/another/unnamed
==> added 5 paths to search for generators
==> found 99 generators

$ canary search-path
foo:
  - git@/path/to/foo
  - /path/to/another_foo
bar:
  - /path/to/bar
unnamed:
  - /path/to/unnamed
  - /path/to/another/unnamed

$ canary search-path remove bar /path/to/unnamed /not/in/paths
==> removed 2 paths from search-paths
==> Warning: '/not/in/paths' does not exist in search-paths
==> found 33 generators

# add a new generator in one of the search paths
$ canary search-path refresh
==> found 34 generators

$ canary selection
default: all
all: out-of-date

$ canary selection add -k keyword -p param=7 my_tests
$ canary selection -v
default: all
all:
  status: out-of-date
  count: None
my_tests:
  status: out-of-date
  count: None

$ canary lock --all
...
$ canary selection -v
default: all
all:
  status: good
  count: 321
my_tests:
  status: good
  count: 33

$ canary selection set-default my_tests
$ canary selection
default: my_tests
all:
  status: good
  count: 321
my_tests:
  status: good
  count: 33

$ canary selection list my_tests
<PAGER list of test cases in selection>

$ canary run
... # execute "my_tests"

$ canary run all
...

$ canary results
<foo> "canary run" ...
<bar> "canary run all" ...

$ canary results select --no-previous foo
$ canary report <format> create
... # creates report for current view in TestResults, in this case from `canary run` (subset)
```

## More detailed command spec

### canary init
```console
canary init [path] -- initialize a workspace rooted at [path], default is current directory
```

### canary search-path
```console
canary search-path -- manage tracked search paths for identifying generators

  canary search-path
  canary search-path add [name:]pathspec [[name:]pathspec...]
  canary search-path remove name|pathspec [name|pathspec...]
  canary search-path refresh

COMMANDS
  With no arguments, shows a list of existing search paths.

  add
    Add <pathspec> to search paths and optionally alias to <name>. Multiple <pathspec> can
    be aliased by <name>.

  remove
    Remove <pathspec> by <pathspec> or alias <name> if it exists. If multiple <pathspec>
    are aliased by <name>, they are all removed.

  refresh
    re-search all paths for generators, e.g., after adding or updating generators.

NOTES
  The add, remove, and refresh commands may invalidate caches.
```

### canary selection
```console
canary selection -- manage test selections in the workspace

  canary selection [-v|--verbose] [--json] [--contains <ref>]
  canary selection add [filter options] [-m|--message <msg>] <name>
  canary selection remove <name>
  canary selection set-default <name>
  canary selection lock [--all] | <name> [name...]
  canary selection list [--format=FORMAT] <name>

OPTIONS
  --verbose
      Print additional information.

  --json
      List selections in JSON format for machine input. Implies --verbose.

  --contains <ref>
      List the selections that contain the object <ref>. <ref> is typically a truncated SHA
      for a test case or generator.

COMMANDS
  With no arguments, shows a list of selections defined in the workspace and their lock
  status. The "all" selection always exists. The name "default" is reserved as an alias to
  the selection specified with `set-default` and is initialized to "all".

  add
    Create a test selection matching [filter options] and referenced by <name>.

    With --message, record additional information about the selection via <msg>.

  remove
    Remove the selection <name>.

  set-default
    Set the "default" alias to <name>.

  lock
    Create test cases in selection <name>, or all selections with the option `--all`.

  list
    List test cases in selection <name> if it is locked

    With --format uses the FORMAT string substitution to print specified fields for each
    test case. The default FORMAT is "{ref[:6]} {name}".
```

### canary run
```console
canary run -- execute tests, generate a results dataset

  canary run
    Run tests in the "default" selection

  canary run <ref>
    Run tests specified by <ref>, where <ref> may be a selection, test case, or batch
```

### canary results
```console
canary results -- manage results datasets and `TestResults` "view"

  canary results [-v|--verbose] [--json]
  canary results select [--no-previous] [id]
  canary results refresh
  canary results remove <id>
  canary results annotate [-m|--message <msg>] [id]
  canary results gc

COMMANDS
  With no arguments, prints a list of the results datasets from invocations of `canary run`
  and associated information.

  select
    Update the test results view to the specified dataset, "latest" if no [id] is provided.

    --previous (default)
    --no-previous
        Indicate whether or not to include results from the latest prior execution of each
        test case in the results view, e.g., if they were not part of the specified dataset.

  refresh
    Manually update the view for the currently selected session. Used primarily if links
    become broken.

  remove
    Remove the specified session.

  annotate
    Record or update a message about dataset [id], "latest" if none specified, using the 
    CANARY_EDITOR.

    -m, --message
      Overwrite the message on the command line without a prompt.

NOTES
  Execution of `canary run` implies selection of the latest data, i.e.,
  `canary results select latest`
```

### canary generators
```
canary generators -- list the generators in the workspace

  canary generators [--format=FORMAT]

OPTIONS
  --format=FORMAT
      Print out the list of generators using the FORMAT python string substitution. The
      default FORMAT is "{ref[:6]} {path}". Specified fields that do not exist are left empty.
      Common fields include:
        keywords - listed keywords in the generator
        ...

NOTES
  A generator's <ref> is "stable" such that a generator at the same path will have the same
  <ref> so long as it remains a valid generator after `canary search-path refresh`,
  otherwise <ref> is invalidated.
```

## Unsure command spec(s)
### canary list (maybe?)
```console
canary list -- a convenience wrapper to list various objects

  canary list [-v|--verbose] {paths,generators,tests,selections,sessions,...}
```
