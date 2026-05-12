# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
from abc import ABC
from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from .status import Status
    from .timekeeper import Timekeeper


class JobPhase(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    DONE = "DONE"


@dataclasses.dataclass(slots=True)
class JobState:
    phase: JobPhase = JobPhase.PENDING

    def is_pending(self) -> bool:
        return self.phase is JobPhase.PENDING

    def is_submitted(self) -> bool:
        return self.phase is JobPhase.SUBMITTED

    def is_running(self) -> bool:
        return self.phase is JobPhase.RUNNING

    def is_done(self) -> bool:
        return self.phase is JobPhase.DONE


class BaseJob(ABC):
    # ---- required data attributes (enforced by convention) ----
    id: str
    state: JobState
    timekeeper: "Timekeeper"

    # ---- scheduler sizing/resources ----
    @abstractmethod
    def cost(self) -> float: ...

    @property
    def exclusive(self) -> bool:
        return False

    @property
    @abstractmethod
    def status(self) -> "Status": ...

    @abstractmethod
    def required_resources(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def assign_resources(self, arg: dict[str, list[dict]]) -> None: ...

    @abstractmethod
    def free_resources(self) -> dict[str, list[dict]]: ...

    # ---- dependency gating / dispatch readiness ----
    @abstractmethod
    def refresh_readiness(self) -> None:
        """Side-effecting: may mark job DONE + BLOCKED, etc."""

    @abstractmethod
    def is_runnable(self) -> bool:
        """True if it could still run in the future."""

    @abstractmethod
    def is_ready(self) -> bool:
        """True if it can be dispatched now."""

    def validate_enqueuable(self) -> None:
        # Keep the rule centralized; queue shouldn’t know phases.
        if self.state.phase not in (JobPhase.PENDING,):
            raise ValueError(f"not enqueuable: phase={self.state.phase}")

    # ---- lifecycle hooks (called by queue) ----
    def on_submitted(self) -> None:
        self.state.phase = JobPhase.SUBMITTED

    def on_started(self) -> None:
        self.state.phase = JobPhase.RUNNING

    def on_finished(self) -> None:
        self.state.phase = JobPhase.DONE

    # ---- executor integration ----
    @abstractmethod
    def total_timeout(self) -> float: ...

    @abstractmethod
    def refresh(self) -> None: ...

    @abstractmethod
    def save(self) -> None: ...

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)

    # ---- presentation ----
    @abstractmethod
    def display_name(self, **kwargs: Any) -> str: ...
