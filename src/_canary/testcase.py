# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import copy
import datetime
import io
import math
import os
import traceback
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from shutil import copyfile
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal
from typing import MutableMapping

from . import config
from .error import TestDiffed
from .error import TestFailed
from .error import TestSkipped
from .error import TestTimedOut
from .expression import Expression
from .job import BaseJob
from .job import JobPhase
from .launcher import Launcher
from .status import Status
from .testexec import ExecutionSpace
from .util import cpu_count
from .util import json_helper as json
from .util import logging
from .util.compression import compress_str
from .util.executable import Executable

if TYPE_CHECKING:
    from .testspec import Mask
    from .testspec import ResolvedSpec

logger = logging.get_logger(__name__)


@dataclass
class AnyMatcher:
    __slots__ = ("choices",)
    choices: set[str]

    def __post_init__(self) -> None:
        self.choices = {choice.lower() for choice in self.choices}

    def __call__(self, name: str) -> bool:
        return name.lower() in self.choices


@dataclass(frozen=True, slots=True)
class Dependency:
    case: "TestCase"
    when: str | None

    def is_satisfied(self) -> bool:
        from .status import Category

        if not self.case.is_done():
            return False
        when = self.when
        if when is None:
            return True
        assert isinstance(when, str)
        if when in ("*", "always"):
            return self.case.is_done()
        if when == "on_success":
            return self.case.status.category is Category.PASS
        elif when == "on_failure":
            return self.case.status.category is Category.FAIL
        expr = Expression.compile(when)
        choices = (self.case.status.category.name, self.case.status.outcome.name)
        return expr.evaluate(AnyMatcher(set(choices)))

    def is_done(self) -> bool:
        return self.case.is_done()


class TestCase(BaseJob):
    def __init__(
        self,
        spec: "ResolvedSpec",
        workspace: ExecutionSpace,
        dependencies: list[Dependency] | None = None,
    ) -> None:
        super().__init__()
        self.spec = spec
        self.workspace = workspace
        self.rparameters = self.get_resource_parameters_from_spec()
        pm = config.pluginmanager.hook
        self.launcher: Launcher = pm.canary_runtest_launcher(case=self)
        self._mask: Mask | None = None

        # Resources assigned to this test during execution
        self._resources: dict[str, list[dict]] = {}
        self.variables: dict[str, str | None] = self.get_environ_from_spec()

        self.depends_on: list[Dependency] = dependencies or []
        self.dependencies: list["TestCase"] = [d.case for d in self.depends_on]

    def __eq__(self, other) -> bool:
        if not isinstance(other, TestCase):
            raise TypeError(f"Cannot compare TestCase with type {other.__class__.__name__}")
        return self.id == other.id

    def __str__(self) -> str:
        return self.spec.display_name()

    def __repr__(self) -> str:
        return self.spec.display_name()

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def exclusive(self) -> bool:
        return self.spec.exclusive

    def get_artifacts(self) -> list[str]:
        artifacts: list[str] = []
        for artifact in self.spec.artifacts:
            if artifact.active(self.status):
                matches = self.workspace.dir.rglob(artifact.pattern)
                artifacts.extend([str(match.relative_to(self.workspace.dir)) for match in matches])
        return artifacts

    @property
    def upstreams(self) -> list["TestCase"]:
        return [d.case for d in self.depends_on]

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

    def total_timeout(self) -> float:
        fac: float = 1.0
        if cli_timeouts := config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                fac = float(t)
        elif t := config.get("run:timeout:multiplier"):
            fac = float(t)
        return fac * self.timeout

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

    @property
    def viewpath(self) -> str:
        return self.spec.viewpath

    def display_name(self, **kwargs) -> str:
        return self.spec.display_name(**kwargs)

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)

    def add_variables(self, **kwds: str) -> None:
        self.variables.update(kwds)

    def statline(self, style: Literal["none", "rich", "html"] = "none") -> str:
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
        return self.rparameters.get("cpus") or 1

    @property
    def gpus(self) -> int:
        return self.rparameters.get("gpus") or 0

    @property
    def nodes(self) -> int:
        return self.rparameters.get("nodes") or 1

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
        for name, value in self.rparameters.items():
            if name == "nodes":
                continue
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

    def is_done(self) -> bool:
        return self.state.is_done()

    def dropped(self) -> bool:
        return self.status.is_skipped()

    def is_runnable(self) -> bool:
        """True if this case could still run in the future."""
        if self.state.is_done():
            return False
        if self.status.is_skipped():
            return False
        # If any dependency finished in a way that violates criteria, this case will never run
        if self.depends_on and any(d.is_done() and not d.is_satisfied() for d in self.depends_on):
            return False
        return True

    def refresh_readiness(self) -> None:
        if self.state.is_done() or not self.depends_on:
            return
        for dep in self.depends_on:
            if not dep.is_done():
                continue
            if not dep.is_satisfied():
                self.state.phase = JobPhase.DONE
                self.status = Status.BLOCKED(
                    f"Dependency {dep.case.name} finished with {dep.case.status.outcome.name!r}; "
                    f"needed {dep.when!r}"
                )
                return

    def is_ready(self) -> bool:
        if self.state.is_done() or self.state.is_running():
            return False
        self.refresh_readiness()
        if not self.is_runnable():
            return False
        if not self.depends_on:
            return True
        all_satisfied = all(d.is_satisfied() for d in self.depends_on if d.is_done())
        all_done = all(d.is_done() for d in self.depends_on)
        return all_satisfied and all_done

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
        from .status import Outcome

        code: int
        xstatus = self.spec.xstatus
        try:
            if self.is_runnable():
                with self.workspace.openfile(self.stdout, "a") as fh:
                    prefix = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
                    fh.write(f"[{prefix}] Begin executing {self.spec.fullname}\n")
                with self.workspace.enter(), self.timekeeper.timeit():
                    self.state.phase = JobPhase.RUNNING
                    self.save()
                    code = self.launcher.run(case=self)
                    self.update_status_from_exit_code(code=code)
        except KeyboardInterrupt:
            self.status = Status.INTERRUPTED()
        except SystemExit as e:
            self.update_status_from_exit_code(code=e.code or 0)
        except TestDiffed as e:
            stat = "XDIFF" if xstatus == Outcome.DIFFED.value else "DIFFED"
            default_reason = None
            if stat == "DIFFED":
                default_reason = "Empty TestDiffed exception raised during execution"
            self.status.set(outcome=stat, reason=default_reason if not e.args else e.args[0])
        except TestFailed as e:
            f_status = Outcome.FAILED.value
            stat = "XFAIL" if (xstatus == f_status or xstatus < 0) else "FAILED"
            default_reason = None
            if stat == "FAILED":
                default_reason = "Empty TestFailed exception raised during execution"
            self.status.set(outcome=stat, reason=None if not e.args else e.args[0])
        except TestSkipped as e:
            self.status.set(outcome="SKIPPED", reason=None if not e.args else e.args[0])
        except TestTimedOut as e:
            self.status.set(outcome="TIMEOUT", reason=None if not e.args else e.args[0])
        except BaseException as e:
            if config.get("debug"):
                logger.exception("Exception during test case execution")
            fh = io.StringIO()
            traceback.print_exc(file=fh, limit=2)
            reason = fh.getvalue()
            f = self.stderr or self.stdout
            with self.workspace.openfile(f, "a") as fp:
                fp.write(reason)
            self.status.set(outcome="ERROR", reason=reason)
        finally:
            self.state.phase = JobPhase.DONE
            logger.debug(f"Finished executing {self.spec.fullname}: status={self.status}")
            self.save()
        return

    def getstate(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "status": self.status,
            "timekeeper": self.timekeeper,
            "measurements": self.measurements,
        }

    def setstate(self, data: dict[str, Any]) -> None:
        """The companion of getstate, save results from the test ran in a child process in the
        parent process"""
        if status := data.get("status"):
            self.status.set(
                category=status.category,
                outcome=status.outcome,
                reason=status.reason,
                code=status.code,
            )
        if timekeeper := data.get("timekeeper"):
            self.timekeeper.submitted = timekeeper.submitted
            self.timekeeper.started = timekeeper.started
            self.timekeeper.finished = timekeeper.finished
        if measurements := data.get("measurements"):
            self.measurements.update(measurements.data)
        if st := data.get("state"):
            self.state.phase = st.phase
        elif not self.status.has_category("NONE"):
            self.state.phase = JobPhase.DONE

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
        from .status import Outcome

        if isinstance(code, str):
            code = 1
        xcode = self.spec.xstatus

        if xcode == Outcome.DIFFED.value:
            if code != Outcome.DIFFED.value:
                self.status = Status.FAILED(
                    reason=f"{self.spec.display_name()}: expected test to diff",
                    code=code,
                )
            else:
                self.status = Status.XDIFF()
        elif xcode != 0:
            # Expected to fail
            if xcode > 0 and code != xcode:
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
        elif code == Outcome.DIFFED.value:
            self.status = Status.DIFFED(reason=f"Test exited with diff exit code = {code}")
        elif code == Outcome.SKIPPED.value:
            self.status = Status.SKIPPED(reason=f"Test exited with skip exit code = {code}")
        else:
            self.status = Status.FAILED(code=code, reason=f"Test exited with exit code = {code}")

    def refresh(self) -> None:
        try:
            data = json.loads(self.workspace.joinpath("testcase.lock").read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return
        status = data["status"]
        self.variables = data["variables"]
        self.status = Status(
            category=status["category"],
            outcome=status["outcome"],
            reason=status["reason"],
            code=status["code"],
        )
        if st := data.get("state"):
            phase = st.get("phase", "PENDING")
            self.state.phase = JobPhase(phase)
        tk = data["timekeeper"]
        self.timekeeper.submitted = tk["submitted"]
        self.timekeeper.started = tk["started"]
        self.timekeeper.finished = tk["finished"]

    def set_runtime_env(self, env: MutableMapping[str, str]) -> None:
        env[config.CONFIG_ENV_CFG64] = config.serialize()
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
        resource_types: set[str] = set(config.pluginmanager.hook.canary_resource_pool_types())
        p = self.spec.parameters | self.spec.meta_parameters
        rparameters: dict[str, int] = {}
        for key in p.keys() & (resource_types | {"nodes"}):
            value = p[key]
            if not isinstance(value, int):
                raise InvalidTypeError(key, value)
            rparameters[key] = value

        # Make sure required resource parameters exist
        cpus: int | None = rparameters.get("cpus")
        gpus: int | None = rparameters.get("gpus")
        nodes: int | None = rparameters.get("nodes")
        rpcount = config.pluginmanager.hook.canary_resource_pool_count_per_node
        cpus_per_node: int = rpcount(type="cpu") or cpu_count()
        gpus_per_node: int = rpcount(type="gpu") or 0
        if nodes is not None:
            if cpus is None:
                cpus = nodes * cpus_per_node
            if gpus is None:
                gpus = nodes * gpus_per_node
        else:
            if cpus is None:
                cpus = 1
            if gpus is None:
                gpus = 0
            nodes = max(1, ceil_div(cpus, cpus_per_node))
            if gpus_per_node > 0:
                nodes = max(nodes, ceil_div(gpus, gpus_per_node))
        assert cpus is not None and gpus is not None and nodes is not None
        rparameters.update({"cpus": cpus, "gpus": gpus, "nodes": nodes})
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
            "state": {"phase": self.state.phase.value},
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
            "state": {"phase": self.state.phase.value},
            "status": self.status.asdict(),
            "timekeeper": self.timekeeper.asdict(),
            "measurements": self.measurements.asdict(),
            "variables": self.variables,
            "resources": self.resources,
            "dependencies": [dep.id for dep in self.dependencies],
            "rparameters": self.rparameters,
        }
        return json.dumps_min(record)

    def read_output(self, compress: bool = False) -> str:
        if self.status.is_skipped():
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
            kb_to_keep = 2 if self.status.is_success() else 300
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
        if not self.status.is_success():
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
            fn = datetime.datetime.fromtimestamp
            dt = fn(self.timekeeper.started) if self.timekeeper.started > 0 else None
            if dt is not None:
                history["last_run"] = dt.strftime("%c")
            name = self.status.category.lower()
            history[name] = history.get(name, 0) + 1
            if self.timekeeper.duration() >= 0 and self.status.is_success():
                count: int = 0
                metrics = cache.setdefault("metrics", {})
                t = metrics.setdefault("time", {})
                if t:
                    # Welford's single pass online algorithm to update statistics
                    count, mean, variance = t["count"], t["mean"], t["variance"]
                    delta = self.timekeeper.duration() - mean
                    mean += delta / (count + 1)
                    M2 = variance * count
                    delta2 = self.timekeeper.duration() - mean
                    M2 += delta * delta2
                    variance = M2 / (count + 1)
                    minimum = min(t["min"], self.timekeeper.duration())
                    maximum = max(t["max"], self.timekeeper.duration())
                else:
                    variance = 0.0
                    mean = minimum = maximum = self.timekeeper.duration()
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


def find_cache_dir(start: Path) -> Path | None:
    if "CANARY_CACHE_DIR" in os.environ:
        return Path(os.environ["CANARY_CACHE_DIR"])
    d = start
    while d != d.parent:
        if (d / "WORKSPACE.TAG").exists():
            return d / "cache"
        d = d.parent
    return None


def ceil_div(a: int, b: int) -> int:
    assert b != 0, "denominator must not be 0"
    return (a + b - 1) // b


class MissingSourceError(Exception):
    pass


class InvalidTypeError(Exception):
    def __init__(self, name, value):
        class_name = value.__class__.__name__
        super().__init__(f"expected type({name})=type({value!r})=int, not {class_name}")
