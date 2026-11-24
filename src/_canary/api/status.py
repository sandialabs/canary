# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/status endpoint."""

from _canary.app.queries import JobRecord
from _canary.app.queries import list_jobs

from .dispatch import Context
from .dispatch import EndpointRegistry
from .models import StatusRequest
from .roots import publish


def status(request: StatusRequest, ctx: Context) -> list[JobRecord]:
    """The latest result of every job (or of ``spec_ids``)."""
    return publish(list_jobs(ids=request.spec_ids, start=ctx.workspace_root), ctx)


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/status", status)
