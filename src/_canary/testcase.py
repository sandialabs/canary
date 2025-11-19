# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import dataclasses
import datetime
import io
import math
import multiprocessing
import os
import signal
import traceback
from functools import cached_property
from pathlib import Path
from shutil import copyfile
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import MutableMapping

from . import config
from .error import TestDiffed
from .error import TestFailed
from .error import TestSkipped
from .error import TestTimedOut
from .error import diff_exit_status
from .error import fail_exit_status
from .status import Status
from .testexec import ExecutionPolicy
from .testexec import ExecutionSpace
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .util.compression import compress_str
from .util.executable import Executable
from .util.time import hhmmss
from .when import match_any

if TYPE_CHECKING:
    from .testspec import TestSpec

logger = logging.get_logger(__name__)


class TestCase:
    def __init__(
        self,
        spec: "TestSpec",
        workspace: ExecutionSpace,
        dependencies: list["TestCase"] | None = None,
    ) -> None:
        self.spec = spec
        self.workspace = workspace
        self.stdout: str = "canary-out.txt"
        self.stderr: str | None = "canary-err.txt"
        hk = config.pluginmanager.hook
        self.execution_policy: ExecutionPolicy = hk.canary_testcase_execution_policy(case=self)
        hk.canary_testcase_modify(case=self)
        self._status = Status()
        self.measurements = Measurements()
        self.timekeeper = Timekeeper()
        self.dependencies = dependencies or []
        if len(self.spec.dependencies) != len(self.dependencies):
            raise ValueError("Incorrect number of dependencies")

        # Resources assigned to this test during execution
        self._resources: dict[str, list[dict]] = {}
        self.variables: dict[str, str | None] = self.get_environ_from_spec()

        # Transfer some attributes from spec to me
        self.id = self.spec.id
        self.exclusive = self.spec.exclusive
        self.mask = self.spec.mask
        self.name = self.spec.name
        self.family = self.spec.family
        self.timeout = self.spec.timeout
        self.fullname = self.spec.fullname
        self.attributes = self.instance_attributes = self.spec.attributes
        self.file_path = self.spec.file_path
        self.file_root = self.spec.file_root
        self.file = self.spec.file

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise TypeError(f"Cannot compare TestCase with type {other.__class__.__name__}")
        return self.id == other.id

    def __str__(self) -> str:
        return self.spec.display_name

    def __repr__(self) -> str:
        return self.spec.display_name

    def display_name(self, **kwargs) -> str:
        name = self.spec.display_name
        if kwargs.get("status"):
            name += " @*%s{%s}" % (self.status.color[0], self.status.name)
        return name

    def set_status(
        self,
        status: str | int | Status,
        message: str | None = None,
        code: int | None = None,
    ) -> None:
        self.status.set(status, message=message, code=code)

    def describe(self) -> str:
        """Write a string describing the test case"""
        name = str(self.workspace.path.parent / self.spec.display_name)
        text = "%s @*b{%s} %s" % (self.status.cname, self.id[:7], name)
        if self.timekeeper.duration >= 0:
            text += " (%s)" % hhmmss(self.timekeeper.duration)
        if self.status.message:
            text += ": %s" % self.status.message
        return text

    def add_variables(self, **kwds: str) -> None:
        self.variables.update(kwds)

    @property
    def statline(self) -> str:
        color = self.status.color[0]
        glyph = self.status.glyph
        status_name = self.status.name
        name = str(self.workspace.path.parent / self.spec.display_name)
        return "@*%s{%s %s} %s\n" % (color, glyph, status_name, name)

    def set_attribute(self, **kwds: Any) -> None:
        self.spec.attributes.update(kwds)

    def get_attribute(self, name: str, default: None = None, /) -> None | Any:
        return self.spec.attributes.get(name, default)

    @property
    def cpus(self) -> int:
        return self.spec.rparameters["cpus"]

    @property
    def gpus(self) -> int:
        return self.spec.rparameters["gpus"]

    @property
    def cpu_ids(self) -> list[str]:
        return [str(_["id"]) for _ in self.resources.get("cpus", [])]

    @property
    def gpu_ids(self) -> list[str]:
        return [str(_["id"]) for _ in self.resources.get("gpus", [])]

    def cost(self) -> float:
        return math.sqrt(self.cpus**2 + self.runtime**2)

    @cached_property
    def runtime(self) -> float:
        try:
            try:
                if cache := self.load_cached_runs():
                    return float(cache["metrics"]["time"]["mean"])
            except KeyError:
                pass
        except Exception:
            logger.debug("Failed to load historic timing data", exc_info=True)
        return self.spec.timeout

    def size(self) -> float:
        vec: list[float | int] = [self.timeout]
        for value in self.spec.rparameters.values():
            vec.append(value)
        return math.sqrt(sum(_**2 for _ in vec))

    @property
    def resources(self) -> dict[str, list[dict]]:
        """resources is of the form

        resources[type] = [{"id": str, "slots": int}]

        If the test required 2 cpus and 2 gpus, resources would look like

        resources = {
            "cpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
            "gpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
        }

        """
        return self._resources

    def assign_resources(self, arg: dict[str, list[dict]]) -> None:
        self._resources.clear()
        self._resources.update(arg)

        # Set resource-type variables
        vars: dict[str, str] = {}
        for type, instances in arg.items():
            varname = type[:-1] if type[-1] == "s" else type
            ids: list[str] = [str(_["id"]) for _ in instances]
            vars[f"{varname}_ids"] = self.variables[f"CANARY_{varname.upper()}_IDS"] = ",".join(ids)

        # Look for variables to expand
        for key, value in self.variables.items():
            try:
                self.variables[key] = value % vars
            except Exception:  # nosec B110
                pass

    def free_resources(self) -> dict[str, list[dict]]:
        tmp = copy.deepcopy(self._resources)
        self._resources.clear()
        return tmp

    def required_resources(self) -> list[dict[str, Any]]:
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
        return self.workspace.joinpath("testcase.lock")

    def create_workspace(self) -> None:
        self.workspace.create(exist_ok=True)
        with self.workspace.openfile(self.stdout, "w") as file:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            file.write(f"[{stamp}] Creating workspace root at {self.workspace}\n")
        if self.stderr is not None:
            self.workspace.unlink(self.stderr, missing_ok=True)
            self.workspace.touch(self.stderr)

    def restore_workspace(self) -> None:
        self.workspace.remove(missing_ok=True)
        self.create_workspace()

    def setup(self) -> None:
        self.workspace.remove(missing_ok=True)
        self.create_workspace()
        copy_all_resources: bool = config.getoption("copy_all_resources", False)
        prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
        try:
            file = open(self.workspace.joinpath(self.stdout), "a")
            file.write(f"[{prefix}] Preparing test: {self.name}\n")
            file.write(f"[{prefix}] Directory: {self.workspace.dir}\n")
            file.write(f"[{prefix}] Linking and copying working files...\n")
            if copy_all_resources:
                file.write(f"[{prefix}] Copying {self.spec.file} to {self.workspace}\n")
                self.workspace.copy(self.spec.file)
            else:
                file.write(f"[{prefix}] Linking {self.spec.file} to {self.workspace}\n")
                self.workspace.link(self.spec.file)
            for asset in self.spec.assets:
                if asset.action not in ("copy", "link"):
                    continue
                if not asset.src.exists():
                    raise MissingSourceError(asset.src)
                if asset.action == "copy" or copy_all_resources:
                    file.write(f"[{prefix}] Copying {asset.src} to {self.workspace}\n")
                    self.workspace.copy(asset.src, asset.dst)
                else:
                    file.write(f"[{prefix}] Linking {asset.src} to {self.workspace}\n")
                    self.workspace.link(asset.src, asset.dst)
        finally:
            file.close()

    def run(self, queue: multiprocessing.Queue) -> None:
        code: int
        try:
            if self.status == "READY":
                with self.workspace.openfile(self.stdout, "a") as fh:
                    prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
                    fh.write(f"[{prefix}] Begin executing {self.spec.fullname}\n")
                xstatus = self.spec.xstatus
                with self.workspace.enter(), self.timekeeper.timeit():
                    self.status.set("RUNNING")
                    self.save()
                    code = self.execution_policy.execute(case=self)
                    self.update_status_from_exit_code(code=code)
        except KeyboardInterrupt:
            self.status.set("CANCELLED", message="Keyboard interrupt", code=signal.SIGINT.value)
        except SystemExit as e:
            self.update_status_from_exit_code(code=e.code or 0)
        except TestDiffed as e:
            stat = "XDIFF" if xstatus == diff_exit_status else "DIFFED"
            self.status.set(stat, message=None if not e.args else e.args[0])
        except TestFailed as e:
            stat = "XFAIL" if (xstatus == fail_exit_status or xstatus < 0) else "FAILED"
            self.status.set(stat, message=None if not e.args else e.args[0])
        except TestSkipped as e:
            self.status.set("SKIPPED", message=None if not e.args else e.args[0])
        except TestTimedOut as e:
            self.status.set("TIMEOUT", message=None if not e.args else e.args[0])
        except BaseException as e:
            if config.get("debug"):
                logger.exception("Exception during test case execution")
            fh = io.StringIO()
            traceback.print_exc(file=fh, limit=2)
            message = fh.getvalue()
            f = self.stderr or self.stdout
            with self.workspace.openfile(f, "a") as fp:
                fp.write(message)
            self.status.set("ERROR", message=message)
        finally:
            logger.debug(f"Finished executing {self.spec.fullname}: status={self.status}")
            queue.put({"status": self.status, "timekeeper": self.timekeeper})
            self.save()
        return

    def on_result(self, data: Any) -> None:
        """The companion of queue.put, save results from the test ran in a child process in the
        parent process"""
        if status := data.get("status"):
            self.status.set(status.name, status.message, status.code)
        if timekeeper := data.get("timekeeper"):
            self.timekeeper.started_on = timekeeper.started_on
            self.timekeeper.finished_on = timekeeper.finished_on
            self.timekeeper.duration = timekeeper.duration

    def do_baseline(self) -> None:
        if not self.spec.baseline:
            return
        logger.info(f"Rebaselining {self.spec.pretty_name}")
        with self.workspace.enter():
            for arg in self.spec.baseline:
                if arg["type"] == "exe":
                    exe = Executable(arg["exe"])
                    exe(*arg["args"], fail_on_error=False)
                else:
                    src = self.workspace.dir / arg["src"]
                    dst = self.spec.file.parent / arg["dst"]
                    if src.exists():
                        logger.debug(f"    Replacing {dst} with {src}\n")
                        copyfile(src, dst)

    def update_status_from_exit_code(self, *, code: int) -> None:
        xcode = self.spec.xstatus

        if xcode == diff_exit_status:
            if code != diff_exit_status:
                self.status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected test to diff",
                    code=code,
                )
            else:
                self.status.set("XDIFF")
        elif xcode != 0:
            # Expected to fail
            if xcode > 0 and code != code:
                self.status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected to exit with code={code}",
                    code=code,
                )
            elif code == 0:
                self.status.set(
                    "FAILED",
                    f"{self.spec.display_name}: expected to exit with code != 0",
                    code=code,
                )
            else:
                self.status.set("XFAIL", code=code)
        elif code == 0:
            self.status.set("SUCCESS")
        else:
            self.status.set(code)

    def refresh(self) -> None:
        try:
            data = json.loads(self.workspace.joinpath("testcase.lock").read_text())
        except FileNotFoundError:
            return
        status = data["status"]
        self.status.set(status["name"], status["message"], status["code"])
        tk = data["timekeeper"]
        self.timekeeper.started_on = tk["started_on"]
        self.timekeeper.finished_on = tk["finished_on"]
        self.timekeeper.duration = tk["duration"]

    def update_env(self, env: MutableMapping[str, str]) -> None:
        for key, val in self.variables.items():
            if val is None:
                env.pop(key, None)
            else:
                env[key] = val

    def get_environ_from_spec(self) -> dict[str, str | None]:
        # Environment variables needed by this test
        variables: dict[str, str | None] = {}
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
        variables["PYTHONPATH"] = f"{self.workspace.dir}:{os.getenv('PYTHONPATH', '')}"
        variables["PATH"] = f"{self.workspace.dir}:{os.environ['PATH']}"
        return variables

    def teardown(self) -> None:
        pass

    def finish(self) -> None:
        try:
            self.cache_last_run()
        except Exception:
            logger.debug("Failed to cache last run", exc_info=True)

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
            "variables": self.variables,
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
                        f"not {self.spec.dep_done_criteria[i]}",
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
        file = self.workspace.joinpath(self.stdout)
        if not file.exists():
            return "Log not found"
        out = io.StringIO()
        out.write(file.read_text(errors="ignore"))
        if self.stderr:
            file = self.workspace.joinpath(self.stderr)
            if file.exists():
                out.write("\nCaptured stderr:\n")
                out.write(file.read_text(errors="ignore"))
        text = out.getvalue()
        if compress:
            kb_to_keep = 2 if self.status.name == "SUCCESS" else 300
            text = compress_str(text, kb_to_keep=kb_to_keep)
        return text

    def load_cached_runs(self) -> dict[str, Any] | None:
        cache_dir = Path(config.cache_dir)
        file = cache_dir / "cases" / self.spec.id[:2] / f"{self.spec.id[2:]}.json"
        if file.exists():
            return json.loads(file.read_text())["cache"]

    def cache_last_run(self) -> None:
        """store relevant information for this run"""
        if self.status.name in ("CANCELLED", "READY", "PENDING"):
            return
        cache_dir = Path(config.cache_dir)
        file = cache_dir / "cases" / self.spec.id[:2] / f"{self.spec.id[2:]}.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        cache: dict[str, Any]
        if not file.exists():
            cache = {
                ".version": [3, 0],
                "meta": {
                    "name": self.spec.display_name,
                    "id": self.spec.id,
                    "root": self.spec.file_root,
                    "path": self.spec.file_path,
                    "parameters": self.spec.parameters,
                },
            }
        else:
            cache = json.loads(file.read_text())["cache"]
        history = cache.setdefault("history", {})
        dt = datetime.datetime.fromisoformat(self.timekeeper.started_on)
        history["last_run"] = dt.strftime("%c")
        name = "pass" if self.status.name == "SUCCESS" else self.status.name.lower()
        history[name] = history.get(name, 0) + 1
        if self.timekeeper.duration >= 0 and self.status.name in (
            "SUCCESS",
            "XFAIL",
            "XDIFF",
            "DIFF",
        ):
            count: int = 0
            metrics = cache.setdefault("metrics", {})
            t = metrics.setdefault("time", {})
            if t:
                # Welford's single pass online algorithm to update statistics
                count, mean, variance = t["count"], t["mean"], t["variance"]
                delta = self.timekeeper.duration - mean
                mean += delta / (count + 1)
                M2 = variance * count
                delta2 = self.timekeeper.duration - mean
                M2 += delta * delta2
                variance = M2 / (count + 1)
                minimum = min(t["min"], self.timekeeper.duration)
                maximum = max(t["max"], self.timekeeper.duration)
            else:
                variance = 0.0
                mean = minimum = maximum = self.timekeeper.duration
            t["mean"] = mean
            t["min"] = minimum
            t["max"] = maximum
            t["variance"] = variance
            t["count"] = count + 1
        file.write_text(json.dumps({"cache": cache}, indent=2))


def load_testcase_from_file(arg: Path | str | None) -> TestCase:
    from _canary.workspace import Workspace

    path = Path(arg or ".").absolute()
    file = path / "testcase.lock" if path.is_dir() else path
    lock_data = json.loads(file.read_text())
    id = lock_data["spec"]["id"]
    workspace = Workspace.load()
    return workspace.locate(case=id)


def load_testcase_from_state(lock_data: dict) -> TestCase:
    from _canary.workspace import Workspace

    workspace = Workspace.load()
    return workspace.locate(case=lock_data["spec"]["id"])


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


class MissingSourceError(Exception):
    pass
