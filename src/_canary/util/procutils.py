# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import warnings

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
