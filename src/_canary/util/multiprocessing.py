# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import multiprocessing
import multiprocessing.context
import multiprocessing.queues
import multiprocessing.shared_memory
import os
import pickle  # nosec B403
import time
from typing import Any

import psutil

from . import logging

logger = logging.get_logger(__name__)


def put_in_shared_memory(obj: Any) -> tuple[str, int]:
    data = pickle.dumps(obj)
    size = len(data)
    shared_mem = multiprocessing.shared_memory.SharedMemory(create=True, size=size)
    shared_mem.buf[:size] = data  # type: ignore
    return shared_mem.name, size


def get_from_shared_memory(name: str, size: int) -> Any:
    shared_mem = multiprocessing.shared_memory.SharedMemory(name=name)
    data = bytes(shared_mem.buf[:size])  # type: ignore
    return pickle.loads(data)  # nosec B301


def unlink_shared_memory(name: str) -> None:
    shared_mem = multiprocessing.shared_memory.SharedMemory(name=name)
    shared_mem.unlink()


class SimpleQueue(multiprocessing.queues.SimpleQueue):
    def __init__(self) -> None:
        super().__init__(ctx=multiprocessing.context._default_context)


class Queue(multiprocessing.queues.Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize, ctx=multiprocessing.context._default_context)


class MeasuredProcess(multiprocessing.Process):
    """A Process subclass that collects resource usage metrics using psutil.
    Metrics are sampled each time is_alive() is called.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.samples = []
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
                except Exception:
                    pass  # nosec B110

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
        if self.pid is not None:
            os.kill(self.pid, signum)
        time.sleep(grace_period)
        self.kill()


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
