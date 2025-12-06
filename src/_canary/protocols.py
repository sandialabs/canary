# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Protocol

if TYPE_CHECKING:
    from .timekeeper import Timekeeper


class StatusProtocol(Protocol):
    name: str
    color: str

    def set(
        self,
        status: "str | int | StatusProtocol",
        reason: str | None = None,
        code: int | None = None,
    ) -> None: ...


class JobProtocol(Protocol):
    cpus: int
    cpu_ids: list[int]
    dependencies: list["JobProtocol"]
    exclusive: bool
    gpus: int
    gpu_ids: list[int]
    id: str
    mask: str
    measurements: "Measurements"
    status: StatusProtocol
    runtime: float
    timeout: float
    timekeeper: "Timekeeper"

    def __str__(self) -> str: ...

    def __iter__(self): ...

    def display_name(self, **kwargs: Any) -> str: ...

    def set_status(
        self,
        status: str | int | StatusProtocol,
        reason: str | None = None,
        code: int | None = None,
    ) -> None: ...

    def refresh(sehf) -> None: ...

    def on_result(self, result: dict[str, Any]) -> None: ...

    def save(self) -> None: ...

    def size(self) -> float: ...

    def finish(self) -> None: ...

    def required_resources(self) -> list[dict[str, Any]]:
        """Returns a list of resource

        required[i] == [{"type": type, "slots": slots}, ...]

        one entry per resource.  For a test requiring 1 slot from 2 cpus:

        required[i] = [{"type": "cpus", "slots": 1}, {"type": "cpus": "slots": 1}]

        This general way of describing resources allows for oversubscribing resources.  Each test
        requires 1 slot per required cpu, but the machine config can specify multiple slots per cpu
        available

        """
        pass

    @property
    def resources(self) -> list[dict[str, list[dict]]]:
        """resources is of the form

        resources[i] = {str: [{"id": str, "slots": int}]}

        If the test required 2 cpus and 2 gpus, resources would look like

        resources = [
          {"cpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}]},
          {"gpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}]},
        ]

        """
        ...

    def assign_resources(self, arg: dict[str, list[dict]]) -> None: ...

    def free_resources(self) -> dict[str, list[dict]]: ...

    def cost(self) -> float: ...


@dataclasses.dataclass
class Measurements:
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def add_measurement(self, name: str, value: Any) -> None:
        self.data[name] = value

    def update(self, measurements: dict) -> None:
        self.data.update(measurements)

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def items(self) -> Generator[tuple[str, Any], None, None]:
        for item in self.data.items():
            yield item
