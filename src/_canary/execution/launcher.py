# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Defines launchers for individual test jobs"""

import importlib.util
import os
import shlex
import signal
import subprocess
import sys
import time
import traceback
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generator
from typing import TextIO

import psutil

from .. import config
from ..core.error import TestTimedOut
from ..hookspec import hookimpl
from ..util import logging
from ..util.module import load as load_module
from ..util.shell import source_rcfile

if TYPE_CHECKING:
    from ..core.job import Job

logger = logging.get_logger(__name__)
StdErrorT = TextIO | int


class Launcher(ABC):
    @abstractmethod
    def run(self, job: "Job") -> int: ...


class SubprocessLauncher(Launcher):
    def __init__(self, args: list[str] | None = None) -> None:
        self.default_args: list[str] = list(args or [])

    @contextmanager
    def context(self, job: "Job") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        try:
            job.set_runtime_env(os.environ)
            for module in job.spec.modules or []:
                load_module(module)
            for rcfile in job.spec.rcfiles or []:
                source_rcfile(rcfile)
            os.chdir(job.workspace.dir)
            _write_env_json(job)
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def run(self, job: "Job") -> int:
        logger.debug(f"Starting {job.display_name()} on pid {os.getpid()}")
        with self.context(job):
            args: list[str] = list(job.spec.command)
            args.extend(self.default_args)
            if a := config.getoption("script_args"):
                args.extend(a)
            if a := job.get_attribute("script_args"):
                args.extend(a)
            if not args:
                raise RuntimeError(f"{job}: not command defined")
            job.add_measurement("command_line", shlex.join(args))
            stdout: TextIO = open(job.stdout, "a")
            stderr: StdErrorT = subprocess.STDOUT if job.stderr is None else open(job.stderr, "a")
            mp = MeasuredProcess(
                lambda: subprocess.Popen(
                    args, stdout=stdout, stderr=stderr, start_new_session=True
                ),
                name=f"{job.id[:7]}",
                sample_children=False,
            )
            try:
                mp.start()
                start = time.time()
                deadline = start + job.total_timeout()
                while True:
                    mp.sample_metrics()
                    rc = mp.poll()
                    if rc is not None:
                        job.measurements.update(mp.get_measurements())
                        logger.debug(f"Finished {job.display_name()}")
                        return rc

                    if time.time() > deadline:
                        # kill whole process group (requires start_new_session=True)
                        pid = mp.pid
                        if isinstance(pid, int):
                            pgid: int | None
                            try:
                                pgid = os.getpgid(pid)
                            except Exception:
                                pgid = None

                            # TERM then KILL
                            try:
                                if pgid is not None:
                                    os.killpg(pgid, signal.SIGTERM)
                                else:
                                    os.kill(pid, signal.SIGTERM)
                            except Exception:
                                pass  # nosec B110

                            time.sleep(0.1)

                            try:
                                if pgid is not None:
                                    os.killpg(pgid, signal.SIGKILL)
                                else:
                                    os.kill(pid, signal.SIGKILL)
                            except Exception:
                                pass  # nosec B110

                        raise TestTimedOut(f"Test exceeded timeout of {job.total_timeout():.1f} s")

                    time.sleep(0.1)
            finally:
                stdout.close()
                if not isinstance(stderr, int):
                    stderr.close()


class PythonFunctionLauncher(Launcher):
    """Launcher that imports a Python file and calls a function *in-process*.

    Used for the synthetic setup/teardown jobs injected from ``canaryconf.py``
    (see :mod:`_canary.canaryconf_impl`).  Rather than spawning
    ``python canaryconf.py`` as a subprocess, this launcher imports the file
    named by the job's ``canary_conftest["source_file"]`` attribute and calls
    the function selected by ``canary_conftest["role"]`` (``canary_setup`` or
    ``canary_teardown``) directly, passing the job's ``TestInstance`` as
    ``ctx``.

    The function runs with the current working directory set to the job's
    workspace directory (which mirrors the ``canaryconf.py``'s governing
    directory in the session tree) and with the job's runtime environment
    applied.  ``stdout``/``stderr`` produced by the function are captured to the
    job's output files.  A raised exception yields a non-zero return code so the
    job is marked failed and downstream tests are gated accordingly.
    """

    def run(self, job: "Job") -> int:
        from ..canaryconf_impl import ROLE_TO_FUNCTION
        from ..testinst import from_job

        logger.debug(f"Starting {job.display_name()} on pid {os.getpid()} (python function)")

        meta = job.get_attribute("canary_conftest") or {}
        role = meta.get("role")
        source_file = meta.get("source_file")
        if role not in ROLE_TO_FUNCTION:
            raise RuntimeError(f"{job}: unknown canary_conftest role {role!r}")
        if not source_file:
            raise RuntimeError(f"{job}: canary_conftest missing source_file")
        func_name = ROLE_TO_FUNCTION[role]

        job.add_measurement("command_line", f"{source_file}::{func_name}(ctx)")

        with self._context(job):
            module = self._import_source(Path(source_file))
            func = getattr(module, func_name, None)
            if not callable(func):
                raise RuntimeError(f"{job}: {source_file} does not define a callable {func_name!r}")
            ctx = from_job(job)
            start = time.time()
            stdout: TextIO = open(job.stdout, "a")
            stderr: StdErrorT = open(job.stderr, "a") if job.stderr is not None else stdout
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    func(ctx)
                rc = 0
            except Exception:
                traceback.print_exc(file=stderr)
                rc = 1
            finally:
                if stderr is not stdout and not isinstance(stderr, int):
                    stderr.close()
                stdout.close()
            job.add_measurement("duration", time.time() - start)
            logger.debug(f"Finished {job.display_name()} (rc={rc})")
            return rc

    @contextmanager
    def _context(self, job: "Job") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        try:
            job.set_runtime_env(os.environ)
            for module in job.spec.modules or []:
                load_module(module)
            for rcfile in job.spec.rcfiles or []:
                source_rcfile(rcfile)
            os.chdir(job.workspace.dir)
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    @staticmethod
    def _import_source(path: Path) -> Any:
        """Import *path* as an anonymous module without polluting ``sys.modules``."""
        name = f"_canary_conftest_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import canaryconf file {path!r}")
        module = importlib.util.module_from_spec(spec)
        # Register temporarily so dataclasses / typing lookups inside the module
        # resolve, then remove to avoid leaking state between jobs.
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
        return module


class MeasuredProcess:
    """
    Wrapper around subprocess.Popen that samples resource usage via psutil.

    Notes:
      - This is *not* a multiprocessing.Process. It's intended to measure the
        actual launched workload PID (e.g., mpiexec/srun) and later can be
        extended to include children.
      - Sampling is explicit: call sample_metrics() from your polling loop.
    """

    def __init__(
        self,
        factory: Callable[[], subprocess.Popen],
        *,
        name: str | None = None,
        sample_children: bool = False,
    ) -> None:
        """
        Args:
            popen_factory: thunk that returns a subprocess.Popen (or compatible) instance.
                          We use a factory so you can prepare args/env/cwd cleanly.
            name: optional name for logging/measurement labeling
            sample_children: if True, include direct+recursive children in aggregates (optional)
        """
        self.name = name or "popen"
        self.sample_children = sample_children

        self.factory = factory
        self.popen: subprocess.Popen | None = None

        self._ps: psutil.Process | None = None
        self._start_time: float | None = None
        self.samples: list[dict[str, Any]] = []

    # --- lifecycle ---------------------------------------------------------

    @property
    def pid(self) -> int | None:
        return None if self.popen is None else self.popen.pid

    @property
    def returncode(self) -> int | None:
        return None if self.popen is None else self.popen.returncode

    def start(self) -> None:
        if self.popen is not None:
            raise RuntimeError("MeasuredProcess.start() called twice")
        self.popen = self.factory()
        self._start_time = time.time()
        try:
            self._ps = psutil.Process(self.popen.pid)
        except Exception as e:
            logger.debug("MeasuredProcess: could not attach psutil to pid=%s: %s", self.pid, e)
            self._ps = None

    def poll(self) -> int | None:
        if self.popen is None:
            raise RuntimeError("MeasuredProcess.poll() called before start()")
        return self.popen.poll()

    def wait(self, timeout: float | None = None) -> int:
        if self.popen is None:
            raise RuntimeError("MeasuredProcess.wait() called before start()")
        return self.popen.wait(timeout=timeout)

    # --- termination -------------------------------------------------------

    def terminate(self) -> None:
        if self.popen is None:
            return
        try:
            self.popen.terminate()
        except Exception as e:
            logger.debug("MeasuredProcess.terminate failed pid=%s: %s", self.pid, e)

    def kill(self) -> None:
        if self.popen is None:
            return
        try:
            self.popen.kill()
        except Exception as e:
            logger.debug("MeasuredProcess.kill failed pid=%s: %s", self.pid, e)

    def shutdown(self, signum: int, grace_period: float = 0.05) -> None:
        """
        Best-effort: send `signum`, wait `grace_period`, then SIGKILL if still alive.
        """
        if self.popen is None:
            return
        self.sample_metrics()

        pid = self.pid
        if pid is None:
            return

        try:
            os.kill(pid, signum)
        except Exception as e:
            logger.debug("MeasuredProcess.shutdown os.kill(%s,%s) failed: %s", pid, signum, e)
            try:
                self.terminate()
            except Exception:  # nosec B110
                pass

        time.sleep(grace_period)
        try:
            if self.poll() is None:
                self.kill()
        except Exception:
            try:
                self.kill()
            except Exception:  # nosec B110
                pass

    # --- measurement API ---------------------------------------------------

    def _collect_one(self, p: psutil.Process) -> dict[str, Any] | None:
        try:
            with p.oneshot():
                mem = p.memory_info()
                return {
                    "cpu_percent": p.cpu_percent(),
                    "memory_rss_mb": mem.rss / (1024 * 1024),
                    "memory_vms_mb": mem.vms / (1024 * 1024),
                    "num_threads": p.num_threads(),
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None
        except Exception as e:
            logger.debug("MeasuredProcess metric read failed pid=%s: %s", getattr(p, "pid", "?"), e)
            return None

    def sample_metrics(self) -> None:
        """
        Append a sample dict to self.samples. Safe to call frequently.
        """
        if self._ps is None:
            return

        now = time.time()

        # Base process
        base = self._collect_one(self._ps)
        if base is None:
            return

        sample: dict[str, Any] = {"timestamp": now, **base}

        # Optional: children aggregation (off by default)
        if self.sample_children:
            try:
                children = self._ps.children(recursive=True)
            except Exception:
                children = []

            rss = base["memory_rss_mb"]
            vms = base["memory_vms_mb"]
            cpu = base["cpu_percent"]
            thr = base.get("num_threads", 0)

            nchildren = 0
            for ch in children:
                chm = self._collect_one(ch)
                if not chm:
                    continue
                nchildren += 1
                rss += chm["memory_rss_mb"]
                vms += chm["memory_vms_mb"]
                cpu += chm["cpu_percent"]
                thr += chm.get("num_threads", 0)

            sample["children"] = nchildren
            sample["cpu_percent_tree"] = cpu
            sample["memory_rss_mb_tree"] = rss
            sample["memory_vms_mb_tree"] = vms
            sample["num_threads_tree"] = thr

        self.samples.append(sample)

    def get_measurements(self) -> dict[str, Any]:
        """
        Summarize collected samples into min/max/ave by key.
        """
        duration = time.time() - self._start_time if self._start_time else 0.0
        measurements: dict[str, Any] = {"duration": duration, "samples": len(self.samples)}
        if not self.samples:
            return measurements

        # Keys we know we might emit
        keys = set().union(*(s.keys() for s in self.samples))
        keys.discard("timestamp")

        for k in sorted(keys):
            vals = [s[k] for s in self.samples if isinstance(s.get(k), (int, float))]
            if not vals:
                continue
            measurements[k] = {"min": min(vals), "max": max(vals), "ave": sum(vals) / len(vals)}
        return measurements


@hookimpl(specname="canary_runtest_launcher")
def canaryconf_job_launcher(case: "Job") -> Launcher | None:
    """Select :class:`PythonFunctionLauncher` for synthetic ``canaryconf.py`` jobs."""
    if case.get_attribute("canary_conftest"):
        return PythonFunctionLauncher()
    return None


@hookimpl(trylast=True, specname="canary_runtest_launcher")
def default_job_launcher(case: "Job") -> Launcher:
    return SubprocessLauncher()


def _write_env_json(job: "Job") -> None:
    """Write the current ``os.environ`` to ``env.json`` in the job workspace.

    Called from :meth:`SubprocessLauncher.context` immediately after
    :meth:`~_canary.core.job.Job.set_runtime_env` has injected the job's variables
    into ``os.environ`` — capturing exactly the environment the test subprocess
    will inherit.  Written best-effort; failures are logged at DEBUG and do not
    affect job execution.

    The file is a plain ``{"VAR": "value", ...}`` JSON object, queryable via
    ``canary query job <id> env`` or ``canary query job <id> env.KEY``.
    """
    import json as _json

    try:
        with job.workspace.openfile("env.json", "w") as fh:
            _json.dump(dict(os.environ), fh, sort_keys=True, indent=2)
    except Exception:
        logger.debug("Failed to write env.json for %s", job.id[:7], exc_info=True)
