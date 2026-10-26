# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import os
import signal
import sys
import time
from multiprocessing.connection import Connection
from multiprocessing.connection import Pipe
from multiprocessing.connection import wait
from multiprocessing.process import BaseProcess
from pathlib import Path
from queue import Empty as QueueEmpty
from typing import Any
from typing import Callable
from typing import Literal

from .. import config
from ..core.job import BaseJob
from ..core.job import JobPhase
from ..error import SessionTerminated
from ..error import StopExecution
from ..events import Event
from ..events import EventBus
from ..events import project_job_event
from ..util import logging
from ..util import multiprocessing as mp
from ..util import procutil
from ..util.misc import boolean
from ..util.returncode import compute_returncode
from .console import EventReporter
from .console import LiveReporter
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue

logger = logging.get_logger(__name__)

EventTypes = Literal["job_submitted", "job_staged", "job_started", "job_stopped", "job_finished"]


@dataclasses.dataclass(frozen=True)
class ExecutionEvent:
    name: str
    slot: "ExecutionSlot | None" = None
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class ProgressSnapshot:
    unit: str
    total: int
    submitted: int
    running: int
    finished: int
    queued: int


@dataclasses.dataclass
class ExecutionSlot:
    job: BaseJob
    qrank: int
    qsize: int
    worker_id: int

    def on_submit(self, at: float | None = None) -> None:
        self.job.on_submit(at=at)

    def on_stage(self, at: float | None = None) -> None:
        self.job.on_stage(at=at)

    def on_start(self, at: float | None = None) -> None:
        self.job.on_start(at=at)

    def on_stop(self, at: float | None = None) -> None:
        self.job.on_stop(at=at)

    def on_finish(self, at: float | None = None) -> None:
        self.job.on_finish(at=at)


class JobFunctor:
    def __call__(
        self,
        executor: Callable,
        job: BaseJob,
        result_queue: mp.Queue,
        logging_queue: mp.Queue,
        config_snapshot: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Process entrypoint: bootstraps environment and executes a single job."""
        _inner_process_setup()
        config.load_snapshot(config_snapshot)
        logging.clear_handlers()
        h = logging.QueueHandler(logging_queue)
        logging.add_handler(h)
        try:
            executor(job, queue=result_queue, **kwargs)
        except Exception as e:
            logger.exception(f"Job {job}: exception occurred during execution of job functor")
            job.set_status(outcome="ERROR", reason=repr(e))
            sys.exit(1)
        else:
            logger.debug(f"Job {job}: job functor exited normally")
        finally:
            try:
                result_queue.put({"event": "job_finished", "timestamp": time.time()})
            except Exception:
                logger.exception("Failed to put job state into queue")
                raise
            finally:
                logging.clear_handlers()
                h.close()


#: Parent-side connections that a *forked* inner job process must close so that
#: the parent sees EOF promptly if the worker dies (set just before fork).
_FORK_INHERITED_CONNS: list[Connection] = []
#: PID of the worker that forked the inner job process (set just before fork).
_FORK_PARENT_PID: int | None = None


def _raise_interrupt(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt(f"Received signal {signum}")


def _inner_process_setup() -> None:
    """Prepare a freshly started inner job process.

    * Close inherited copies of the worker's event pipe (fork only) so a dead
      worker is detected immediately.
    * Convert SIGTERM into :class:`KeyboardInterrupt` so the launcher's cleanup
      (which reaps the test's process group) runs when the worker terminates us.
    * Ask the kernel to SIGTERM us if the worker dies (Linux), and bail out if
      it already has.
    """
    global _FORK_INHERITED_CONNS
    for conn in _FORK_INHERITED_CONNS:
        try:
            conn.close()
        except Exception:  # nosec B110
            pass
    _FORK_INHERITED_CONNS = []
    procutil.install_termination_handlers(procutil.termination_signals(), _raise_interrupt)
    procutil.set_parent_death_signal(signal.SIGTERM)
    if _FORK_PARENT_PID is not None and os.getppid() != _FORK_PARENT_PID:
        raise SystemExit(1)


def inner_ctx() -> Any:
    """
    Inner job process context.

    Default: fork (fast for many tiny tests).

    Override (env var):
      CANARY_INNER_START_METHOD=default|inherit -> use mp.get_context() (global default)
      CANARY_INNER_START_METHOD=spawn          -> force spawn
      CANARY_INNER_START_METHOD=forkserver     -> force forkserver
      CANARY_INNER_START_METHOD=fork           -> force fork
      CANARY_INNER_START_METHOD=auto           -> same as unset (defaults to fork)
    """
    override = os.getenv("CANARY_INNER_START_METHOD", "").strip().lower()

    method: str
    if override in ("", "auto"):
        method = "fork"
    elif override in ("default", "inherit"):
        return mp.get_context()
    elif override in ("fork", "spawn", "forkserver"):
        method = override
    else:
        logger.warning(f"Unknown CANARY_INNER_START_METHOD={override!r}; falling back to fork")
        method = "fork"

    try:
        return mp.get_context(method)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning(f"inner_ctx: failed to get_context({method!r}): {e}; using default")
        return mp.get_context()


class _MainWorker:
    def __init__(
        self,
        *,
        worker_id: int,
        task_q: mp.Queue,
        event_conn: Connection,
        logging_queue: mp.Queue,
        config_snapshot: dict[str, Any],
        executor: Callable,
        common_kwargs: dict[str, Any],
    ) -> None:
        self.worker_id = worker_id
        self.task_q = task_q
        self.event_conn = event_conn
        self.logging_queue = logging_queue
        self.config_snapshot = config_snapshot
        self.executor = executor
        self.common_kwargs = common_kwargs

        self.ctx = inner_ctx()
        #: PID of the process that created this worker (the main canary process).
        self.parent_pid = os.getpid()
        self._worker_pid: int | None = None
        #: Set when the worker has been asked to stop; running jobs are reaped
        #: immediately instead of being given time to finish.
        self._stopping = False

        # Sampling / polling controls
        self.poll_sleep = 0.01

        # Per-job state (set during run_one_job)
        self.local_q: mp.Queue | None = None
        self._proc: BaseProcess | None = None

    @property
    def proc(self) -> BaseProcess:
        if self._proc is None:
            raise RuntimeError("proc is None")
        return self._proc

    @proc.setter
    def proc(self, arg: BaseProcess) -> None:
        self._proc = arg

    def send(self, payload: dict[str, Any]) -> None:
        try:
            self.event_conn.send(payload)
        except (BrokenPipeError, EOFError, OSError) as e:
            raise ParentGone from e

    def _on_terminate(self, signum: int, frame: Any) -> None:
        """SIGTERM/SIGHUP handler: stop the current job's whole process tree, then exit.

        Forked inner job processes inherit this handler until they replace it;
        in that case simply behave like an interrupt.
        """
        if os.getpid() != self._worker_pid:
            raise KeyboardInterrupt(f"Received signal {signum}")
        self._stopping = True
        raise ParentGone(f"worker {self.worker_id} received signal {signum}")

    def __call__(self) -> None:
        self._worker_pid = os.getpid()
        procutil.install_termination_handlers(procutil.termination_signals(), self._on_terminate)
        # If the main canary process dies (even by SIGKILL), get SIGTERM'd so
        # that we in turn reap the job we are running.
        procutil.set_parent_death_signal(signal.SIGTERM)
        config.load_snapshot(self.config_snapshot)
        try:
            if os.getppid() != self.parent_pid:
                return
            self.run()
        except (ParentGone, KeyboardInterrupt):
            self._stopping = True
            return
        finally:
            self.cleanup_all()

    def run(self) -> None:
        watcher = procutil.ParentWatcher()
        while True:
            try:
                msg = self.task_q.get(timeout=1.0)
            except QueueEmpty:
                if not watcher.parent_alive():
                    self._stopping = True
                    raise ParentGone("main canary process exited")
                continue
            if msg is None:
                return
            job, per_job_kwargs = msg
            self.run_one_job(job, per_job_kwargs or {})

    def run_one_job(self, job: BaseJob, per_job_kwargs: dict[str, Any]) -> None:
        global _FORK_INHERITED_CONNS, _FORK_PARENT_PID
        # IMPORTANT: use mp.Queue (not SimpleQueue) so we can do get(timeout=...)
        self.local_q = mp.Queue()
        proc: BaseProcess = self.ctx.Process(
            target=JobFunctor(),
            args=(self.executor, job, self.local_q, self.logging_queue, self.config_snapshot),
            kwargs={**self.common_kwargs, **per_job_kwargs},
        )
        self.proc = proc
        _FORK_INHERITED_CONNS = [self.event_conn]
        _FORK_PARENT_PID = os.getpid()
        try:
            proc.start()
        finally:
            _FORK_INHERITED_CONNS = []
            _FORK_PARENT_PID = None

        try:
            self.monitor_job(job)
        except BaseException:
            # Interrupted/terminated mid-job: do not wait for the job to finish.
            self._stopping = True
            raise
        finally:
            self.cleanup_job()

    def monitor_job(self, job: BaseJob) -> None:
        proc = self.proc
        local_q = self.local_q
        if local_q is None:
            raise RuntimeError("monitor_job called without active proc/local_q")

        job_id = job.id

        wall_limit = config.timeout_multiplier() * job.timeout
        # Jobs may declare a longer worst-case lifetime than their run timeout
        # (e.g. HPC batches: scheduler queue wait + 2x wall backstop) so the
        # watchdog never fires while they are legitimately waiting.
        budget = wall_limit
        try:
            if (declared := job.watchdog_timeout()) is not None:
                budget = max(wall_limit, float(declared))
        except Exception as e:
            logger.debug("watchdog_timeout() failed for %s: %s", job_id[:7], e)
        watchdog_grace = float(
            os.getenv("CANARY_WORKER_WATCHDOG_GRACE", str(max(300.0, min(1800.0, 0.10 * budget))))
        )
        watchdog_deadline = time.time() + budget + watchdog_grace

        def terminate_and_report(event: str, **extra: Any) -> None:
            logger.warning(
                "Terminating worker for job %s: event=%s timeout=%s grace=%s extra=%r",
                job_id[:7],
                event,
                budget,
                watchdog_grace,
                extra,
            )

            # Kill the inner job process *and* the test it launched (which runs in
            # its own session/process group).  Give the job enough time after
            # SIGTERM to run its own cleanup -- for batches that means cancelling
            # the scheduler job (scancel/flux cancel) -- before escalating.
            self.kill_job_tree(grace=max(procutil.kill_grace_period(), 30.0))

            payload: dict[str, Any] = {
                "job_id": job_id,
                "worker_id": self.worker_id,
                "event": event,
                **extra,
            }
            self.send(payload)

        while True:
            payload: dict[str, Any] = {"job_id": job_id, "worker_id": self.worker_id}

            try:
                payload.update(local_q.get(timeout=0.05))
            except QueueEmpty:
                pass
            else:
                event = payload.get("event")
                self.send(payload)

                if event == "job_finished":
                    return

                continue

            now = time.time()

            if proc.is_alive() and now > watchdog_deadline:
                terminate_and_report(
                    "job_timeout", phase="watchdog", timeout=budget, grace=watchdog_grace
                )
                return

            if not proc.is_alive():
                payload.update({"event": "job_died", "exitcode": getattr(proc, "exitcode", None)})
                self.send(payload)
                return

            time.sleep(self.poll_sleep)

    def kill_job_tree(self, grace: float | None = None) -> None:
        """Terminate the inner job process and every descendant (including the test)."""
        proc = self._proc
        if proc is None:
            return
        pid = getattr(proc, "pid", None)
        if not isinstance(pid, int):
            return
        try:
            procutil.kill_process_tree(pid, grace=grace)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("kill_process_tree(%s) failed: %s", pid, e)
        try:
            proc.join(timeout=1.0)
        except Exception as e:  # pragma: no cover
            logger.debug("proc.join failed: %s", e)

    def cleanup_job(self) -> None:
        if self._proc is not None:
            try:
                # Normal completion: the inner process is exiting on its own.
                self._proc.join(timeout=0.5 if self._stopping else 5.0)
                if self._proc.is_alive():
                    # Still running (interrupted, terminated, or stuck): never
                    # abandon it -- reap the inner process and the test's group.
                    self.kill_job_tree()
                if not self._proc.is_alive():
                    self._proc.close()
            except Exception as e:
                logger.debug("proc cleanup failed: %s", e)
            self._proc = None

        if self.local_q is not None:
            try:
                self.local_q.close()
            except Exception as e:
                logger.debug("local_q.close failed: %s", e)
            self.local_q = None

    def cleanup_all(self) -> None:
        # If we are exiting mid-job, still release job resources.
        self.cleanup_job()
        try:
            self.event_conn.close()
        except Exception as e:
            logger.debug("event_conn.close failed: %s", e)


class ResourceQueueExecutor:
    """Manages a pool of worker processes with timeout support and metrics collection."""

    def __init__(
        self,
        queue: ResourceQueue,
        executor: Callable,
        max_workers: int = -1,
        busy_wait_time: float = 0.01,
        event_bus: EventBus | None = None,
    ):
        self.max_workers = mp.max_workers(hint=max_workers)
        self.queue: ResourceQueue = queue
        self.executor = executor
        self.busy_wait_time = busy_wait_time
        self.event_bus = event_bus

        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}
        self.entered: bool = False
        self.started_on: float = -1.0
        self._store: dict[str, Any] = {}
        self.alogger = logging.AdaptiveDebugLogger(logger.name)
        self.listeners: list[Callable[[ExecutionEvent], None]] = []

        # worker infrastructure
        self.workers: list[dict[str, Any]] = []
        self.worker_connections: list[Connection] = []
        self.idle_workers: list[int] = []
        self.busy_workers: dict[int, str] = {}  # worker_id -> job_id
        self.slots_by_id: dict[str, ExecutionSlot] = {}

    def live_reporting(self) -> bool:
        style = config.getoption("console_style") or {}
        live_reporting: bool = style.get("live", True)
        if config.get("debug"):
            live_reporting = False
        if not sys.stdin.isatty():
            live_reporting = False
        if "CANARY_LIVE" in os.environ and not boolean(os.environ["CANARY_LIVE"]):
            live_reporting = False
        elif int(os.getenv("CANARY_LEVEL", "0")) > 0:
            live_reporting = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            live_reporting = False
        return live_reporting

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    def progress_snapshot(self) -> ProgressSnapshot:
        unit = "job"
        if slot := next(iter(self.slots_by_id.values()), None):
            unit = slot.job.identity_label()
        total = len(self.queue.jobs())
        submitted = len(self.submitted)
        running = len(self.running)
        finished = len(self.finished)
        queued = max(0, total - submitted - running - finished)
        return ProgressSnapshot(
            unit=unit,
            total=total,
            submitted=submitted,
            running=running,
            finished=finished,
            queued=queued,
        )

    def add_listener(self, callback: Callable[[ExecutionEvent], None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[[ExecutionEvent], None]) -> None:
        try:
            self.listeners.remove(callback)
        except ValueError:  # nosec B110
            pass

    def __enter__(self) -> "ResourceQueueExecutor":
        self._store.clear()
        self._start_mp_logging()

        logging_queue: mp.Queue = self._store["logging_queue"]
        config_snapshot = config.snapshot()

        common_kwargs: dict[str, Any] = {}

        # Start persistent workers once (use global default context)
        ctx = mp.get_context("spawn")
        for wid in range(self.max_workers):
            parent_conn, child_conn = Pipe(duplex=False)
            task_q = mp.Queue(-1)
            proc = ctx.Process(  # type: ignore
                target=_MainWorker(
                    worker_id=wid,
                    task_q=task_q,
                    event_conn=child_conn,
                    logging_queue=logging_queue,
                    config_snapshot=config_snapshot,
                    executor=self.executor,
                    common_kwargs=common_kwargs,
                )
            )
            proc.start()
            self.worker_connections.append(parent_conn)
            self.workers.append({"id": wid, "task_q": task_q, "proc": proc})
            self.idle_workers.append(wid)

        self.entered = True
        self.started_on = time.time()
        return self

    def __exit__(self, *args):
        self.entered = False
        self.started_on = -1.0
        self._shutdown_workers()
        self._stop_mp_logging()
        for c in self.worker_connections:
            try:
                c.close()
            except Exception:
                logger.exception("Error closing worker connection")
        self.worker_connections.clear()

    def _shutdown_workers(self) -> None:
        busy = set(self.busy_workers)
        for w in self.workers:
            try:
                w["task_q"].put(None)
            except Exception as e:
                logger.debug("task_q.put failed: %s", e)
        procs = [w["proc"] for w in self.workers]
        # Idle workers exit promptly on the sentinel.  Busy workers are told to
        # stop: SIGTERM makes them reap their job's whole process tree first.
        for w in self.workers:
            if w["id"] in busy:
                try:
                    w["proc"].terminate()
                except Exception as e:
                    logger.debug("proc.terminate failed: %s", e)
        try:
            terminate_procs(procs)
        except Exception as e:
            logger.debug("terminate_procs failed: %s", e)
        self.workers.clear()
        self.idle_workers.clear()
        self.busy_workers.clear()

    def _start_mp_logging(self) -> None:
        self._store["logging_queue"] = logging_queue = mp.Queue(-1)
        root = logging.get_logger("root")
        handlers: list[logging.builtin_logging.Handler] = []
        # The listener's stream handler must stay at INFO or above even when
        # -d is active.  The listener runs in the parent process in a daemon
        # thread that is *not* under LiveReporter's Rich console, so any
        # sub-INFO records it emits would write raw text directly to stderr
        # and corrupt the live table.  DEBUG records from worker processes
        # are therefore routed only to the JSON log file (below), which is
        # the correct durable destination for per-job debug output.
        handlers.append(logging.stream_handler(logging.INFO))
        for h in root.handlers:
            if isinstance(h, logging.FileHandler) and isinstance(
                h.formatter, logging.JsonFormatter
            ):
                f = Path(h.baseFilename).absolute()
                handlers.append(logging.json_file_handler(f, h.level))
                self._store.setdefault("json_file_handlers", []).append(f)
        listener = logging.QueueListener(logging_queue, *handlers, respect_handler_level=True)
        listener.start()
        self._store["logging_listener"] = listener
        root.handlers.clear()
        root.addHandler(logging.QueueHandler(logging_queue))

    def _stop_mp_logging(self) -> None:
        if listener := self._store.pop("logging_listener", None):
            listener.stop()
        logging.clear_handlers()
        logging.add_handler(logging.stream_handler())
        for file in self._store.pop("json_file_handlers", []):
            h = logging.json_file_handler(file)
            logging.add_handler(h)
        if logging_queue := self._store.pop("logging_queue", None):
            logging_queue.close()
            logging_queue.join_thread()

    def run(self, **kwargs: Any) -> int:
        if not self.entered:
            raise RuntimeError("ResourceQueueExecutor.run must be called in a context")

        logger.info(f"[bold]Starting[/] process pool with max {self.max_workers} workers")

        session_timeout = float(config.get("run:timeout:session", -1))
        qrank, qsize = 0, len(self.queue)
        start = time.time()

        def on_terminate(signum: int, frame: Any) -> None:
            raise SessionTerminated(signum)

        previous_handlers = procutil.install_termination_handlers(
            procutil.termination_signals(), on_terminate
        )
        try:
            return self._run(start, session_timeout, qrank, qsize, **kwargs)
        finally:
            procutil.restore_handlers(previous_handlers)

    def _run(
        self, start: float, session_timeout: float, qrank: int, qsize: int, **kwargs: Any
    ) -> int:
        reporter = LiveReporter(self) if self.live_reporting() else EventReporter(self)
        with reporter:
            drain = False
            while True:
                try:
                    if drain:
                        # Draining happens inside the ``try`` so that an interrupt,
                        # ``canary.kill`` or session timeout raised while waiting for
                        # the last jobs still goes through the cleanup handlers below.
                        self._wait_all(start, session_timeout, reporter=reporter)
                        break

                    if session_timeout >= 0.0 and time.time() - start > session_timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks()
                        raise TimeoutError(
                            f"Test session exceeded time out of {session_timeout} s."
                        )

                    self._check_finished_processes()
                    self._check_for_leaks()
                    reporter.poll()

                    # Wait for an idle worker
                    while not self.idle_workers:
                        self._check_finished_processes()
                        self._check_for_leaks()
                        if session_timeout >= 0.0 and time.time() - start > session_timeout:
                            self._terminate_all(signal.SIGUSR2)
                            self._check_for_leaks()
                            raise TimeoutError(
                                f"Test session exceeded time out of {session_timeout} s."
                            )
                        reporter.poll()
                        time.sleep(self.busy_wait_time)

                    job = self.queue.get()
                    qrank += 1

                    wid = self.idle_workers.pop()
                    self.busy_workers[wid] = job.id
                    slot = ExecutionSlot(job=job, qrank=qrank, qsize=qsize, worker_id=wid)
                    self.slots_by_id[job.id] = slot
                    self.submitted[job.id] = slot

                    self.workers[wid]["task_q"].put((job, kwargs))

                except Busy:
                    if not self.inflight:
                        pending = list(self.queue.pending())
                        reason = (
                            "Job could not be scheduled: no runnable job could acquire resources "
                            "or satisfy dependencies"
                        )
                        for job in pending:
                            if job.state.is_done():
                                continue
                            try:
                                job.set_status(outcome="BLOCKED", reason=reason)
                                job.state.phase = JobPhase.DONE
                                job.save()
                            except Exception:
                                logger.exception("Failed to mark blocked job %s", job.id[:7])
                        break
                    time.sleep(self.busy_wait_time)

                except Empty:
                    drain = True

                except CanaryKill:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt as e:
                    reason = None
                    if isinstance(e, SessionTerminated):
                        reason = f"Session terminated by {e.signame}"
                    self._terminate_all(signal.SIGINT, reason=reason)
                    self._check_for_leaks()
                    raise

        return compute_returncode(self.queue.jobs())

    def notify_listeners(self, event: ExecutionEvent) -> None:
        for cb in self.listeners:
            try:
                cb(event)
            except Exception:
                logger.exception("Execution listener failed for event %s", event.name)
        if self.event_bus is not None:
            self.event_bus.publish(Event(name=event.name, payload=self._event_payload(event)))

    @staticmethod
    def _event_payload(event: ExecutionEvent) -> dict[str, Any]:
        """Project the (slot,) notify args into a primitives-only bus payload.

        The internal listener path above still receives the live ``ExecutionSlot``;
        the bus gets a :class:`~_canary.events.JobEvent` so no runtime object
        crosses the interface boundary.  Returns an empty payload when there is
        no slot (e.g. session-level events).
        """
        payload: dict[str, Any] = dict(event.payload)
        slot = event.slot
        if slot is None:
            return payload
        job = getattr(slot, "job", None)
        if job is None:
            return payload
        job_event = project_job_event(
            job,
            qrank=getattr(slot, "qrank", -1),
            qsize=getattr(slot, "qsize", -1),
            worker_id=getattr(slot, "worker_id", -1),
        )
        payload["job"] = job_event
        return payload

    def _check_finished_processes(self) -> None:

        def validate(msg: Any) -> dict[str, Any] | None:
            if not isinstance(msg, dict):
                logger.warning("Malformed worker message: %r", msg)
                return None
            assert isinstance(msg, dict)
            if "job_id" not in msg or "worker_id" not in msg:
                logger.warning("Malformed worker message: %r", msg)
                return None
            return msg

        self._check_for_leaks()

        if Path("canary.kill").exists():
            Path("canary.kill").unlink()
            raise CanaryKill

        ready = wait(self.worker_connections, timeout=0)
        for conn in ready:
            if not isinstance(conn, Connection):
                continue
            try:
                msg = conn.recv()
            except (EOFError, OSError) as e:
                self._handle_dead_worker_conn(conn, e)
                continue
            if payload := validate(msg):
                self._handle_worker_payload(payload)
            while conn.poll(0.0):
                try:
                    if not conn.poll(0.0):
                        break
                    msg = conn.recv()
                except (EOFError, OSError) as e:
                    self._handle_dead_worker_conn(conn, e)
                    break
                if payload := validate(msg):
                    self._handle_worker_payload(payload)

    def _handle_worker_payload(self, payload: dict[str, Any]) -> None:

        job_id: str = payload["job_id"]
        wid: int = payload["worker_id"]

        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return

        if event := payload.get("event"):
            if event == "job_submitted":
                slot.on_submit(float(payload["timestamp"]))
                self.notify_listeners(ExecutionEvent(name=event, slot=slot))
                return

            if event == "job_staged":
                slot.on_stage(float(payload["timestamp"]))
                self.notify_listeners(ExecutionEvent(name=event, slot=slot))
                return

            if event == "job_started":
                slot.on_start(float(payload["timestamp"]))
                self.running[job_id] = slot
                self.submitted.pop(job_id, None)
                self.notify_listeners(ExecutionEvent(name=event, slot=slot))
                return

            if event == "job_stopped":
                slot.on_stop(float(payload["timestamp"]))
                self.notify_listeners(ExecutionEvent(name=event, slot=slot))
                return

            if event == "job_updated":
                # This job, running in a different process, is passing updated attributes
                attrs = payload.get("attrs", {})
                if not isinstance(attrs, dict):
                    logger.warning(f"Malformed job_updated payload: {payload!r}")
                    return
                for name, value in attrs.items():
                    if isinstance(name, str) and not name.startswith("_"):
                        setattr(slot.job, name, value)
                detail = payload.get("detail")
                event_payload: dict[str, Any] = {"attrs": attrs}
                if isinstance(detail, str) and detail:
                    event_payload["detail"] = detail
                self.notify_listeners(ExecutionEvent(name=event, slot=slot, payload=event_payload))
                return

            if event == "job_finished":
                # job_started event sent by worker process
                try:
                    slot.job.refresh()
                except Exception:
                    logger.exception(f"Post-processing failed for job {slot.job}")
                    slot.job.set_status(outcome="ERROR", reason="Post-processing failure")
                    try:
                        slot.job.save()
                    except Exception as e:
                        logger.debug("job.save failed: %s", e)
                finally:
                    finished_at = float(payload.get("timestamp", time.time()))
                    slot.on_finish(finished_at)
                    self.finished[job_id] = slot
                    self.running.pop(job_id, None)
                    self.submitted.pop(job_id, None)
                    self.queue.done(slot.job)
                    self.busy_workers.pop(wid, None)
                    self.idle_workers.append(wid)
                    self.notify_listeners(ExecutionEvent(name=event, slot=slot))
                return

            if event == "job_timeout":
                applied = payload.get("timeout")
                if not isinstance(applied, (int, float)):
                    applied = config.timeout_multiplier() * slot.job.timeout
                reason = f"Job timed out after {float(applied):.1f} s (worker watchdog)."

                self._finish_abnormal_slot(slot, outcome="TIMEOUT", reason=reason)

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.queue.done(slot.job)
                self.busy_workers.pop(wid, None)
                self.idle_workers.append(wid)
                self.notify_listeners(ExecutionEvent(name="job_finished", slot=slot))
                return

            if event == "job_died":
                exitcode = payload.get("exitcode", None)

                reason = "Worker job process died unexpectedly"
                code = -1

                if isinstance(exitcode, int):
                    code = exitcode
                    if exitcode < 0:
                        reason += f" (signal {-exitcode})"
                    else:
                        reason += f" (exitcode {exitcode})"

                self._finish_abnormal_slot(slot, outcome="ERROR", reason=reason, code=code)

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.queue.done(slot.job)
                self.busy_workers.pop(wid, None)
                self.idle_workers.append(wid)
                self.notify_listeners(ExecutionEvent(name="job_finished", slot=slot))
                return

            logger.warning(f"Unexpected worker payload for {job_id[:7]}: {payload}")

    def _finish_abnormal_slot(
        self, slot: ExecutionSlot, *, outcome: str, reason: str, code: int = -1
    ) -> None:
        """
        Finish a slot for abnormal executor-side terminal events.

        This is used when the worker reports timeout/death rather than the normal
        job_finished event. If we never observed a start event, treat the job as
        having started at submit/spawn time so the timer has a meaningful Running
        phase instead of a zero-duration finish.

        """
        now = time.time()
        try:
            slot.job.refresh()
        except Exception as e:
            logger.debug("job.refresh failed during abnormal finish: %s", e)

        slot.on_finish(now)
        slot.job.set_status(outcome=outcome, reason=reason, code=code)
        try:
            slot.job.save()
        except Exception as e:
            logger.debug("job.save failed during abnormal finish: %s", e)

    def _handle_dead_worker_conn(self, conn: Connection, exc: BaseException) -> None:
        # map conn -> wid
        try:
            wid = self.worker_connections.index(conn)
        except ValueError:
            logger.critical("Lost unknown worker connection: %r (%s)", conn, exc)
            return

        job_id = self.busy_workers.get(wid)

        logger.critical(
            "Worker %d IPC channel closed (%s). job_id=%s. "
            "This usually means the worker or inner job process crashed (e.g., SIGBUS).",
            wid,
            repr(exc),
            job_id,
        )

        p = self.workers[wid]["proc"]
        exitcode = getattr(p, "exitcode", None)
        if exitcode is not None and exitcode < 0:
            signum = -exitcode
            logger.critical("Worker %d exited due to signal %d", wid, signum)

        # If a job was in flight, mark it as died so the queue can continue
        if job_id:
            self._handle_worker_payload({"job_id": job_id, "worker_id": wid, "event": "job_died"})

        # Make the executor robust: retire the worker and optionally restart it
        self._retire_and_restart_worker(wid)

    def _retire_and_restart_worker(self, wid: int) -> None:
        # remove old conn from wait list by replacing it
        old = self.workers[wid]
        try:
            old["task_q"].close()
        except Exception as e:
            logger.debug("task_q.close failed: %s", e)
        try:
            terminate_proc(old["proc"])
        except Exception as e:
            logger.debug("proc.close failed: %s", e)
        try:
            self.worker_connections[wid].close()
        except Exception as e:
            logger.debug("worker_connection.close failed: %s", e)

        # start new worker
        logging_queue: mp.Queue = self._store["logging_queue"]
        config_snapshot = config.snapshot()
        common_kwargs: dict[str, Any] = {}

        ctx = mp.get_context("spawn")
        parent_conn, child_conn = Pipe(duplex=False)
        task_q = mp.Queue(-1)
        proc = ctx.Process(  # type: ignore
            target=_MainWorker(
                worker_id=wid,
                task_q=task_q,
                event_conn=child_conn,
                logging_queue=logging_queue,
                config_snapshot=config_snapshot,
                executor=self.executor,
                common_kwargs=common_kwargs,
            )
        )
        proc.start()

        self.worker_connections[wid] = parent_conn
        self.workers[wid] = {"id": wid, "task_q": task_q, "proc": proc}

        # ensure wid is available again
        self.busy_workers.pop(wid, None)
        if wid not in self.idle_workers:
            self.idle_workers.append(wid)

    def _check_for_leaks(self) -> None:
        # NOTE: still reads queue internals; ideally ResourceQueue should provide a safe accessor.
        busy_ids = set(self.queue._busy)
        inflight_ids = {slot.job.id for slot in self.inflight.values()}
        if busy_ids != inflight_ids:
            leaked = busy_ids - inflight_ids
            missing = inflight_ids - busy_ids
            logger.critical(f"Busy/inflight mismatch leaked={leaked}, missing={missing}")
            raise StuckQueueError("Busy/inflight mismatch")
        terminal_busy = {job.id for job in self.queue._busy.values() if job.state.is_done()}
        if terminal_busy:
            logger.critical(f"Terminal jobs still marked busy: {','.join(terminal_busy)}")
            raise StuckQueueError(f"Terminal jobs still busy: {terminal_busy}")

    def _wait_all(self, start: float, timeout: float, *, reporter: Any | None = None) -> None:
        while True:
            if not self.inflight:
                break
            if timeout >= 0.0 and time.time() - start > timeout:
                self._terminate_all(signal.SIGUSR2)
                self._check_for_leaks()
                raise TimeoutError(f"Test session exceeded time out of {timeout} s.")
            self._check_finished_processes()
            self._check_for_leaks()
            if reporter is not None:
                reporter.poll()
            time.sleep(self.busy_wait_time)

    def _terminate_all(self, signum: int, reason: str | None = None) -> None:
        if signum == signal.SIGINT:
            stat = "INTERRUPTED"
            reason = reason or "Keyboard interrupt"
            code = int(signal.SIGINT)
        else:
            stat = "ERROR"
            reason = reason or f"Job terminated with signal {signum}"
            code = -1

        inflight_slots = list(self.inflight.values())
        self.running.clear()
        self.submitted.clear()

        for slot in inflight_slots:
            try:
                self._close_slot_abnormally(slot, outcome=stat, reason=reason, code=code)
            except Exception:
                logger.exception(f"Unexpected error terminating job {slot.job.id[:7]}")

            finally:
                self.finished[slot.job.id] = slot

                try:
                    self.queue.done(slot.job)
                except Exception as e:
                    logger.debug("queue.done failed: %s", e)

                self.notify_listeners(ExecutionEvent(name="job_finished", slot=slot))

        self._shutdown_workers()
        self.queue.clear(stat, reason=reason, code=code)

    def _close_slot_abnormally(
        self,
        slot: ExecutionSlot,
        *,
        outcome: str,
        reason: str,
        code: int = -1,
        when: float | None = None,
    ) -> None:
        now = time.time() if when is None else float(when)

        try:
            slot.job.refresh()
        except Exception as e:
            logger.debug("job.refresh failed during abnormal close: %s", e)
        slot.on_finish(now)
        slot.job.set_status(outcome=outcome, reason=reason, code=code)
        try:
            slot.job.save()
        except Exception as e:
            logger.debug("job.save failed during abnormal close: %s", e)


def terminate_procs(procs: list, *, exit_timeout: float = 2.0) -> None:
    """Stop worker processes: wait briefly, then SIGTERM, then SIGKILL; always reap.

    Workers handle SIGTERM by reaping their current job's process tree, which
    takes up to :func:`~_canary.util.procutil.kill_grace_period` seconds, so we
    allow for that before escalating.
    """
    procs = [p for p in procs if p is not None]

    def alive() -> list:
        out = []
        for p in procs:
            try:
                if p.is_alive():
                    out.append(p)
            except ValueError:  # already closed
                continue
        return out

    procutil.wait_for(lambda: not alive(), exit_timeout)
    for p in alive():
        try:
            p.terminate()
        except Exception as e:
            logger.debug("terminate failed: %s", e)
    procutil.wait_for(lambda: not alive(), procutil.kill_grace_period() + 3.0)
    for p in alive():
        try:
            pid = p.pid
            if isinstance(pid, int):
                procutil.kill_process_tree(pid, sig=signal.SIGKILL, grace=0.5)
            p.kill()
        except Exception as e:
            logger.debug("kill failed: %s", e)
    for p in procs:
        try:
            p.join(timeout=1.0)
            if not p.is_alive():
                p.close()
        except Exception as e:
            logger.debug("join/close failed: %s", e)


def terminate_proc(proc) -> None:
    """Stop a single worker process (see :func:`terminate_procs`)."""
    terminate_procs([proc], exit_timeout=0.0)


class CanaryKill(Exception):
    pass


class StuckQueueError(Exception):
    pass


class ParentGone(Exception):
    pass
