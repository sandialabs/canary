# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Defines launchers for individual test cases"""

import os
import shlex
import signal
import subprocess
import time
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generator
from typing import TextIO

import psutil

from . import config
from .error import TestTimedOut
from .hookspec import hookimpl
from .util import logging
from .util.module import load as load_module
from .util.shell import source_rcfile

if TYPE_CHECKING:
    from .testcase import TestCase

logger = logging.get_logger(__name__)
StdErrorT = TextIO | int


class Launcher(ABC):
    @abstractmethod
    def run(self, case: "TestCase") -> int: ...


class SubprocessLauncher(Launcher):
    def __init__(self, args: list[str] | None = None) -> None:
        self.default_args: list[str] = list(args or [])

    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        try:
            case.set_runtime_env(os.environ)
            for module in case.spec.modules or []:
                load_module(module)
            for rcfile in case.spec.rcfiles or []:
                source_rcfile(rcfile)
            os.chdir(case.workspace.dir)
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def run(self, case: "TestCase") -> int:
        logger.debug(f"Starting {case.display_name()} on pid {os.getpid()}")
        with self.context(case):
            args: list[str] = list(case.spec.command)
            args.extend(self.default_args)
            if a := config.getoption("script_args"):
                args.extend(a)
            if a := case.get_attribute("script_args"):
                args.extend(a)
            if not args:
                raise RuntimeError(f"{case}: not command defined")
            case.add_measurement("command_line", shlex.join(args))
            stdout: TextIO = open(case.stdout, "a")
            stderr: StdErrorT = subprocess.STDOUT if case.stderr is None else open(case.stderr, "a")
            mp = MeasuredProcess(
                lambda: subprocess.Popen(
                    args, stdout=stdout, stderr=stderr, start_new_session=True
                ),
                name=f"{case.id[:7]}",
                sample_children=False,
            )
            try:
                mp.start()
                start = time.time()
                deadline = start + case.total_timeout()
                while True:
                    mp.sample_metrics()
                    rc = mp.poll()
                    if rc is not None:
                        case.measurements.update(mp.get_measurements())
                        logger.debug(f"Finished {case.display_name()}")
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

                        raise TestTimedOut(f"Test exceeded timeout of {case.total_timeout():.1f} s")

                    time.sleep(0.1)
            finally:
                stdout.close()
                if not isinstance(stderr, int):
                    stderr.close()


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
            measurements[k] = {
                "min": min(vals),
                "max": max(vals),
                "ave": sum(vals) / len(vals),
            }
        return measurements


@hookimpl(trylast=True, specname="canary_runtest_launcher")
def default_testcase_launcher(case: "TestCase") -> Launcher:
    return SubprocessLauncher()
