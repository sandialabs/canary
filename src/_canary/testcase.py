# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import dataclasses
import datetime
import io
import math
import os
import traceback
from functools import cached_property
from pathlib import Path
from shutil import copyfile
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import MutableMapping
from typing import cast

from . import config
from .error import TestDiffed
from .error import TestFailed
from .error import TestSkipped
from .error import TestTimedOut
from .launcher import Launcher
from .status import Status
from .testexec import ExecutionSpace
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .util.compression import compress_str
from .util.executable import Executable

if TYPE_CHECKING:
    from .testspec import Mask
    from .testspec import ResolvedSpec

logger = logging.get_logger(__name__)


class TestCase:
    def __init__(
        self,
        spec: "ResolvedSpec",
        workspace: ExecutionSpace,
        dependencies: list["TestCase"] | None = None,
    ) -> None:
        self.spec = spec
        self.workspace = workspace
        self.rparameters = self.get_resource_parameters_from_spec()
        pm = config.pluginmanager.hook
        self.launcher: Launcher = pm.canary_runtest_launcher(case=self)
        self._status = Status()
        self.measurements = Measurements()
        self.timekeeper = Timekeeper()
        self.dependencies = dependencies or []
        if len(self.spec.dependencies) != len(self.dependencies):
            raise ValueError("Incorrect number of dependencies")
        self._mask: Mask | None = None

        # Resources assigned to this test during execution
        self._resources: dict[str, list[dict]] = {}
        self.variables: dict[str, str | None] = self.get_environ_from_spec()

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def exclusive(self) -> bool:
        return self.spec.exclusive

    @property
    def stdout(self) -> str:
        return self.spec.stdout

    @property
    def stderr(self) -> str | None:
        return self.spec.stderr

    @property
    def file(self) -> Path:
        return self.spec.file

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def timeout(self) -> float:
        return self.spec.timeout

    @property
    def attributes(self) -> dict[str, Any]:
        return self.spec.attributes

    @property
    def mask(self) -> "Mask":
        if self._mask is None:
            return self.spec.mask
        return self._mask

    @mask.setter
    def mask(self, arg: "Mask") -> None:
        self._mask = arg

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise TypeError(f"Cannot compare TestCase with type {other.__class__.__name__}")
        return self.id == other.id

    def __str__(self) -> str:
        return self.spec.display_name()

    def __repr__(self) -> str:
        return self.spec.display_name()

    def display_name(self, **kwargs) -> str:
        return self.spec.display_name(**kwargs)

    def add_measurement(self, name: str, value: Any) -> None:
        self.measurements.add_measurement(name, value)

    def set_status(
        self,
        state: str | None = None,
        category: str | None = None,
        status: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(state=state, category=category, status=status, reason=reason, code=code)

    def add_variables(self, **kwds: str) -> None:
        self.variables.update(kwds)

    def statline(self, style: str = "none") -> str:
        status_name = self.status.display_name(style=style)
        name = self.display_name(style=style, resolve=True)
        return f"{status_name} {name}"

    def set_attribute(self, name: str, value: Any) -> None:
        self.spec.set_attribute(name, value)

    def set_attributes(self, **kwds: Any) -> None:
        self.spec.set_attributes(**kwds)

    def get_attribute(self, name: str, default: None = None, /) -> None | Any:
        return self.spec.attributes.get(name, default)

    @property
    def cpus(self) -> int:
        return self.rparameters["cpus"]

    @property
    def gpus(self) -> int:
        return self.rparameters["gpus"]

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
        return self.timeout

    def size(self) -> float:
        vec: list[float | int] = [self.timeout]
        for value in self.rparameters.values():
            vec.append(value)
        return math.sqrt(sum(_**2 for _ in vec))

    @property
    def resources(self) -> dict[str, list[dict]]:
        """resources is of the form::

          resources[type] = [{"id": str, "slots": int}]

        If the test required 2 cpus and 2 gpus, resources would look like::

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
            if value is None:
                continue
            try:
                self.variables[key] = value % vars
            except Exception:  # nosec B110
                pass

    def free_resources(self) -> dict[str, list[dict]]:
        tmp = copy.deepcopy(self._resources)
        self._resources.clear()
        return tmp

    def required_resources(self) -> list[dict[str, Any]]:
        reqd: list[dict[str, Any]] = []
        for name, value in self.rparameters.items():
            if name == "nodes":
                continue
            reqd.extend([{"type": name, "slots": 1} for _ in range(value)])
        return reqd

    @property
    def status(self) -> Status:
        if self._status.state == "PENDING":
            if not self.dependencies:
                self._status = Status.READY()
            else:
                self.set_dependency_based_status()
        return self._status

    @status.setter
    def status(self, arg: Status) -> None:
        self._status = arg

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

    def run(self) -> None:
        code: int
        xstatus = self.spec.xstatus
        try:
            if self.status == "READY":
                with self.workspace.openfile(self.stdout, "a") as fh:
                    prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
                    fh.write(f"[{prefix}] Begin executing {self.spec.fullname}\n")
                with self.workspace.enter(), self.timekeeper.timeit():
                    self.status = Status.RUNNING()
                    self.save()
                    code = self.launcher.run(case=self)
                    self.update_status_from_exit_code(code=code)
        except KeyboardInterrupt:
            self.status = Status.INTERRUPTED()
        except SystemExit as e:
            self.update_status_from_exit_code(code=e.code or 0)
        except TestDiffed as e:
            stat = "XDIFF" if xstatus == Status.code_for_status["DIFFED"] else "DIFFED"
            default_reason: str | None = None
            if stat == "DIFFED":
                default_reason = "Empty TestDiffed exception raised during execution"
            self.status.set(status=stat, reason=default_reason if not e.args else e.args[0])
        except TestFailed as e:
            f_status = Status.code_for_status["FAILED"]
            stat = "XFAIL" if (xstatus == f_status or xstatus < 0) else "FAILED"
            default_reason: str | None = None
            if stat == "FAILED":
                default_reason = "Empty TestFailed exception raised during execution"
            self.status.set(status=stat, reason=None if not e.args else e.args[0])
        except TestSkipped as e:
            self.status.set(status="SKIPPED", reason=None if not e.args else e.args[0])
        except TestTimedOut as e:
            self.status.set(status="TIMEOUT", reason=None if not e.args else e.args[0])
        except BaseException as e:
            if config.get("debug"):
                logger.exception("Exception during test case execution")
            fh = io.StringIO()
            traceback.print_exc(file=fh, limit=2)
            reason = fh.getvalue()
            f = self.stderr or self.stdout
            with self.workspace.openfile(f, "a") as fp:
                fp.write(reason)
            self.status.set(status="ERROR", reason=reason)
        finally:
            logger.debug(f"Finished executing {self.spec.fullname}: status={self.status}")
            self.save()
        return

    def getstate(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timekeeper": self.timekeeper,
            "measurements": self.measurements,
        }

    def setstate(self, data: dict[str, Any]) -> None:
        """The companion of getstate, save results from the test ran in a child process in the
        parent process"""
        if status := data.get("status"):
            self.status.set(
                state=status.state,
                category=status.category,
                status=status.status,
                reason=status.reason,
                code=status.code,
            )
        if timekeeper := data.get("timekeeper"):
            self.timekeeper.submitted_on = timekeeper.submitted_on
            self.timekeeper.started_on = timekeeper.started_on
            self.timekeeper.finished_on = timekeeper.finished_on
            self.timekeeper.duration = timekeeper.duration
        if measurements := data.get("measurements"):
            self.measurements.update(measurements.data)

    def do_baseline(self) -> None:
        if not self.spec.baseline:
            return
        logger.info(f"Rebaselining {self.spec.display_name()}")
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

    def update_status_from_exit_code(self, *, code: int | str) -> None:
        if isinstance(code, str):
            code = 1
        xcode = self.spec.xstatus

        if xcode == Status.code_for_status["DIFFED"]:
            if code != Status.code_for_status["DIFFED"]:
                self.status = Status.FAILED(
                    reason=f"{self.spec.display_name()}: expected test to diff",
                    code=code,
                )
            else:
                self.status = Status.XDIFF()
        elif xcode != 0:
            # Expected to fail
            if xcode > 0 and code != code:
                self.status = Status.FAILED(
                    f"{self.spec.display_name()}: expected to exit with code={code}",
                    code=code,
                )
            elif code == 0:
                self.status = Status.FAILED(
                    f"{self.spec.display_name()}: expected to exit with code != 0",
                    code=code,
                )
            else:
                self.status = Status.XFAIL()
        elif code == 0:
            self.status = Status.SUCCESS()
        elif code == Status.code_for_status["DIFFED"]:
            self.status = Status.DIFFED(reason=f"Test exited with diff exit code = {code}")
        elif code == Status.code_for_status["SKIPPED"]:
            self.status = Status.SKIPPED(reason=f"Test exited with skip exit code = {code}")
        else:
            self.status = Status.FAILED(code=code, reason=f"Test exited with exit code = {code}")

    def refresh(self) -> None:
        try:
            data = json.loads(self.workspace.joinpath("testcase.lock").read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return
        status = data["status"]
        self.status = Status(
            state=status["state"],
            category=status["category"],
            status=status["status"],
            reason=status["reason"],
            code=status["code"],
        )
        tk = data["timekeeper"]
        self.timekeeper.submitted_on = tk["submitted_on"]
        self.timekeeper.started_on = tk["started_on"]
        self.timekeeper.finished_on = tk["finished_on"]
        self.timekeeper.duration = tk["duration"]

    def set_runtime_env(self, env: MutableMapping[str, str]) -> None:
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

    def get_resource_parameters_from_spec(self) -> dict[str, int]:
        """Default parameters used to set up resources required by test case"""
        rparameters: dict[str, int] = {}
        rparameters.update({"cpus": 1, "gpus": 0, "nodes": 1})
        resource_types: set[str] = set(config.pluginmanager.hook.canary_resource_pool_types())
        parameters = self.spec.parameters | self.spec.meta_parameters
        assert "cpus" in parameters, "Expected cpus to be in spec.parameters or meta_parameters"
        assert "gpus" in parameters, "Expected cpus to be in spec.parameters or meta_parameters"
        for key, value in parameters.items():
            if key in resource_types and not isinstance(value, int):
                raise InvalidTypeError(key, value)
        rpcount = config.pluginmanager.hook.canary_resource_pool_count
        if "nodes" in parameters:
            nodes = cast(int, parameters["nodes"])
            rparameters["nodes"] = int(nodes)
            rparameters["cpus"] = max(nodes * rpcount(type="cpu"), parameters["cpus"])
            rparameters["gpus"] = max(nodes * rpcount(type="gpu"), parameters["gpus"])
        if "cpus" in parameters:
            cpus = cast(int, parameters["cpus"])
            rparameters["cpus"] = max(int(cpus), rparameters["cpus"])
            if "nodes" not in parameters:
                cpu_count = rpcount(type="cpu")
                node_count = rpcount(type="node")
                cpus_per_node = math.ceil(cpu_count / node_count)
                if cpus_per_node > 0:
                    nodes = max(rparameters["nodes"], math.ceil(cpus / cpus_per_node))
                    rparameters["nodes"] = max(nodes, rparameters["nodes"])
        if "gpus" in parameters:
            gpus = cast(int, parameters["gpus"])
            rparameters["gpus"] = max(int(gpus), rparameters["gpus"])
            if "nodes" not in parameters:
                gpu_count = rpcount(type="gpu")
                node_count = rpcount(type="node")
                gpus_per_node = math.ceil(gpu_count / node_count)
                if gpus_per_node > 0:
                    nodes = max(rparameters["nodes"], math.ceil(gpus / gpus_per_node))
                    rparameters["nodes"] = max(nodes, rparameters["nodes"])
        # We have already done validation, now just fill in missing resource types
        resource_types -= {"nodes", "cpus", "gpus"}
        for key, value in parameters.items():
            if key in resource_types:
                rparameters[key] = int(value)
        return rparameters

    def teardown(self) -> None:
        pass

    def finish(self) -> None:
        try:
            self.cache_last_run()
        except Exception:
            logger.debug("Failed to cache last run", exc_info=True)

    def save(self) -> None:
        record = self.asdict()
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        self.lockfile.write_text(json.dumps(record, indent=2))

    def asdict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "status": self.status.asdict(),
            "spec": self.spec.asdict(),
            "timekeeper": self.timekeeper.asdict(),
            "measurements": self.measurements.asdict(),
            "workspace": self.workspace.asdict(),
            "variables": self.variables,
            "resources": self.resources,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "runtime": self.runtime,
            "dependencies": [dep.lockfile for dep in self.dependencies],
            "rparameters": self.rparameters,
        }
        record["spec"]["name"] = self.spec.name

        return record

    def serialize(self) -> str:
        record: dict[str, Any] = {
            "id": self.spec.id,
            "status": self.status.asdict(),
            "timekeeper": self.timekeeper.asdict(),
            "measurements": self.measurements.asdict(),
            "variables": self.variables,
            "resources": self.resources,
            "dependencies": [dep.id for dep in self.dependencies],
            "rparameters": self.rparameters,
        }
        return json.dumps_min(record)

    def set_dependency_based_status(self) -> None:
        # Determine if dependent cases have completed and, if so, flip status to 'ready'
        flags = self.dep_condition_flags()
        if all(flag == "can_run" for flag in flags):
            self.status = Status.READY()
            return
        for i, flag in enumerate(flags):
            if flag == "wont_run":
                # this case will never be able to run
                dep = self.dependencies[i]
                self.status = Status.BLOCKED(
                    f"Dependency {dep.name} finished with status {dep.status.status!r}, "
                    f"not {self.spec.dep_done_criteria[i]}",
                )
                break

    def dep_condition_flags(self) -> list[str]:
        # Determine if dependent cases have completed and, if so, flip status to 'can_run'
        expected = self.spec.dep_done_criteria
        flags: list[str] = ["none"] * len(self.dependencies)
        for i, dep in enumerate(self.dependencies):
            if dep.status.state in ("READY", "PENDING", "RUNNING"):
                # Still pending on this case
                flags[i] = "pending"
            elif expected[i].upper() in (None, dep.status.category, dep.status.status, "*"):
                flags[i] = "can_run"
            else:
                flags[i] = "wont_run"
        return flags

    def read_output(self, compress: bool = False) -> str:
        if self.status.category == "SKIP":
            return f"Test skipped.  Reason: {self.status.reason}"
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
            kb_to_keep = 2 if self.status.category == "PASS" else 300
            text = compress_str(text, kb_to_keep=kb_to_keep)
        return text

    def load_cached_runs(self) -> dict[str, Any] | None:
        if cache_dir := find_cache_dir(start=self.workspace.root):
            file = cache_dir / "cases" / self.spec.id[:2] / f"{self.spec.id[2:]}.json"
            if file.exists():
                return json.loads(file.read_text())["cache"]
        return None

    def cache_last_run(self) -> None:
        """store relevant information for this run"""
        if self.status.category != "PASS":
            return
        if cache_dir := find_cache_dir(start=self.workspace.root):
            file = cache_dir / "cases" / self.spec.id[:2] / f"{self.spec.id[2:]}.json"
            file.parent.mkdir(parents=True, exist_ok=True)
            cache: dict[str, Any]
            if not file.exists():
                cache = {
                    ".version": [3, 0],
                    "meta": {
                        "name": self.spec.display_name(),
                        "id": self.spec.id,
                        "root": self.spec.file_root,
                        "path": self.spec.file_path,
                        "parameters": self.spec.parameters,
                    },
                }
            else:
                cache = json.loads(file.read_text())["cache"]
            history = cache.setdefault("history", {})
            dt = (
                datetime.datetime.fromisoformat(self.timekeeper.started_on)
                if self.timekeeper.started_on != "NA"
                else None
            )
            if dt is not None:
                history["last_run"] = dt.strftime("%c")
            name = self.status.category.lower()
            history[name] = history.get(name, 0) + 1
            if self.timekeeper.duration >= 0 and self.status.category == "PASS":
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
    return workspace.find(case=id)


def load_testcase_from_state(lock_data: dict) -> TestCase:
    from _canary.workspace import Workspace

    workspace = Workspace.load()
    return workspace.find(case=lock_data["spec"]["id"])


@dataclasses.dataclass
class Measurements:
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def add_measurement(self, name: str, value: Any) -> None:
        self.data[name] = value

    def update(self, measurements: dict) -> None:
        self.data.update(measurements)

    def reset(self) -> None:
        self.data.clear()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Measurements":
        return cls(data=data)

    def asdict(self) -> dict[str, Any]:
        return self.data

    def items(self) -> Generator[tuple[str, Any], None, None]:
        for item in self.data.items():
            yield item


def find_cache_dir(start: Path) -> Path | None:
    if "CANARY_CACHE_DIR" in os.environ:
        return Path(os.environ["CANARY_CACHE_DIR"])
    d = start
    while d != d.parent:
        if (d / "WORKSPACE.TAG").exists():
            return d / "cache"
        d = d.parent
    return None


class MissingSourceError(Exception):
    pass


class InvalidTypeError(Exception):
    def __init__(self, name, value):
        class_name = value.__class__.__name__
        super().__init__(f"expected type({name})=type({value!r})=int, not {class_name}")
