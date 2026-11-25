# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/help and /canary/schema endpoints, generated from the endpoint registry."""

import inspect
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict

from ..util.returncode import EXIT_CODES
from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import build_registry
from .models import Envelope
from .models import Result


class SchemaRequest(BaseModel):
    """Request for /canary/schema (no fields)."""

    model_config = ConfigDict(extra="forbid")


class HelpRequest(BaseModel):
    """Request for /canary/help (no fields)."""

    model_config = ConfigDict(extra="forbid")


def endpoint_help(request: HelpRequest, ctx: Context) -> dict[str, Any]:
    """Every route: its lane, what it does and its fields (``/canary/schema`` has the schemas)."""
    endpoints = ctx.registry if ctx.registry is not None else build_registry()
    return {
        "usage": (
            "POST a JSON object body to a route (carl POST file:///WS/canary/run -d '{...}'); "
            "reads may use GET (carl GET file:///WS/canary/status).  Work runs one request "
            "at a time, in arrival order; reads answer at once.  "
            "Unknown fields are rejected (400). /canary/schema has each body's JSON schema."
        ),
        "exit_codes": EXIT_CODES,
        "endpoints": {
            e.path: {
                "lane": e.lane,
                "summary": _summary(e.func),
                "fields": {name: _field(f) for name, f in e.model.model_fields.items()},
            }
            for e in endpoints
        },
    }


def _summary(func: Any) -> str:
    """The first paragraph of *func*'s docstring, on one line, without reST markup."""
    paragraph = (inspect.getdoc(func) or "").split("\n\n")[0]
    return " ".join(paragraph.split()).replace("``", "`")


def _field(field: Any) -> str:
    """``TYPE, required -- DESCRIPTION`` or ``TYPE, default VALUE -- DESCRIPTION``."""
    annotation = field.annotation
    kind = annotation.__name__ if isinstance(annotation, type) else str(annotation)
    kind = kind.replace("typing.", "")
    if field.is_required():
        kind += ", required"
    else:
        kind += f", default {field.get_default(call_default_factory=True)!r}"
    return f"{kind} -- {field.description}" if field.description else kind


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
    registry.register("/canary/help", endpoint_help)
    registry.register("/canary/schema", schema)
