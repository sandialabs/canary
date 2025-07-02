# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import warnings
from typing import Any

import psutil

from . import logging


def cleanup_children(pid: int | None = None, include_parent: bool = False) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        pid = pid or os.getpid()
        logging.debug("killing child processes")
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
        logging.debug(f"Process with PID {proc.pid} does not exist.")
    except psutil.AccessDenied:
        logging.debug(f"Access denied to process with PID {proc.pid}.")
    except psutil.ZombieProcess:
        logging.debug(f"Process with PID {proc.pid} is a Zombie process.")
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
