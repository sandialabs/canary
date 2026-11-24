# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""``/canary/hpc/run``: ``canary hpc run`` as a request-server endpoint.

Registered through ``canary_addendpoint`` (see ``canary_hpc/__init__.py``).  Like
``/canary/run`` it fills canary's options object from the request and calls the same
application function as the ``canary hpc run`` command (:func:`canary_hpc.app.run`).
"""

from typing import Annotated
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from _canary.api.argv import Dest
from _canary.api.dispatch import Context
from _canary.api.models import Only
from _canary.api.work import check_run_paths
from _canary.api.work import exit_code
from _canary.api.work import options_for

from . import app


class HPCRunRequest(BaseModel):
    """Request for /canary/hpc/run endpoint (subprocess, async)."""

    model_config = ConfigDict(extra="forbid")

    pathspec: Annotated[list[str], Dest("runpaths")] = Field(
        default_factory=list,
        description="Paths, spec ids or a selection tag (none: the workspace's tests)",
    )
    backend: Annotated[str, Dest("hpc_backend")] = Field(
        ..., description="HPC scheduler backend (slurm, pbs, lsf)"
    )
    keyword: Annotated[str | None, Dest("keyword_exprs")] = Field(
        default=None, description="Keyword expression"
    )
    owner: Annotated[str | None, Dest("owners")] = Field(
        default=None, description="Filter by test owner"
    )
    parameter: Annotated[str | None, Dest("parameter_expr")] = Field(
        default=None, description="Parameter expression"
    )
    regex: Annotated[str | None, Dest("regex_filter")] = Field(
        default=None, description="Regular expression match"
    )
    only: Annotated[Only | None, Dest("only")] = Field(
        default=None, description="Which tests to run"
    )
    on_options: Annotated[list[str], Dest("on_options")] = Field(
        default_factory=list, description="Generation options"
    )
    workers: Annotated[int | None, Dest("workers")] = Field(
        default=None, description="Number of parallel workers"
    )
    timeout: Annotated[str | None, Dest("timeout")] = Field(
        default=None, description="Timeout spec"
    )
    fail_fast: Annotated[bool, Dest("fail_fast")] = Field(
        default=False, description="Stop after first failure"
    )
    view: Annotated[str | None, Dest("view")] = Field(default=None, description="View spec")
    batch_spec: Annotated[str | None, Dest("hpc_batchspec")] = Field(
        default=None, description="Batch spec like 'cpus=16,time=3600'"
    )
    batch_workers: Annotated[int | None, Dest("hpc_batch_workers")] = Field(
        default=None, description="Workers per batch"
    )
    submit_args: Annotated[list[str], Dest("hpc_submit_args")] = Field(
        default_factory=list, description="Raw scheduler submit arguments"
    )
    allow_hyperthreading: Annotated[bool, Dest("hpc_allow_hyperthreading")] = Field(
        default=False, description="Count hyperthreads as CPUs"
    )
    batch_exact_estimate: Annotated[bool, Dest("hpc_batch_exact_estimate")] = Field(
        default=False, description="Run exact scheduling simulation"
    )


def hpc_run(request: HPCRunRequest, ctx: Context) -> dict[str, Any]:
    """Run tests through an HPC scheduler, as ``canary hpc run`` does: ``{"exit_code": N}``."""
    options = options_for(request, "hpc", "run")
    check_run_paths(options, ctx)
    return {"exit_code": exit_code(lambda: app.run(options))}
