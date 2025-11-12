# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import io
import multiprocessing
import os
import signal
import traceback
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from . import config
from .error import TestDiffed
from .error import TestFailed
from .error import TestSkipped
from .error import TestTimedOut
from .error import diff_exit_status
from .error import exception_exit_status
from .error import fail_exit_status
from .error import skip_exit_status
from .error import timeout_exit_status
from .status import Status
from .testexec import ExecutionPolicy
from .testexec import ExecutionSpace
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .util.compression import compress_str
from .util.time import hhmmss
from .when import match_any

if TYPE_CHECKING:
    from .testspec import TestSpec

logger = logging.get_logger(__name__)


class TestCase:
    def __init__(
        self, spec: "TestSpec", workspace: ExecutionSpace, dependencies: list["TestCase"]
    ) -> None:
        self.spec = spec
        self.workspace = workspace
        self.workspace.stdout = self.spec.stdout
        self.workspace.stderr = self.spec.stderr
        hk = config.pluginmanager.hook
        self.execution_policy: ExecutionPolicy = hk.canary_testcase_execution_policy(spec=self.spec)
        self._status = Status()
        self.measurements = Measurements()
        self.timekeeper = Timekeeper()
        self.dependencies = dependencies

        # Resources assigned to this test during execution
        self._resources: list[dict[str, list[dict]]] = []

        # Transfer some attributes from spec to me
        self.id = self.spec.id
        self.exclusive = self.spec.exclusive
        self.mask = self.spec.mask
        self.name = self.spec.name
        self.family = self.spec.family
        self.timeout = self.spec.timeout
        self.fullname = self.spec.fullname
        self.display_name = self.spec.display_name
        self.attributes = self.instance_attributes = self.spec.attributes
        self.file_path = self.spec.file_path
        self.file_root = self.spec.file_root
        self.file = self.spec.file

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise TypeError(f"Cannot compare TestCase with type {other.__class__.__name__}")
        return self.id == other.id

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return self.display_name

    def describe(self) -> str:
        """Write a string describing the test case"""
        name = str(self.workspace.path / self.display_name)
        text = "%s @*b{%s} %s" % (self.status.cname, self.id[:7], name)
        if self.timekeeper.duration >= 0:
            text += " (%s)" % hhmmss(self.timekeeper.duration)
        if self.status.message:
            text += ": %s" % self.status.message
        return text

    @property
    def statline(self) -> str:
        color = self.status.color[0]
        glyph = self.status.glyph
        status_name = self.status.name
        name = str(self.workspace.path.parent / self.spec.display_name)
        return "@*%s{%s %s} %s\n" % (color, glyph, status_name, name)

    @property
    def cpus(self) -> int:
        return self.spec.rparameters["cpus"]

    @property
    def gpus(self) -> int:
        return self.spec.rparameters["gpus"]

    @property
    def cpu_ids(self) -> list[str]:
        # self._resources: list[dict[str, list[dict]]] = []
        cpu_ids: list[str] = []
        for group in self.resources:
            for type, instances in group.items():
                if type == "cpus":
                    cpu_ids.extend([str(_["id"]) for _ in instances])
        return cpu_ids

    @property
    def gpu_ids(self) -> list[str]:
        gpu_ids: list[str] = []
        for group in self.resources:
            for type, instances in group.items():
                if type == "gpus":
                    gpu_ids.extend([str(_["id"]) for _ in instances])
        return gpu_ids

    @property
    def runtime(self) -> float:
        return self.spec.timeout  # FIXME

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
        return self._resources

    @resources.setter
    def resources(self, arg: list[dict[str, list[dict]]]) -> None:
        self.assign_resources(arg)

    def set_attribute(self, **kwds: Any) -> None:
        self.spec.attributes.update(kwds)

    def assign_resources(self, arg: list[dict[str, list[dict]]]) -> None:
        self._resources.clear()
        self._resources.extend(arg)

    def free_resources(self) -> list[dict[str, list[dict]]]:
        tmp = self._resources
        self._resources = []
        return tmp

    def required_resources(self) -> list[list[dict[str, Any]]]:
        return self.spec.required_resources()

    @property
    def status(self) -> Status:
        if self._status.name == "PENDING":
            if not self.dependencies:
                self._status = Status.READY()
            else:
                self.set_dependency_based_status()
        return self._status

    @property
    def lockfile(self) -> Path:
        return self.workspace.dir / "testcase.lock"

    def setup(self) -> None:
        with self.workspace.enter():
            copy_all_resources: bool = config.getoption("copy_all_resources", False)
            prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            self.workspace.restore()
            with self.workspace.enter():
                with open(self.workspace.stdout, "a") as file:
                    file.write(f"[{prefix}] Preparing test: {self.name}\n")
                    file.write(f"[{prefix}] Directory: {self.workspace.dir}\n")
                    file.write(f"[{prefix}] Linking and copying working files...\n")
                if copy_all_resources:
                    self.workspace.copy(self.spec.file)
                else:
                    self.workspace.link(self.spec.file)
                for asset in self.spec.assets:
                    if asset.action not in ("copy", "link"):
                        continue
                    if not asset.src.exists():
                        raise MissingSourceError(asset.src)
                    if asset.action == "copy" or copy_all_resources:
                        self.workspace.copy(asset.src, asset.dst)
                    else:
                        self.workspace.link(asset.src, asset.dst)

    def run(self, queue: multiprocessing.Queue) -> None:
        code: int
        message: str | None = None
        try:
            with self.workspace.enter(), self.timekeeper.timeit():
                self.status.set("RUNNING")
                code = self.execution_policy.execute(case=self, queue=queue)
        except KeyboardInterrupt:
            code = signal.SIGINT.value
        except SystemExit as e:
            code = 0 if e.code is None else e.code if isinstance(e.code, int) else 1
        except TestDiffed as e:
            code = diff_exit_status
            message = None if not e.args else e.args[0]
        except TestFailed as e:
            code = fail_exit_status
            message = None if not e.args else e.args[0]
        except TestSkipped as e:
            code = skip_exit_status
            message = None if not e.args else e.args[0]
        except TestTimedOut:
            code = timeout_exit_status
        except BaseException as e:
            if config.get("config:debug"):
                logger.exception("Exception during test case execution")
            with open(self.workspace.dir / self.workspace.stdout, "a") as fh:
                traceback.print_exc(file=fh)
            code = exception_exit_status
            message = f"Caught exception: {e}"
        finally:
            logger.debug(f"Finished executing {self.spec.fullname}: code={code}, message={message}")
            self.update_status(code=code, message=message)
            queue.put({"status": self.status, "timekeeper": self.timekeeper})
            self.save()
        return

    def update_status(self, *, code: int, message: str | None) -> None:
        xcode = self.spec.xstatus
        status = self.status

        if xcode == diff_exit_status:
            if code != diff_exit_status:
                status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected test to diff",
                    code=code,
                )
            else:
                status.set("XDIFF")
        elif xcode != 0:
            # Expected to fail
            if xcode > 0 and code != code:
                status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected to exit with code={code}",
                    code=code,
                )
            elif code == 0:
                status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected to exit with code != 0",
                    code=code,
                )
            else:
                status.set("XFAIL", code=code)
        else:
            status.set(code, message)

    def update(self, **attrs: Any) -> None:
        if status := attrs.get("status"):
            self.status.set(status.name, status.message, status.code)
        if timekeeper := attrs.get("timekeeper"):
            self.timekeeper.started_on = timekeeper.started_on
            self.timekeeper.finished_on = timekeeper.finished_on
            self.timekeeper.duration = timekeeper.duration

    @property
    def environment(self) -> dict[str, str | None]:
        # Environment variables needed by this test
        variables: dict[str, str] = {}
        variables.update(self.spec.environment)
        for mod in self.spec.environment_modifications:
            name, action, value, sep = mod["name"], mod["action"], mod["value"], mod["sep"]
            if action == "set":
                variables[name] = value
            elif action == "unset":
                variables[name] = None
            elif action == "prepend-path":
                variables[name] = f"{value}{sep}{os.getenv(name, '')}"
            elif action == "append-path":
                variables[name] = f"{os.getenv(name, '')}{sep}{value}"

        # Set resource-type variables
        vars = {}
        for group in self.resources:
            for type, instances in group.items():
                varname = type[:-1] if type[-1] == "s" else type
                ids: list[str] = [str(_["id"]) for _ in instances]
                vars[f"{varname}_ids"] = variables[f"CANARY_{varname.upper()}"] = ",".join(ids)
        for key, value in variables.items():
            try:
                variables[key] = value % vars
            except Exception:  # nosec B110
                pass
        variables["PYTHONPATH"] = f"{self.workspace.dir}:{os.getenv('PYTHONPATH', '')}"
        variables["PATH"] = f"{self.workspace.dir}:{os.environ['PATH']}"
        return variables

    def teardown(self) -> None:
        pass

    def finish(self) -> None:
        pass

    def save(self) -> None:
        record = self.asdict()
        self.lockfile.write_text(json.dumps(record, indent=2))

    def asdict(self) -> dict[str, dict]:
        record: dict[str, dict] = {
            "status": self.status.asdict(),
            "spec": self.spec.asdict(),
            "timekeeper": self.timekeeper.asdict(),
            "measurements": self.measurements.asdict(),
            "workspace": self.workspace.asdict(),
        }
        return record

    def set_dependency_based_status(self) -> None:
        # Determine if dependent cases have completed and, if so, flip status to 'ready'
        flags = self.dep_condition_flags()
        if all(flag == "can_run" for flag in flags):
            self._status.set("READY")
            return
        for i, flag in enumerate(flags):
            if flag == "wont_run":
                # this case will never be able to run
                dep = self.dependencies[i]
                if dep.status.name == "SKIPPED":
                    self._status.set("SKIPPED", "one or more dependencies was skipped")
                elif dep.status.name == "CANCELLED":
                    self._status.set("NOT_RUN", "one or more dependencies was cancelled")
                elif dep.status.name == "TIMEOUT":
                    self._status.set("NOT_RUN", "one or more dependencies timed out")
                elif dep.status.name == "FAILED":
                    self._status.set("NOT_RUN", "one or more dependencies failed")
                elif dep.status.name == "DIFFED":
                    self._status.set("SKIPPED", "one or more dependencies diffed")
                elif dep.status.name == "SUCCESS":
                    self._status.set("SKIPPED", "one or more dependencies succeeded")
                else:
                    self._status.set(
                        "NOT_RUN",
                        f"Dependency {dep.name} finished with status {dep.status.name!r}, "
                        f"not {self.spec.dep_done_criteria}",
                    )
                break

    def dep_condition_flags(self) -> list[str]:
        # Determine if dependent cases have completed and, if so, flip status to 'can_run'
        expected = self.spec.dep_done_criteria
        flags: list[str] = ["none"] * len(self.dependencies)
        for i, dep in enumerate(self.dependencies):
            if dep.mask and dep.status.name in ("READY", "PENDING"):
                flags[i] = "wont_run"
            elif dep.status.name in ("READY", "PENDING", "RUNNING"):
                # Still pending on this case
                flags[i] = "pending"
            elif expected[i] in (None, dep.status.name, "*"):
                flags[i] = "can_run"
            elif match_any(expected[i], [dep.status.name, *dep.status.labels], ignore_case=True):
                flags[i] = "can_run"
            else:
                flags[i] = "wont_run"
        return flags

    def read_output(self, compress: bool = False) -> str:
        if self.status.name == "SKIPPED":
            return f"Test skipped.  Reason: {self.status.message}"
        file = self.workspace.dir / self.workspace.stdout
        if not file.exists():
            return "Log not found"
        out = io.StringIO()
        out.write(file.read_text(errors="ignore"))
        if self.workspace.stderr:
            file = self.workspace.dir / self.workspace.stderr
            if file.exists():
                out.write("\nCaptured stderr:\n")
                out.write(file.read_text(errors="ignore"))
        text = out.getvalue()
        if compress:
            kb_to_keep = 2 if self.status.name == "SUCCESS" else 300
            text = compress_str(text, kb_to_keep=kb_to_keep)
        return text


@dataclasses.dataclass
class Measurements:
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def add_measurement(self, name: str, value: Any) -> None:
        self.data[name] = value

    def update(self, measurements: dict) -> None:
        self.data.update(measurements)

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class MissingSourceError(Exception):
    pass
