# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/learn/* endpoints: the installed capability and skill data (read-only)."""

from typing import Any
from typing import Callable

from _canary.app import learn

from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import RequestError
from .models import LearnRequest


def _lookup(find: Callable[..., Any], request: LearnRequest, route: str) -> Any:
    try:
        return find(request.topic, list_keys=request.list_keys)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        hint = f'POST {route} with {{"topic": ".", "list_keys": true}} lists the topics'
        raise RequestError(404, f"no topic {request.topic!r} ({exc}); {hint}") from None


def capabilities(request: LearnRequest, ctx: Context) -> Any:
    """What canary and its plugins can do, as for `canary learn capabilities TOPIC`.

    ``topic`` outside a namespace is under ``core``; ``ext.`` selects the extensions'.
    """
    return _lookup(learn.capabilities, request, "/canary/learn/capabilities")


def skills(request: LearnRequest, ctx: Context) -> Any:
    """The installed agent skills, as for `canary learn skills TOPIC`."""
    return _lookup(learn.skills, request, "/canary/learn/skills")


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/learn/capabilities", capabilities)
    registry.register("/canary/learn/skills", skills)
