# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/status endpoint."""

from _canary.app.queries import JobRecord
from _canary.app.queries import list_jobs

from .dispatch import Context
from .dispatch import EndpointRegistry
from .models import StatusRequest
from .query import resolve_job_id
from .roots import publish


def status(request: StatusRequest, ctx: Context) -> list[JobRecord]:
    """The latest result of every job (or of ``spec_ids``)."""
    ids = None
    if request.spec_ids is not None:
        ids = [resolve_job_id(spec_id, ctx) for spec_id in request.spec_ids]
    return publish(list_jobs(ids=ids, start=ctx.workspace_root), ctx)


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/status", status)
