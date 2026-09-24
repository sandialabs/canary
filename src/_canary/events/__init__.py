# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary event model and in-process event bus.

Canary's execution layer emits job-lifecycle events as dicts
(``{"event": "job_started", ...}``) that the parent process routes through
:class:`~_canary.execution.queue_executor.ResourceQueueExecutor` and fans out to
registered listeners.  This package provides a typed equivalent:

* :data:`~_canary.events.bus.EventName` -- canonical event-name literals kept in
  lock-step with the strings the executor emits.
* :class:`~_canary.events.bus.Event` -- an immutable "something happened" record.
* :class:`~_canary.events.bus.EventBus` -- a synchronous publish/subscribe hub
  whose delivery semantics match ``ResourceQueueExecutor.notify_listeners``.

The bus does not own any delivery mechanism: the cross-process transport
(mp.Queue/Pipe) and the durable spool (``FSQueue``) remain in the execution
layer.
"""

from .bus import Event
from .bus import EventBus
from .bus import EventName
from .bus import JobEvent
from .bus import Subscriber
from .bus import project_job_event

__all__ = ["Event", "EventBus", "EventName", "JobEvent", "Subscriber", "project_job_event"]
