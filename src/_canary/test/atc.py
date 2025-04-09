# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import abc
from typing import Any
from typing import Generator

from ..status import Status


class AbstractTestCase(abc.ABC):
    """Abstract test case"""

    def __init__(self) -> None:
        self._resources: list[dict[str, list[dict]]] = []

    def __iter__(self) -> Generator["AbstractTestCase", None, None]:
        yield self

    def __len__(self) -> int:
        return 1

    @abc.abstractmethod
    def size(self) -> float:
        pass

    @abc.abstractmethod
    def required_resources(self) -> list[list[dict[str, Any]]]:
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
        return self._resources

    @resources.setter
    def resources(self, arg: list[dict[str, list[dict]]]) -> None:
        self.assign_resources(arg)

    def assign_resources(self, arg: list[dict[str, list[dict]]]) -> None:
        self._resources.clear()
        self._resources.extend(arg)

    def free_resources(self) -> None:
        self._resources.clear()

    @property
    @abc.abstractmethod
    def id(self) -> str: ...

    @property
    @abc.abstractmethod
    def status(self) -> Status: ...

    @status.setter
    @abc.abstractmethod
    def status(self, arg: list[str]) -> None: ...

    @property
    @abc.abstractmethod
    def cpus(self) -> int: ...

    @property
    @abc.abstractmethod
    def gpus(self) -> int: ...

    @property
    @abc.abstractmethod
    def cputime(self) -> float: ...

    @property
    @abc.abstractmethod
    def runtime(self) -> float: ...

    @property
    @abc.abstractmethod
    def path(self) -> str: ...

    @abc.abstractmethod
    def refresh(self) -> None: ...

    @abc.abstractmethod
    def command(self) -> list[str]: ...

    @property
    def cpu_ids(self) -> list[str]:
        # self._resources: list[dict[str, list[dict]]] = []
        cpu_ids: list[str] = []
        for group in self.resources:
            for type, instances in group.items():
                if type == "cpus":
                    cpu_ids.extend([str(_["gid"]) for _ in instances])
        return cpu_ids

    @property
    def exclusive(self) -> bool:
        return False

    @property
    def gpu_ids(self) -> list[str]:
        gpu_ids: list[str] = []
        for group in self.resources:
            for type, instances in group.items():
                if type == "gpus":
                    gpu_ids.extend([str(_["gid"]) for _ in instances])
        return gpu_ids
