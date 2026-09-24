# Canary TUI: Plan and Progress

**Status:** Active development. This document is the single source of truth for
the TUI effort and is updated as work lands, so an interrupted session can be
resumed without rediscovery.

**End goal:** A full TUI front end to `canary run` -- discover/select tests, see
details, edit a test file, and (re)run tests *in place* inside the TUI with live
progress, without shelling out to a separate process or tearing the display
down.

---

## 1. Architecture recap (what the TUI stands on)

The TUI is a thin **interface adapter** over the application layer
(`canary.app`). It holds no business logic; all workspace access goes through
`_canary.app.queries` (reads) and `_canary.app.run` (the run use case).

Relevant modules:

| Module | Role |
|---|---|
| `_canary/tui/state.py` | Pure, fully testable UI state machine (`ExplorerState`). No I/O. |
| `_canary/tui/render.py` | Rich renderers (header/table/detail/footer/log). |
| `_canary/tui/app.py` | The only I/O module: `ExplorerModel` (bridges queries+run to state) and `run()` (the runner loop, raw-mode key reader, `rich.live.Live`). |
| `_canary/app/queries.py` | Read surface: `list_jobs`, `job_log`, `workspace_summary`, `status_counts`, `job_history`, `get_event_bus`. |
| `_canary/app/run.py` | The run use case: `run(request, options)` -> exit code. |
| `_canary/events/bus.py` | Process-wide `EventBus`; typed `Event`/`JobEvent`; `project_job_event`. |
| `_canary/app/facade.py` | Holds the singleton `EventBus` (`get_event_bus`). |

**Event flow (already wired):** during an in-process run the executor
(`ResourceQueueExecutor`, `runtest.py:204`) publishes job-lifecycle events to the
process-wide `EventBus` returned by `app.get_event_bus()`. The TUI's
`ExplorerModel.subscribe()` already listens and flips a thread-safe *dirty* flag
so the runner refreshes rows from the DB promptly (`tui/app.py:74-94, 248`).
Events only mark dirty; the DB remains the source of truth for row content.

---

## 2. Progress log (most recent first)

- **DONE** Live-run monitoring (roadmap item 2, first cut). While an in-place
  rerun executes, a yellow "running" panel shows a progress bar
  (finished/total + %), running/pending counts, per-status tallies, and elapsed
  time -- fed by the event stream, not the DB (`tui/progress.py` `RunProgress`,
  `render_run_progress`). The tracker learns the total from event `qsize`, is
  idempotent on duplicate terminal events, and is thread-safe (updated on the
  publisher thread, snapshotted on the render thread).
- **DONE** In-place rerun (steps 1-3). `r` now runs the marked/cursor tests in a
  **child process** whose events stream back onto the app `EventBus` via the
  durable spool; the TUI keeps its `Live` display up, shows a "running…" footer,
  refuses a concurrent rerun, and refreshes on completion. No console handoff.
  (`ExplorerModel.begin_rerun`/`poll_run`, `_live_session` polls the run.)
- **DONE** Unified cross-process transport on a durable spool bus
  (`events/spool.py`: `SpoolBus`/`SpoolListener`), replacing the ad-hoc mp.Queue
  bridge that deadlocked on the Queue feeder thread. `FSQueue` now orders by a
  monotonic filename key (was mtime) so event streams drain in order. Commit
  `275287f7`.
- **DONE** `app.run_in_subprocess` + `RunHandle`: spawn a child that runs the
  session, redirects its stdout/stderr, publishes events to the spool; parent
  reads the return code from the process exit code.
- **DONE** `fix(app): expose absolute file_path in JobView` -- the TUI edit
  action opened a path relative to the scan root, not CWD. `JobView.file_path`
  is now `file_root/file_path`. Commit `968f675a`.
- **DONE** `fix(tui): edit test files with vim instead of $EDITOR/$VISUAL`
  (c81fce86).
- **DONE** `feat(tui): edit a test file (e) and rerun the edit` (c238e9a1).
- **DONE** `feat(tui): multi-select jobs and rerun the selection` (2b35b59c).
- **DONE** scrolling viewport + job-log drill-down (f4d06c58, e51f050f).
- **DONE** project job events to primitive payloads; TUI subscribes (5ff56cb7).
- **DONE** initial workspace-explorer TUI, Phase 8 (6e7d92fe).

### Implemented UI capabilities (see `state.py` key map)
- Navigate (`j/k`, arrows, `g/G`, page keys), scroll viewport sized to terminal.
- Detail pane toggle (`d`); log drill-down (`enter`/`space`), log scrolling.
- Status filter cycle (`f`) / clear (`a`).
- Multi-select (`x` mark/advance, `c` clear).
- Edit (`e`) the selected test's file in vim; auto-marks the edited test for rerun.
- Rerun (`r`) the marked set (or cursor row) **in place** -- runs in a child
  process, streams live into the table, TUI never leaves the screen.
- Quit (`q`/`escape`).

---

## 3. Current rerun behavior and the in-place goal

### 3.1 How rerun works today (out-of-process feel)

`ExplorerModel.rerun(spec_ids)` (`tui/app.py:121-132`) calls
`_canary.app.run.run(SpecIdsRequest(...))`. The runner loop tears the live
display and raw-mode reader **down** first, then calls `rerun`, which runs the
session synchronously and returns an exit code (`tui/app.py:274-279`). The run
is in the *same OS process*, but it owns the terminal: `workspace.run` installs
a Rich `LiveReporter` that writes the live results table to stdout
(`execution/console.py:397-502`), which would corrupt the TUI's own
`rich.live.Live` display -- hence the teardown. After the run the TUI is
re-entered with fresh data.

So "separate process" is not literally true; the real issue is **two competing
owners of the terminal** (the TUI's `Live` vs. the run's `LiveReporter`).

### 3.2 What "in place" means

Run the session **without tearing the TUI down**, streaming progress into the
TUI's own table via the event bus the TUI already subscribes to, then leave the
user in the explorer with updated rows -- no console handoff, no visible
separate run output.

### 3.3 The key seam (why this is tractable)

`ResourceQueueExecutor` already chooses its reporter from a flag:

```
# queue_executor.py:502
reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)
```

`live_reporting` is derived in `__init__` (`queue_executor.py:368-379`) and is
already forced **off** when `not sys.stdin.isatty()`, on `CANARY_LIVE=0`, in
debug, in nested canary levels, etc. `EventReporter` does not own the screen; it
just fans job events out. And crucially, **job events already flow to the
process-wide `EventBus` regardless of which reporter is active** -- the TUI's
live update does not depend on `LiveReporter` at all.

Therefore: if we run the session with the executor's own `LiveReporter`
suppressed, the run produces no competing terminal output, and the TUI updates
itself from the events it already receives.

---

## 4. In-place rerun: scope and plan

### 4.1 Chosen approach (in-process, suppress LiveReporter, TUI keeps the screen)

Rationale: the events, the subscription, the DB-as-truth refresh, and the
reporter seam **already exist**. This is the smallest change that reaches the
goal and matches the redesign doc's "interfaces embed the app and subscribe to
the bus" direction. A subprocess/thread-isolated run would add IPC and
duplicate the event transport for no benefit at this stage.

Steps:

1. **A suppression switch for the executor's console reporter.** Add an
   explicit, first-class way to run with `live_reporting=False` that does not
   rely on the incidental `isatty()`/env heuristics. Options considered:
   - (a) A `RunOptions.live_console: bool | None` threaded through
     `app.run` -> `workspace.run` -> `Session.run` -> `default_runtests` ->
     `ResourceQueueExecutor(live_reporting=...)`. **Preferred** -- explicit and
     testable, no global state.
   - (b) Set `CANARY_LIVE=0` in the environment around the call. Simpler but
     process-global and racy; rejected except as a fallback.
   The plumbing in (a) is several layers but each is a pass-through parameter.

2. **Keep the TUI `Live` running during the rerun.** In `tui/app.py`, stop
   tearing the display down for `rerun`. Instead, run the session on a
   background thread while the live loop keeps drawing; the existing dirty-flag
   subscription already repaints as events arrive. The raw-mode key reader can
   keep running so the user can watch (and later cancel).

3. **Concurrency care.** `workspace.run` mutates workspace/DB state and spawns
   worker processes; the TUI refresh reads the DB. They already coexist during a
   normal live run (the run process reads the DB while workers spool results
   through the single-writer `ResultListener`). Running the session on a worker
   thread within the TUI process needs: a run-in-progress guard (no second
   rerun until the first finishes), and the footer reflecting "running…".

4. **Restore/settle.** On completion, do a final `model.refresh()` and clear the
   run guard; keep the user on the same cursor row (the state already preserves
   the selected spec id across refreshes, `state.py:68-81`).

### 4.2 Files expected to change

- `_canary/app/run.py` -- add `live_console` to `RunOptions`, pass through.
- `_canary/session/workspace.py` -- `run(..., live_console=...)` pass-through.
- `_canary/execution/runtest.py` -- pass the flag into `ResourceQueueExecutor`.
- `_canary/execution/queue_executor.py` -- honor an explicit `live_reporting`
  argument over the heuristics.
- `_canary/tui/app.py` -- run the session on a thread, keep `Live` up, guard
  re-entrancy, refresh on completion.
- `tests/tui_integration.py` -- a test that an in-place rerun updates rows
  without a console handoff (assert `LiveReporter` is not constructed / the
  event path drives the refresh).

### 4.3 Risks / open considerations

- **Terminal contention** is the whole ballgame: any stray stdout/stderr from
  the run (log lines routed through Rich handlers, warnings) can still smear the
  TUI. Mitigation: with `live_reporting=False` the `_LiveConsoleHandler` is not
  installed; verify no other code writes to stdout during the run while the TUI
  owns it. May need to route run-time logging to the workspace log file only
  while the TUI is active.
- **Threading vs. signals:** `ResourceQueueExecutor` installs SIGINT handling
  for cancellation; signal handlers only work on the main thread. If the run is
  on a background thread, cancellation/`Ctrl-C` semantics need checking. This
  intersects with the planned in-TUI cancel key.
- **Blocking `workspace.run`** holds a global lock (`global_lock`); ensure the
  TUI's read queries don't deadlock against it (they read via a separate DB
  connection today).

### 4.4 Decision needed from maintainer (genuine tradeoff)

Deeper scoping found two real complications that make this **not** a
straightforward pass-through, so it is paused for a decision:

1. **The reporter flag can't be a clean parameter.** `Session.run` invokes the
   executor through a pluggy hook: `canary_runtests(runner=runner)`
   (`workspace.py:195`). There is no argument channel from `app.run` to the
   executor except via the global `config` (which is snapshotted into workers)
   or by hanging state on the `Runner`/`Session`. So "plumb a `live_console`
   parameter" really means either (a) add a config option that
   `ResourceQueueExecutor.__init__` reads instead of / in addition to the
   `isatty()` heuristics, or (b) set `CANARY_LIVE=0` in the environment around
   the in-TUI run (already honored at `queue_executor.py:374`). (b) is a
   one-line, isolated stopgap; (a) is the cleaner long-term switch but adds a
   public-ish config option and touches the CLI run path.

2. **`Session.run` calls `os.chdir()`** (`workspace.py:194,201`), which is
   process-global and not thread-safe. Running the session on a background
   thread while the TUI's main thread keeps drawing would race the CWD. So the
   "keep `Live` up and run on a worker thread" plan (section 4.1 step 2) is
   unsafe as written. Realistic options:
   - **A. In-process, main thread, suppress the run's console; accept a brief
     non-interactive pause.** Keep the TUI process, set the reporter off, run the
     session on the *main* thread (TUI `Live` paused but not exited), and let the
     final refresh repaint. Loses live streaming *during* the rerun but is safe
     and small. Arguably barely different from today except no visible console
     handoff.
   - **B. Run the session in a child process** and have the TUI consume events
     over a transport (pipe/socket). Gives true live in-place streaming and
     isolates `os.chdir`/signals, but requires the cross-process event bridge
     that `facade.get_event_bus` explicitly defers ("Cross-process delivery ...
     belongs to a future transport"). Bigger effort.
   - **C. Make `Session.run` not use `os.chdir`** (pass cwd per-job) so the run
     is thread-safe, then run on a background thread with the `Live` display
     staying fully live. Best UX, but changes core execution behavior and needs
     its own care/tests.

**Recommendation:** ship **A** now (safe, small, removes the console handoff and
the "separate process" feel), and treat **C** as the follow-up that unlocks true
live streaming (feeding roadmap item 2, the live-run view). **B** only if a
remote/child-process run is wanted for other reasons.

**DECISION (maintainer):** Build **B** -- subprocess + event bridge. Rationale:
the `canary tui` command is a stepping stone to a *general* TUI that hosts and
interacts with `canary run`, `status`, etc. That requires true live streaming
while the TUI keeps the screen, and a run that is isolated from the TUI's
process (no shared `os.chdir`/signal/terminal contention). B is the only option
that generalizes to a remote/GUI client later; A and C are in-process dead ends
for that goal.

### 4.5 Chosen design (B): child-process run + event bridge

Grounded in the existing machinery (see the research map in the commit history /
below):

- **Wire format already exists.** Workers emit `{"event": <EventName>, ...}`
  dicts; `_handle_worker_payload` -> `notify_listeners` -> `event_bus.publish`
  already turns those into `Event(name, {"job": JobEvent})` on the app
  `EventBus` (`queue_executor.py:558-585`). We reuse this verbatim.
- **The bridge mirrors `ResultListener`** (`database.py:1028-1060`): a
  parent-side daemon thread that drains a cross-process transport fed by the
  child run and republishes each item onto the parent's `EventBus` via
  `get_event_bus().publish(...)`. The TUI already subscribes to that bus, so no
  TUI-side change is needed to *observe* -- only to *launch*.
- **Transport.** `multiprocessing` with an explicit spawn context so parent and
  child share an `mp.Queue`: the child target calls `app.run(...)` after
  installing a bus subscriber that forwards every `Event` onto the shared queue;
  the parent's bridge thread drains it. (`FSQueue`,
  `util/multiprocessing.py:334`, is the disk-backed fallback if a shared mp
  context proves impractical, e.g. a fully independent `python -m canary run`.)
- **DB single-writer stays intact.** The child run is its own process at
  `canary_level == 0`, so it legitimately owns the `ResultListener` and SQLite
  writer for its session (`workspace.py:527-531`). The parent TUI only *reads*
  the DB (separate connection) and consumes events -- it must **not** also run a
  writer for that session. This side-steps the two-writer hazard by keeping the
  writer in the child.
- **Console suppression in the child.** The child sets `CANARY_LIVE=0` (honored
  at `queue_executor.py:374`) so it uses `EventReporter`, not `LiveReporter`;
  its stdout/stderr are captured/redirected (not shared with the TUI terminal).

### 4.6 Incremental implementation plan (each step usable, tests as we go)

1. **`_canary/events/`: a process-boundary forwarder.** Add a small helper that,
   given an `mp.Queue`, subscribes to a bus and puts each `Event` (name +
   primitives-only payload) on the queue; and a parent-side `EventBridge`
   daemon thread that drains the queue and republishes onto a target bus.
   Pure, unit-testable with two in-process buses + a real `mp.Queue`.
2. **`_canary/app/`: a `run_in_subprocess(request, options)` use case.** Spawns
   a child (spawn context) that: reconstructs config, installs the forwarder on
   its bus, sets `CANARY_LIVE=0`, calls `app.run.run(...)`, and returns the
   exit code via the queue/sentinel. Parent starts the `EventBridge` onto
   `get_event_bus()` and returns a handle (poll/return-code + join). Headless
   test: events observed on the parent bus; correct return code; DB updated.
3. **`_canary/tui/app.py`: use the subprocess run, keep `Live` up.** Replace the
   teardown-then-`rerun` path: launch via the app use case, keep the live loop
   drawing (the dirty-flag subscription already repaints on each forwarded
   event), show a "running…" footer, guard re-entrancy, `refresh()` on
   completion. Integration test with `once=`-style/headless harness.
4. **Cancellation hook (roadmap item 3) becomes natural**: cancel = terminate
   the child (or signal it), emit `job_cancelled`. Deferred to its own step.

### 4.7 Risks specific to B

- **Config reconstruction in the child** must reproduce the parent's workspace
  and plugins (`config.snapshot()`/`CANARYCFGFILE`, `canary_addconfig`; see
  `config.py:118-134,213-239`). Spawn (not fork) means no inherited state, so
  the snapshot handoff must be complete.
- **Payload must stay primitives-only** across the queue (pickle): `JobEvent`
  already is (`bus.py:68-92`); ensure no `_canary` object is forwarded.
- **Child lifecycle**: orphan/zombie prevention on TUI exit or crash (join /
  terminate in a `finally`); the bridge thread must stop when the child ends.
- **Ordering/backpressure**: an `mp.Queue` preserves per-producer order; the bus
  is best-effort cross-job today, which matches current behavior.

**Awaiting nothing further -- implementing B incrementally per 4.6.**

### 4.8 Transport pivot: unify on a durable spool bus (supersedes 4.5/4.6 transport)

**Why:** the first cut of B used a fresh `multiprocessing.Queue` for the child ->
parent event stream and immediately hit the classic mp.Queue deadlock -- a
`Queue`'s background *feeder thread* blocks process exit until every buffered
item is flushed to and consumed from the pipe, so a child that produces a burst
of events cannot cleanly exit unless the parent perfectly drains it. Working
around it (`cancel_join_thread`, sentinels, control-queue ordering) is fragile.

Stepping back, Canary already has **several bespoke cross-process queues built
in isolation**: worker->parent job events (`mp.Pipe` + `_handle_worker_payload`),
logging (`mp.Queue` + `QueueHandler`), HPC batch events (`SimpleQueue`), and the
durable result spool (`FSQueue` + `ResultListener`). Three share one shape:
*a producer in another process; a daemon thread in the parent drains into a
sink.* Crucially, the **only** one that already crosses a fully independent
`canary` process boundary without feeder-flush deadlocks is the disk-backed
`FSQueue` (`util/multiprocessing.py:334`), drained by `ResultListener`
(`database.py:1028-1060`) -- because files have no feeder thread and atomic
rename makes it multi-writer safe.

**Decision (maintainer):** generalize that proven pattern into a reusable
**durable spool bus** and route job events through it, instead of adding an Nth
ad-hoc mp queue. This benefits the core CLI run path (one transport to reason
about) and the TUI (deadlock-free child->parent streaming), while leaving CLI
behavior and the test-author API unchanged.

**Design:**
- `events/spool.py`:
  - `SpoolBus(dir)` -- wraps an `FSQueue`; `publish(Event)` pickles a
    ``(name, payload)`` record to the spool (safe from any process, including a
    fully independent `canary` child).
  - `SpoolListener(dir, bus)` -- a daemon thread (mirrors `ResultListener`) that
    `drain()`s the spool FIFO-by-mtime and republishes each record onto an
    in-process `EventBus`. `start()` / `stop()`.
- The child run installs a bus subscriber that writes to `SpoolBus`; the parent
  runs a `SpoolListener` onto `app.get_event_bus()`. No mp.Queue, no feeder
  deadlock, no sentinels. Return code/errors come from the child *process exit
  code* (already reliable), not an in-band control queue.
- Spool location: `<workspace>/.canary/tmp/events` (sibling to the DB spool at
  `tmp/db`), so events and result records never mix.
- **Follow-up (not now, tracked here):** migrate the logging queue and,
  eventually, the worker event pipe onto the same `SpoolBus`/listener shape so
  there is a single cross-process channel abstraction. Gated on not regressing
  the hot CLI run path; measured before/after. The worker<->parent *pipe* is the
  latency-sensitive one and may stay as-is if the spool adds measurable overhead
  to the inner loop -- to be decided with numbers, not assumptions.

**Superseded:** the `QueueForwarder`/`EventBridge` (mp.Queue) added in step 1 and
the mp.Queue plumbing in `run_in_subprocess` are replaced by `SpoolBus`/
`SpoolListener`. The `EventBus`, `Event`, `JobEvent`, and `project_job_event`
types are unchanged.

### 4.9 Revised implementation steps

1. **DONE (revised):** `events/spool.py` -- `SpoolBus` + `SpoolListener`, unit
   tested (two buses + a real temp dir; burst of events; stop semantics).
2. `app/run_subprocess.py` -- child publishes to `SpoolBus`; parent runs a
   `SpoolListener`; return code from `process.exitcode`. Headless integration
   test: events observed on the parent bus, correct rc, DB updated, **child
   exits cleanly** (the regression that motivated the pivot).
3. TUI uses the subprocess run and keeps `Live` up (unchanged from 4.6 step 3).
4. Cancellation (unchanged from 4.6 step 4).

---

## 5. Roadmap toward "full TUI front end to canary run"

Ordered, each step independently useful:

1. **In-place rerun** (section 4) -- run without leaving the explorer.
2. **Live-run view** -- **DONE (first cut):** a progress panel fed purely by
   `EventBus` events (counts, per-job status, elapsed) shown while a run is in
   flight. Future: per-row phase animation in the table, worker-slot occupancy.
3. **First-class cancellation** -- a cancel key that stops the running session
   (`ResourceQueue.clear` + signal), surfaced as `job_cancelled` events (the bus
   already reserves the name, `events/bus.py:37`).
4. **Start a run from scratch in the TUI** -- not just rerun: pick scanpaths /
   a selection/tag, build a `RunOptions`, and launch. This is the last piece for
   a full `canary run` front end (the app layer already accepts scanpaths/tag
   requests, `app/run.py:99-135`).
5. **Live log tailing** -- stream a running job's output into the log pane
   (needs a `job_output` event or file tail; noted as an open question in the
   redesign doc, section 10.4).

---

## 6. Verification commands

```
# from src/canary, using the agent venv
../../venv.agent/bin/ruff check src/_canary/tui tests/tui_integration.py
../../venv.agent/bin/ruff format --check src/_canary/tui tests/tui_integration.py
../../venv.agent/bin/mypy src/_canary/tui
../../venv.agent/bin/bandit -q -c pyproject.toml src/_canary/tui/app.py
../../venv.agent/bin/python -m pytest tests/tui_integration.py tests/tui_state.py -q
```
