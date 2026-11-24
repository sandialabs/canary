# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The canary API: typed, HTTP-style endpoints, a sister of the CLI and the TUI.

Each endpoint is a route (``/canary/run``, ``/canary/status``, ...), a pydantic request
model and a handler that drives ``_canary.app``; :mod:`.dispatch` routes requests to them.
Servers (the file server, :mod:`_canary.service.fs`; HTTP later) receive requests and
hand them to :func:`.dispatch.accept`, knowing nothing of the endpoints themselves.

Endpoints register through the ``canary_addendpoint`` hook, core and plugins alike.
The handler modules are imported only when a registry is built, so ordinary ``canary``
commands never load pydantic.
"""

from ..plugins.hookspec import hookimpl


@hookimpl(specname="canary_addendpoint")
def core_endpoints(registry) -> None:
    from . import query
    from . import schema
    from . import status
    from . import work

    for module in (query, schema, status, work):
        module.register(registry)
