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

from . import config
from .error import StopExecution
from .job import BaseJob
from .job import JobPhase
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue
from .reporter import EventReporter
from .reporter import LiveReporter
from .util import logging
from .util import multiprocessing as mp
from .util.misc import boolean
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)

EventTypes = Literal["job_submitted", "job_staged", "job_started", "job_stopped", "job_finished"]


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

    def __call__(self) -> None:
        config.load_snapshot(self.config_snapshot)
        try:
            self.run()
        except ParentGone:
            return
        finally:
            self.cleanup_all()

    def run(self) -> None:
        while True:
            msg = self.task_q.get()
            if msg is None:
                return
            job, per_job_kwargs = msg
            self.run_one_job(job, per_job_kwargs or {})

    def run_one_job(self, job: BaseJob, per_job_kwargs: dict[str, Any]) -> None:
        # IMPORTANT: use mp.Queue (not SimpleQueue) so we can do get(timeout=...)
        self.local_q = mp.Queue()
        proc: BaseProcess = self.ctx.Process(
            target=JobFunctor(),
            args=(self.executor, job, self.local_q, self.logging_queue, self.config_snapshot),
            kwargs={**self.common_kwargs, **per_job_kwargs},
        )
        self.proc = proc
        proc.start()

        try:
            self.monitor_job(job)
        finally:
            self.cleanup_job()

    def monitor_job(self, job: BaseJob) -> None:
        proc = self.proc
        local_q = self.local_q
        if local_q is None:
            raise RuntimeError("monitor_job called without active proc/local_q")

        job_id = job.id

        total_timeout = float(job.total_timeout())
        watchdog_grace = float(
            os.getenv(
                "CANARY_WORKER_WATCHDOG_GRACE", str(max(300.0, min(1800.0, 0.10 * total_timeout)))
            )
        )
        watchdog_deadline = time.time() + total_timeout + watchdog_grace

        def terminate_and_report(event: str, **extra: Any) -> None:
            logger.warning(
                "Terminating worker for job %s: event=%s timeout=%s grace=%s extra=%r",
                job_id[:7],
                event,
                total_timeout,
                watchdog_grace,
                extra,
            )

            pid = getattr(proc, "pid", None)
            if isinstance(pid, int):
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception as e:
                    logger.debug("os.kill(SIGTERM) failed pid=%s: %s", pid, e)

                time.sleep(0.05)

                try:
                    if proc.is_alive():
                        os.kill(pid, signal.SIGKILL)
                except Exception as e:
                    logger.debug("os.kill(SIGKILL) failed pid=%s: %s", pid, e)

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
                    "job_timeout", phase="watchdog", timeout=total_timeout, grace=watchdog_grace
                )
                return

            if not proc.is_alive():
                payload.update({"event": "job_died", "exitcode": getattr(proc, "exitcode", None)})
                self.send(payload)
                return

            time.sleep(self.poll_sleep)

    def cleanup_job(self) -> None:
        if self.local_q is not None:
            try:
                self.local_q.close()
            except Exception as e:
                logger.debug("local_q.close failed: %s", e)
            self.local_q = None

        if self._proc is not None:
            try:
                self._proc.join(timeout=0.1)
                self._proc.close()
            except Exception as e:
                logger.debug("proc.close failed: %s", e)
            self._proc = None

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
    ):
        self.max_workers = mp.max_workers(hint=max_workers)
        self.queue: ResourceQueue = queue
        self.executor = executor
        self.busy_wait_time = busy_wait_time

        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}
        self.entered: bool = False
        self.started_on: float = -1.0
        self._store: dict[str, Any] = {}
        self.alogger = logging.AdaptiveDebugLogger(logger.name)
        self.listeners: list[Callable[..., None]] = []

        # worker infrastructure
        self.workers: list[dict[str, Any]] = []
        self.worker_connections: list[Connection] = []
        self.idle_workers: list[int] = []
        self.busy_workers: dict[int, str] = {}  # worker_id -> job_id
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        style = config.getoption("console_style") or {}
        self.live_reporting = style.get("live", True)
        if config.get("debug"):
            self.live_reporting = False
        if not sys.stdin.isatty():
            self.live_reporting = False
        if "CANARY_LIVE" in os.environ and not boolean(os.environ["CANARY_LIVE"]):
            self.live_reporting = False
        elif int(os.getenv("CANARY_LEVEL", "0")) > 0:
            self.live_reporting = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            self.live_reporting = False

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    def add_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
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
        for w in self.workers:
            try:
                w["task_q"].put(None)
            except Exception as e:
                logger.debug("task_q.put failed: %s", e)
        for w in self.workers:
            try:
                terminate_proc(w["proc"])
            except Exception as e:
                logger.debug("proc.close failed: %s", e)
        self.workers.clear()
        self.idle_workers.clear()
        self.busy_workers.clear()

    def _start_mp_logging(self) -> None:
        self._store["logging_queue"] = logging_queue = mp.Queue(-1)
        root = logging.get_logger("root")
        handlers: list[logging.builtin_logging.Handler] = []
        handlers.append(logging.stream_handler())
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

        reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)
        with reporter:
            while True:
                try:
                    if session_timeout >= 0.0 and time.time() - start > session_timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks()
                        raise TimeoutError(
                            f"Test session exceeded time out of {session_timeout} s."
                        )

                    self._check_finished_processes()
                    self._check_for_leaks()

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
                    time.sleep(self.busy_wait_time)

                except Empty:
                    self._wait_all(start, session_timeout)
                    break

                except CanaryKill:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise

        return compute_returncode(self.queue.jobs())

    def notify_listeners(self, event: EventTypes, *args: Any) -> None:
        for cb in self.listeners:
            cb(event, *args)

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
                self.notify_listeners(event, slot)
                return

            if event == "job_staged":
                slot.on_stage(float(payload["timestamp"]))
                self.notify_listeners(event, slot)
                return

            if event == "job_started":
                slot.on_start(float(payload["timestamp"]))
                self.running[job_id] = slot
                self.submitted.pop(job_id, None)
                self.notify_listeners(event, slot)
                return

            if event == "job_stopped":
                slot.on_stop(float(payload["timestamp"]))
                self.notify_listeners(event, slot)
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
                    self.notify_listeners(event, slot)
                    self.busy_workers.pop(wid, None)
                    self.idle_workers.append(wid)
                return

            if event == "job_timeout":
                reason = f"Job timed out after {slot.job.total_timeout()} s."

                self._finish_abnormal_slot(slot, outcome="TIMEOUT", reason=reason)

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)
                self.busy_workers.pop(wid, None)
                self.idle_workers.append(wid)
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
                self.notify_listeners("job_finished", slot)
                self.busy_workers.pop(wid, None)
                self.idle_workers.append(wid)
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

        For HPC batches (jobs that expose a ``finalize_status_from_child_jobs``
        method) we first refresh child lockfiles from disk.  If all children
        have already reached a terminal state the batch status is derived from
        the real child outcomes rather than the abnormal executor event; the
        abnormal event is recorded as a warning so the discrepancy is visible
        in logs.  This handles the case where the worker process was killed by
        the outer watchdog after the scheduler already completed the batch but
        before the subprocess could send ``job_finished``.
        """
        now = time.time()
        try:
            slot.job.refresh()
        except Exception as e:
            logger.debug("job.refresh failed during abnormal finish: %s", e)

        # For HPC batches: check whether all child jobs finished successfully
        # on disk before trusting the abnormal executor-level outcome.
        if hasattr(slot.job, "finalize_status_from_child_jobs"):
            try:
                slot.job.finalize_status_from_child_jobs()
                if not slot.job.status.is_unset():
                    # Children have a real terminal status — use it and warn.
                    logger.warning(
                        "Batch %s: abnormal executor event (%s: %s) but child "
                        "jobs have terminal status %s — using child-derived "
                        "status.  The worker process may have been killed after "
                        "the scheduler job completed.",
                        slot.job.id[:7],
                        outcome,
                        reason,
                        slot.job.status.outcome.name,
                    )
                    slot.job.state.phase = JobPhase.DONE
                    slot.job._allocation["state"] = "inactive"
                    try:
                        slot.job.save()
                    except Exception as e:
                        logger.debug("job.save failed after child reconciliation: %s", e)
                    return
            except Exception as e:
                logger.debug("finalize_status_from_child_jobs failed during abnormal finish: %s", e)

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

    def _wait_all(self, start: float, timeout: float) -> None:
        while True:
            if not self.inflight:
                break
            if timeout >= 0.0 and time.time() - start > timeout:
                self._terminate_all(signal.SIGUSR2)
                self._check_for_leaks()
                raise TimeoutError(f"Test session exceeded time out of {timeout} s.")
            self._check_finished_processes()
            self._check_for_leaks()
            time.sleep(self.busy_wait_time)

    def _terminate_all(self, signum: int) -> None:
        stat = "CANCELLED" if signum == signal.SIGINT else "ERROR"
        reason = f"Job terminated with signal {signum}"

        inflight_slots = list(self.inflight.values())
        self.running.clear()
        self.submitted.clear()

        for slot in inflight_slots:
            try:
                self._close_slot_abnormally(slot, outcome=stat, reason=reason)
            except Exception:
                logger.exception(f"Unexpected error terminating job {slot.job.id[:7]}")

            finally:
                self.finished[slot.job.id] = slot

                try:
                    self.queue.done(slot.job)
                except Exception as e:
                    logger.debug("queue.done failed: %s", e)

                self.notify_listeners("job_finished", slot)

        self._shutdown_workers()
        self.queue.clear(stat)

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


def terminate_proc(proc):
    i = 0
    while i < 3 and proc.is_alive():
        proc.terminate()
        proc.join(timeout=0.5)
        i += 1
    proc.close()


class CanaryKill(Exception):
    pass


class StuckQueueError(Exception):
    pass


class ParentGone(Exception):
    pass
