# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/schema endpoint."""

from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict

from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import build_registry
from .models import Envelope
from .models import Result


class SchemaRequest(BaseModel):
    """Request for /canary/schema (no fields)."""

    model_config = ConfigDict(extra="forbid")


def schema(request: SchemaRequest, ctx: Context) -> dict[str, Any]:
    """JSON schema of the envelope, the result, and every endpoint's request body."""
    endpoints = ctx.registry if ctx.registry is not None else build_registry()
    return {
        "envelope": Envelope.model_json_schema(),
        "result": Result.model_json_schema(),
        "endpoints": {
            e.path: {"lane": e.lane, "request": e.model.model_json_schema()} for e in endpoints
        },
    }


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/schema", schema)
