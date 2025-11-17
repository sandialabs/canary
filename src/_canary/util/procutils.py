# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import multiprocessing
import os
import time
import warnings
from typing import Any

import psutil

from . import logging

logger = logging.get_logger(__name__)


def cleanup_children(pid: int | None = None, include_parent: bool = False) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        pid = pid or os.getpid()
        try:
            fd = os.open(os.devnull, os.O_WRONLY)
            stdout = os.dup(1)
            stderr = os.dup(2)
            os.dup2(fd, 1)
            os.dup2(fd, 2)
            process = psutil.Process(pid)
            children = process.children(recursive=True)
            if include_parent:
                if pid == os.getpid():
                    raise ValueError("cannot kill self")
                children.append(process)
            for p in children:
                if p.is_running():
                    try:
                        p.terminate()
                    except BaseException:
                        pass
            _, alive = psutil.wait_procs(children, timeout=0.2)
            for p in alive:
                try:
                    p.kill()
                except BaseException:
                    pass
        finally:
            os.dup2(stdout, 1)
            os.dup2(stderr, 2)
            os.close(fd)


def get_process_metrics(
    proc: psutil.Popen, metrics: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    # Collect process information
    metrics = metrics or {}
    try:
        valid_names = set(psutil._as_dict_attrnames)
        skip_names = {
            "cmdline",
            "cpu_affinity",
            "net_connections",
            "cwd",
            "environ",
            "exe",
            "gids",
            "ionice",
            "memory_full_info",
            "memory_maps",
            "threads",
            "name",
            "nice",
            "pid",
            "ppid",
            "status",
            "terminal",
            "uids",
            "username",
        }
        names = valid_names - skip_names
        new_metrics = proc.as_dict(names)
    except psutil.NoSuchProcess:
        logger.debug(f"Process with PID {proc.pid} does not exist.")
    except psutil.AccessDenied:
        logger.debug(f"Access denied to process with PID {proc.pid}.")
    except psutil.ZombieProcess:
        logger.debug(f"Process with PID {proc.pid} is a Zombie process.")
    else:
        for name, metric in new_metrics.items():
            if name == "open_files":
                files = metrics.setdefault("open_files", [])
                for f in metric:
                    if f[0] not in files:
                        files.append(f[0])
            elif name == "cpu_times":
                metrics["cpu_times"] = {"user": metric.user, "system": metric.system}
            elif name in ("num_threads", "cpu_percent", "num_fds", "memory_percent"):
                n = metrics.setdefault(name, 0)
                metrics[name] = max(n, metric)
            elif name == "memory_info":
                for key, val in metric._asdict().items():
                    n = metrics.setdefault(name, {}).setdefault(key, 0)
                    metrics[name][key] = max(n, val)
            elif hasattr(metric, "_asdict"):
                metrics[name] = dict(metric._asdict())
            else:
                metrics[name] = metric
    finally:
        return metrics


class MeasuredProcess(multiprocessing.Process):
    """A Process subclass that collects resource usage metrics using psutil.
    Metrics are sampled each time is_alive() is called.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.samples: list[dict[str, float]] = []
        self._psutil_process = None
        self._start_time = None

    def start(self):
        """Start the process and initialize psutil monitoring."""
        super().start()
        self._start_time = time.time()
        try:
            self._psutil_process = psutil.Process(self.pid)
        except Exception:
            logger.warning(f"Could not attach psutil to process {self.pid}")
            self._psutil_process = None

    def _sample_metrics(self):
        """Sample current process metrics."""
        if not psutil or not self._psutil_process:
            return

        try:
            # Get process info
            with self._psutil_process.oneshot():
                cpu_percent = self._psutil_process.cpu_percent()
                mem_info = self._psutil_process.memory_info()

                sample = {
                    "timestamp": time.time(),
                    "cpu_percent": cpu_percent,
                    "memory_rss_mb": mem_info.rss / (1024 * 1024),  # RSS in MB
                    "memory_vms_mb": mem_info.vms / (1024 * 1024),  # VMS in MB
                }

                # Add number of threads if available
                try:
                    sample["num_threads"] = self._psutil_process.num_threads()
                except:
                    pass

                self.samples.append(sample)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have terminated
            pass
        except Exception as e:
            logger.debug(f"Error sampling metrics: {e}")

    def is_alive(self):
        """Check if process is alive and sample metrics."""
        alive = super().is_alive()
        if alive:
            self._sample_metrics()
        return alive

    def get_measurements(self):
        """Calculate statistics from collected samples.
        Returns a dict with min, max, avg for each metric.
        """
        if not self.samples:
            return {
                "duration": time.time() - self._start_time if self._start_time else 0,
                "samples": 0,
            }

        measurements = {
            "duration": time.time() - self._start_time if self._start_time else 0,
            "samples": len(self.samples),
        }

        # Calculate stats for each metric
        metrics = ["cpu_percent", "memory_rss_mb", "memory_vms_mb", "num_threads"]

        for metric in metrics:
            values = [s[metric] for s in self.samples if metric in s]
            if values:
                measurements.setdefault(metric, {})["min"] = min(values)
                measurements.setdefault(metric, {})["max"] = max(values)
                measurements.setdefault(metric, {})["ave"] = sum(values) / len(values)

        return measurements

    def shutdown(self, signum: int, grace_period: float = 0.05) -> None:
        logger.debug(f"Terminating process {self.pid}")
        self._sample_metrics()
        os.kill(self.pid, signum)
        time.sleep(grace_period)
        self.kill()
