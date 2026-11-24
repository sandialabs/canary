# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""canary_hpc's application layer: what ``canary hpc run`` and ``/canary/hpc/run`` both call.

Each interface fills canary's options object its own way (the command line, an API
request) and hands it here; nothing here knows which one did.
"""

import argparse

import canary

from .conductor import CanaryHPCConductor


def run(options: argparse.Namespace) -> int:
    """Batch the selected jobs and run them through the HPC scheduler ``options.hpc_backend``.

    Returns the session's exit code.
    """
    hpc_backend = getattr(options, "hpc_backend", None)
    if hpc_backend is None:
        raise ValueError("canary hpc run requires --backend")
    conductor = CanaryHPCConductor(backend=hpc_backend)
    conductor.register(canary.config.pluginmanager)
    return conductor.run(options)
