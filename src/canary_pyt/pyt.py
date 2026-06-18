# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import errno
import glob
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Literal
from typing import Sequence

from _canary import enums
from _canary.error import diff_exit_status
from _canary.ir import DependencySelector
from _canary.ir import JobSpecIR
from _canary.jobspec import Artifact
from _canary.jobspec import Asset
from _canary.jobspec import BaselineAction
from _canary.jobspec import BaselineCopyAction
from _canary.jobspec import BaselineScriptAction
from _canary.jobspec import Mask
from _canary.paramset import ParameterSet
from _canary.status import Outcome
from _canary.third_party.monkeypatch import monkeypatch
from _canary.util import logging
from _canary.util import reducer
from _canary.util.field import Field
from _canary.util.reducer import Reducer
from _canary.util.reducer import unique
from _canary.util.string import stringify
from _canary.util.time import time_in_seconds

if TYPE_CHECKING:
    from _canary.jobspec import JobSpec


WhenType = str | dict[str, str]
DependencyType = str | dict[str, Any] | DependencySelector

logger = logging.get_logger(__name__)


def flatten_unique(xss: list[list[str]]) -> list[str]:
    return unique(reducer.concat(xss))


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    name: str
    use: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzeSpec:
    flag: str | None = None
    script: str | None = None
    requires: str = "success"


@dataclass(frozen=True, slots=True)
class XstatusSpec:
    code: int = 0


@dataclass(frozen=True)
class RecordedDirectiveCall:
    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    file: str | None = None
    line: int | None = None


class DirectiveRecorder:
    __slots__ = ("_target", "_record_location", "_calls")

    _reserved = {
        "calls",
        "recorded_calls",
        "__dict__",
        "__class__",
        "__getattr__",
        "__getattribute__",
        "__setattr__",
        "__slots__",
    }

    _target: Any | None
    _record_location: bool
    _calls: list[RecordedDirectiveCall]

    def __init__(self, target: Any | None = None, *, record_location: bool = True) -> None:
        self._target = target
        self._record_location = record_location
        self._calls = []

    @property
    def recorded_calls(self) -> list[RecordedDirectiveCall]:
        return self._calls  # type: ignore[return-value]

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name in self._reserved or name.startswith("_"):
            raise AttributeError(name)

        def _directive(*args: Any, **kwargs: Any) -> Any:
            file: str | None = None
            line: int | None = None
            if self._record_location:
                frame = inspect.currentframe()
                caller = frame.f_back if frame else None
                if caller is not None:
                    file = caller.f_code.co_filename
                    line = caller.f_lineno

            self._calls.append(
                RecordedDirectiveCall(
                    name=name, args=tuple(args), kwargs=dict(kwargs), file=file, line=line
                )
            )

            tgt = self._target
            if tgt is not None:
                fn = getattr(tgt, f"f_{name}", None)
                if fn is None:
                    raise AttributeError(
                        f"Unknown directive {name!r} (no method f_{name} on {type(tgt).__name__})"
                    )
                return fn(*args, **kwargs)

            return None

        return _directive


class PYTModel:
    file_patterns: ClassVar[tuple[str, ...]] = ()

    def __init__(self, root: str, path: str | None = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = Path(root).resolve()
        self.path = Path(path)
        self.file = Path(self.root).joinpath(self.path)
        if not self.file.exists():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = self.file.stem

        self.families: Field[str, list[str]] = Field(reducer=reducer.IDENTITY)
        self.parameter_sets: Field[ParameterSet, list[ParameterSet]] = Field(
            reducer=reducer.IDENTITY
        )
        self.meta_parameters: Field[dict[str, Any], dict[str, Any]] = Field(
            reducer=reducer.MERGE_DICTS
        )
        self.keywords: Field[list[str], list[str]] = Field(
            reducer=Reducer("flatten_unique", flatten_unique)
        )
        self.timeout: Field[float, float | None] = Field.make(reducer.LAST)
        self.modules: Field[ModuleSpec, list[ModuleSpec]] = Field(reducer=reducer.IDENTITY)
        self.rcfiles: Field[str, list[str]] = Field(reducer=reducer.IDENTITY)
        self.artifacts: Field[Artifact, list[Artifact]] = Field(reducer=reducer.IDENTITY)
        self.sources: Field[Asset, list[Asset]] = Field(reducer=reducer.IDENTITY)
        self.baseline: Field[BaselineAction, list[BaselineAction]] = Field(reducer=reducer.IDENTITY)
        self.exclusive: Field[bool, bool] = Field(reducer=reducer.ANY)
        self.depends_on: Field[DependencySelector, list[DependencySelector]] = Field(
            reducer=reducer.IDENTITY
        )
        self.attributes: Field[dict[str, Any], dict[str, Any]] = Field(reducer=reducer.MERGE_DICTS)
        self.analyze: Field[AnalyzeSpec, AnalyzeSpec | None] = Field.make(reducer.LAST)
        self.preload: Field[str, str | None] = Field.make(reducer.LAST)
        self.enable: Field[bool, list[bool]] = Field(reducer=reducer.IDENTITY)
        self.skip_reason: Field[str, str | None] = Field.make(reducer.LAST)
        self.xstatus: Field[XstatusSpec, XstatusSpec | None] = Field.make(reducer.LAST)

        self.filter_warnings: bool = False
        self.owners: list[str] = []

        self.command: list[str] = [sys.executable, self.path.name]

    def option_expressions(self) -> list[str]:
        option_expressions: set[str] = set()
        for _, attr in vars(self).items():
            if not isinstance(attr, Field):
                continue
            for c in attr.items:
                expr = c.when.option_expr
                if expr:
                    option_expressions.add(expr)
        return sorted(option_expressions)

    # ----------------------------- add_* API -----------------------------

    def add_family(self, name: str, when: WhenType | None = None) -> None:
        self.families.add(name, when=when)

    def add_owner(self, *names: str) -> None:
        self.owners.extend(names)

    def add_keywords(self, *words: str, when: WhenType | None = None) -> None:
        self.keywords.add(list(words), when=when)

    def add_timeout(self, value: str | float | int, when: WhenType | None = None) -> None:
        self.timeout.add(float(time_in_seconds(value)), when=when)

    def add_parameter_set(self, pset: ParameterSet, when: WhenType | None = None) -> None:
        self.parameter_sets.add(pset, when=when)

    def add_module(self, name: str, use: str | None = None, when: WhenType | None = None) -> None:
        self.modules.add(ModuleSpec(name=name, use=use), when=when)

    def add_rcfile(self, name: str, when: WhenType | None = None) -> None:
        self.rcfiles.add(name, when=when)

    def add_artifact(
        self,
        pattern: str,
        upon: Literal["always", "never", "on_failure", "on_success"] = "always",
        when: WhenType | None = None,
    ) -> None:
        self.artifacts.add(Artifact(pattern=pattern, when=upon), when=when)

    def add_source(
        self,
        *,
        action: Literal["copy", "link", "none"],
        src: str | Path,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        dirname = self.file.parent
        a = Path(src)
        if not a.is_absolute():
            a = dirname / a
        asset = Asset(action=action, src=a, dst=dst)
        self.sources.add(asset, when=when)

    def add_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        flag: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        b: BaselineAction
        if flag is not None:
            if src is not None or dst is not None:
                raise TypeError("'flag' and 'src/dst' or mutually exclusive")
            b = BaselineScriptAction(script=[sys.executable, self.file.name, flag])
        else:
            if src is None or dst is None:
                raise TypeError("baseline: both 'src' and 'dst' are required arguments")
            b = BaselineCopyAction(src=Path(src), dst=dst)
        self.baseline.add(b, when=when)

    def set_exclusive(self, when: WhenType | None = None) -> None:
        self.exclusive.add(True, when=when)

    def add_dependency(self, dep: DependencySelector, when: WhenType | None = None) -> None:
        self.depends_on.add(dep, when=when)

    def set_attributes(self, when: WhenType | None = None, **attrs: Any) -> None:
        self.attributes.add(dict(attrs), when=when)

    def set_preload(self, arg: str, when: WhenType | None = None) -> None:
        self.preload.add(arg, when=when)

    def set_enable(self, value: bool, when: WhenType | None = None) -> None:
        self.enable.add(bool(value), when=when)

    def set_skipif(self, skip: bool, reason: str) -> None:
        if skip:
            self.skip_reason.add(reason, when=None)

    def set_filter_warnings(self, value: bool) -> None:
        if value:
            self.filter_warnings = True

    def set_analyze(
        self,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
        requires: str = "success",
    ) -> None:
        self.analyze.add(AnalyzeSpec(flag=flag, script=script, requires=requires), when=when)

    def set_xfail(self, when: WhenType | None = None, code: int = -1) -> None:
        self.xstatus.add(XstatusSpec(code=code), when=when)

    def set_xdiff(self, when: WhenType | None = None) -> None:
        self.xstatus.add(XstatusSpec(code=diff_exit_status), when=when)

    def set_meta_parameters(self, when: WhenType | None = None, **params: Any) -> None:
        self.meta_parameters.add(dict(params), when=when)

    def set_resource_parameter(
        self,
        name: Literal["cpus", "gpus", "nodes"],
        value: int,
        when: WhenType | None = None,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
        minimum = 0 if name == "gpus" else 1
        if value < minimum:
            raise ValueError(f"{name} must be >= {minimum}, got {value}")
        self.set_meta_parameters(when=when, **{name: value})

    # ----------------------------- getters -----------------------------

    def get_families(self, on_options: list[str] | None = None) -> list[str]:
        names = self.families.eval(on_options=on_options)
        return names or [self.name]

    def get_parameters(
        self, family: str, on_options: list[str] | None = None
    ) -> list[dict[str, Any]]:
        psets = self.parameter_sets.eval(family=family, on_options=on_options)
        return ParameterSet.combine(psets)

    def get_keywords(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[str]:
        return self.keywords.eval(family=family, parameters=parameters, on_options=on_options)

    def get_timeout(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> float | None:
        return self.timeout.eval(family=family, parameters=parameters, on_options=on_options)

    def get_modules(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[ModuleSpec]:
        return self.modules.eval(family=family, parameters=parameters, on_options=on_options)

    def get_rcfiles(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> list[str]:
        return self.rcfiles.eval(family=family, parameters=parameters, on_options=on_options)

    def get_artifacts(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
        subs: dict[str, Any] | None = None,
    ) -> list[Artifact]:
        artifacts = self.artifacts.eval(family=family, parameters=parameters, on_options=on_options)
        if subs:
            for i, a in enumerate(artifacts):
                artifacts[i] = Artifact(
                    pattern=self.safe_substitute(a.pattern, **subs), when=a.when
                )
        return artifacts

    def get_sources(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
        subs: dict[str, Any] | None = None,
    ) -> list[Asset]:
        sources = self.sources.eval(family=family, parameters=parameters, on_options=on_options)

        assets: list[Asset] = []
        base_dir = self.file.parent

        def _has_glob(p: str) -> bool:
            return any(ch in p for ch in ("*", "?", "["))

        for s in sources:
            src_text = s.src.as_posix()
            dst_text = s.dst

            if subs:
                src_text = self.safe_substitute(src_text, **subs)
                dst_text = None if dst_text is None else self.safe_substitute(dst_text, **subs)

            # Expand globs (relative patterns resolved from the test file directory)
            if _has_glob(src_text):
                if os.path.isabs(src_text):
                    matches = [Path(p) for p in glob.glob(src_text)]
                else:
                    matches = sorted(base_dir.glob(src_text))

                if not matches:
                    logger.warning("source glob matched nothing: %r (from %s)", src_text, self.file)
                    continue

                # If dst is provided and multiple files match, a single dst is ambiguous
                if dst_text is not None and len(matches) > 1:
                    logger.warning(
                        "source glob %r matched %d files but dst=%r was provided; "
                        "ignoring dst and using default destination names",
                        src_text,
                        len(matches),
                        dst_text,
                    )
                    dst_use = None
                else:
                    dst_use = dst_text

                for m in matches:
                    assets.append(Asset(src=m, dst=dst_use, action=s.action))
            else:
                assets.append(Asset(src=Path(src_text), dst=dst_text, action=s.action))

        return assets

    def get_baseline(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
        subs: dict[str, Any] | None = None,
    ) -> list[BaselineAction]:
        actions = self.baseline.eval(family=family, parameters=parameters, on_options=on_options)
        if subs:
            for i, a in enumerate(actions):
                if isinstance(a, BaselineCopyAction):
                    src = self.safe_substitute(str(a.src), **subs)
                    dst = self.safe_substitute(a.dst, **subs)
                    actions[i] = BaselineCopyAction(src=Path(src), dst=dst)
        return actions

    def get_exclusive(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> bool:
        return self.exclusive.eval(family=family, parameters=parameters, on_options=on_options)

    def get_dependencies(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
        subs: dict[str, Any] | None = None,
    ) -> list[DependencySelector]:
        deps = self.depends_on.eval(family=family, parameters=parameters, on_options=on_options)
        if subs:
            for i, dep in enumerate(deps):
                deps[i] = DependencySelector(
                    pattern=self.safe_substitute(dep.pattern, **subs),
                    expects=dep.expects,
                    when=dep.when,
                )
        return deps

    def get_attributes(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.attributes.eval(family=family, parameters=parameters, on_options=on_options)

    def get_preload(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> str | None:
        return self.preload.eval(family=family, parameters=parameters, on_options=on_options)

    def get_enable(self, family=None, parameters=None, on_options=None) -> tuple[bool, str | None]:
        for c in self.enable.items:
            result = c.when.evaluate(testname=family, on_options=on_options, parameters=parameters)
            if c.value is True and not result.value:
                return False, result.reason
            if c.value is False and result.value:
                return False, result.reason or "[bold]enable=False[/]"
        return True, None

    def get_skip_reason(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> str | None:
        return self.skip_reason.eval(family=family, parameters=parameters, on_options=on_options)

    def get_xstatus(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> int:
        xs = self.xstatus.eval(family=family, parameters=parameters, on_options=on_options)
        return xs.code if xs is not None else 0

    def get_analyze(
        self, family: str | None = None, on_options: list[str] | None = None
    ) -> AnalyzeSpec | None:
        return self.analyze.eval(family=family, parameters=None, on_options=on_options)

    def get_meta_parameters(
        self,
        family: str | None = None,
        parameters: dict[str, Any] | None = None,
        on_options: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.meta_parameters.eval(
            family=family, parameters=parameters, on_options=on_options
        )

    # ----------------------------- substitution helpers -----------------------------

    def safe_substitute(self, text: str, **kwds: Any) -> str:
        if "$" in text:
            return Template(text).safe_substitute(**kwds)
        return text.format(**kwds)

    def _sub_kwds(
        self,
        family: str | None,
        parameters: dict[str, Any] | None,
        meta_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kw: dict[str, Any] = {}
        if parameters:
            kw.update({k: stringify(v) for k, v in parameters.items()})
        if meta_parameters:
            kw.update({k: stringify(v) for k, v in meta_parameters.items()})
        if family:
            kw["name"] = family
        for k in list(kw.keys()):
            kw[k.upper()] = kw[k]
        return kw


class PYTAdapter:
    def __init__(self, model: PYTModel) -> None:
        self.m = model

    def apply(self, calls: list[RecordedDirectiveCall]) -> None:
        for c in calls:
            fn = getattr(self, f"f_{c.name}", None)
            if fn is None:
                raise AttributeError(f"Unknown directive {c.name!r}")
            fn(*c.args, **c.kwargs)

    def f_testname(self, arg: str) -> None:
        self.m.add_family(arg)

    f_name = f_testname

    def f_keywords(self, *args: str, when: WhenType | None = None) -> None:
        self.m.add_keywords(*args, when=when)

    def f_owners(self, *args: str) -> None:
        self.m.add_owner(*args)

    def f_owner(self, arg: str) -> None:
        self.m.add_owner(arg)

    def f_timeout(self, arg: str | float | int, *, when: WhenType | None = None) -> None:
        self.m.add_timeout(arg, when=when)

    def f_parameterize(
        self,
        names: str | Sequence[str],
        values: list[Sequence[Any] | Any],
        *,
        when: WhenType | None = None,
        type: enums.enums = enums.list_parameter_space,
        samples: int = 10,
        random_seed: float = 1234.0,
    ) -> None:
        if type is enums.centered_parameter_space:
            pset = ParameterSet.centered_parameter_space(names, values, file=self.m.file.as_posix())
        elif type is enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                names, values, samples=samples, random_seed=random_seed, file=self.m.file.as_posix()
            )
        else:
            pset = ParameterSet.list_parameter_space(names, values, file=self.m.file.as_posix())
        self.m.add_parameter_set(pset, when=when)

    def f_cpus(self, arg: int, *, when: WhenType | None = None) -> None:
        self.m.set_resource_parameter("cpus", arg, when=when)

    def f_gpus(self, arg: int, *, when: WhenType | None = None) -> None:
        self.m.set_resource_parameter("gpus", arg, when=when)

    def f_nodes(self, arg: int, *, when: WhenType | None = None) -> None:
        self.m.set_resource_parameter("nodes", arg, when=when)

    def f_copy(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        for arg in args:
            self.m.add_source(action="copy", src=arg, when=when)
        if src is not None:
            self.m.add_source(action="copy", src=src, dst=dst, when=when)

    def f_link(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        for arg in args:
            self.m.add_source(action="link", src=arg, when=when)
        if src is not None:
            self.m.add_source(action="link", src=src, dst=dst, when=when)

    def f_sources(self, *args: str, when: WhenType | None = None) -> None:
        for arg in args:
            self.m.add_source(action="none", src=arg, when=when)

    def f_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
        flag: str | None = None,
    ) -> None:
        self.m.add_baseline(src=src, dst=dst, flag=flag, when=when)

    def f_depends_on(
        self,
        arg: DependencyType | list[DependencyType],
        when: WhenType | None = None,
        **kwargs: Any,
    ) -> None:
        dependencies = parse_dependencies(arg, **kwargs)
        for dep in dependencies:
            self.m.add_dependency(dep, when=when)

    def f_set_attribute(self, *, when: WhenType | None = None, **attributes: Any) -> None:
        self.m.set_attributes(when=when, **attributes)

    def f_load_module(
        self, arg: str, *, when: WhenType | None = None, use: str | None = None
    ) -> None:
        self.m.add_module(arg, use=use, when=when)

    def f_source(self, arg: str, *, when: WhenType | None = None) -> None:
        self.m.add_rcfile(arg, when=when)

    def f_artifact(self, file: str, *, when: WhenType | None = None, upon: str = "always") -> None:
        mapped: Literal["always", "never", "on_failure", "on_success"]
        if upon == "always":
            mapped = "always"
        elif upon == "success":
            mapped = "on_success"
        elif upon == "failure":
            mapped = "on_failure"
        else:
            raise ValueError("upon: invalid value, choose from 'always', 'success', 'failure'")
        self.m.add_artifact(file, upon=mapped, when=when)

    def f_enable(self, *args: bool, when: WhenType | None = None) -> None:
        value = True if not args else bool(args[0])
        self.m.set_enable(value, when=when)

    def f_skipif(self, arg: bool, *, reason: str) -> None:
        self.m.set_skipif(bool(arg), reason=reason)

    def f_filter_warnings(self, arg: bool) -> None:
        self.m.set_filter_warnings(bool(arg))

    def f_preload(self, arg: str, *, when: WhenType | None = None) -> None:
        self.m.set_preload(arg, when=when)

    def f_exclusive(self, *, when: WhenType | None = None) -> None:
        self.m.set_exclusive(when=when)

    def f_xdiff(self, *, when: WhenType | None = None) -> None:
        self.m.set_xdiff(when=when)

    def f_xfail(self, *, code: int = -1, when: WhenType | None = None) -> None:
        self.m.set_xfail(code=code, when=when)

    def f_generate_composite_base_case(
        self,
        *,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
        requires: str = "success",
    ) -> None:
        self.m.set_analyze(when=when, flag=flag, script=script, requires=requires)

    def f_analyze(
        self,
        *,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
        requires: str = "success",
    ) -> None:
        if script is None and flag is None:
            flag = "--analyze"
        self.m.set_analyze(when=when, flag=flag, script=script, requires=requires)


class PYTLockEmitter:
    def lock(
        self,
        model: PYTModel,
        on_options: list[str] | None = None,
    ) -> Sequence["JobSpecIR | JobSpec"]:
        if model.filter_warnings:
            with logging.suppress_stream_below(logging.ERROR):
                return self._lock(model, on_options=on_options)
        return self._lock(model, on_options=on_options)

    def _lock(self, model: PYTModel, on_options: list[str] | None = None) -> list[JobSpecIR]:
        irs: list[JobSpecIR] = []
        families = model.get_families(on_options=on_options)

        for family in families:
            param_dicts = model.get_parameters(family, on_options=on_options)
            if not param_dicts:
                param_dicts = [{}]

            test_mask: str | None = None
            my_irs: list[JobSpecIR] = []

            for parameters in param_dicts:
                meta_params = model.get_meta_parameters(family, parameters, on_options=on_options)
                kw = model._sub_kwds(family, parameters, meta_parameters=meta_params)
                test_mask = model.get_skip_reason(family, parameters, on_options=on_options)
                keywords = model.get_keywords(family, parameters, on_options=on_options)
                modules = model.get_modules(family, parameters, on_options=on_options)
                timeout = model.get_timeout(family, parameters, on_options=on_options)
                preload = model.get_preload(family, parameters, on_options=on_options)
                xstatus = model.get_xstatus(family, parameters, on_options=on_options)
                exclusive = model.get_exclusive(family, parameters, on_options=on_options)
                rcfiles = model.get_rcfiles(family, parameters, on_options=on_options)
                artifacts = model.get_artifacts(family, parameters, on_options=on_options, subs=kw)
                attributes = model.get_attributes(family, parameters, on_options=on_options)
                baseline = model.get_baseline(family, parameters, on_options=on_options, subs=kw)
                assets = model.get_sources(family, parameters, on_options=on_options, subs=kw)
                deps = model.get_dependencies(family, parameters, on_options=on_options, subs=kw)

                ir = JobSpecIR(
                    file_root=Path(model.root),
                    file_path=Path(model.path),
                    family=family,
                    keywords=keywords,
                    parameters=parameters,
                    meta_parameters=meta_params,
                    modules=[m.name for m in modules],
                    owners=model.owners,
                    timeout=timeout or -1.0,
                    baseline=baseline,
                    assets=assets,
                    xstatus=xstatus,
                    preload=preload,
                    rcfiles=rcfiles,
                    artifacts=artifacts,
                    exclusive=exclusive,
                    dependencies=deps,
                    command=list(model.command),
                )
                ir.add_artifact("testcase.lock")
                ir.add_artifact(ir.stdout)
                if ir.stderr is not None:
                    ir.add_artifact(ir.stderr)

                enabled, reason = model.get_enable(family, parameters, on_options=on_options)
                if test_mask is None and enabled is False:
                    test_mask = reason

                if test_mask is not None:
                    ir.mask = Mask.masked(test_mask)

                if any(m.use is not None for m in modules):
                    mp = [x.strip() for x in os.getenv("MODULEPATH", "").split(":") if x.strip()]
                    for m in modules:
                        if m.use:
                            mp.insert(0, m.use)
                    ir.environment["MODULEPATH"] = ":".join(mp)

                for k, v in attributes.items():
                    ir.attributes[k] = v

                my_irs.append(ir)

            analyze = model.get_analyze(family, on_options=on_options)
            if analyze is not None:
                psets = model.parameter_sets.eval(family=family, on_options=on_options)
                if not any(psets):
                    raise ValueError(
                        "Generation of composite base job requires at least one parameter"
                    )

                modules = model.get_modules(family, parameters=None, on_options=on_options)
                deps = [
                    DependencySelector(pattern=d.id, expects=1, when=analyze.requires)
                    for d in my_irs
                ]

                pset_meta = []
                for ps in psets:
                    pset_meta.append({"keys": ps.keys, "values": ps.values})

                kw = model._sub_kwds(family, None)
                parent = JobSpecIR(
                    file_root=Path(model.root),
                    file_path=Path(model.path),
                    family=family,
                    baseline=[],
                    owners=model.owners,
                    modules=[m.name for m in modules],
                    assets=model.get_sources(family, on_options=on_options, subs=kw),
                    xstatus=model.get_xstatus(family, on_options=on_options),
                    preload=model.get_preload(family, on_options=on_options),
                    rcfiles=model.get_rcfiles(family, on_options=on_options),
                    keywords=model.get_keywords(family, on_options=on_options),
                    artifacts=model.get_artifacts(family, on_options=on_options, subs=kw),
                    exclusive=model.get_exclusive(family, on_options=on_options),
                    timeout=model.get_timeout(family, on_options=on_options) or -1.0,
                    attributes={"multicase": True, "paramsets": pset_meta},
                    dependencies=deps,
                )
                parent.add_artifact("testcase.lock")
                parent.add_artifact(parent.stdout)
                if parent.stderr is not None:
                    parent.add_artifact(parent.stderr)
                if analyze.flag:
                    parent.command = [sys.executable, os.path.basename(model.path), analyze.flag]
                elif analyze.script:
                    script = analyze.script
                    if os.path.exists(script):
                        f = Path(script).absolute()
                    else:
                        f = model.file.parent / script
                    if not any(
                        a.action in ("link", "copy") and a.src.name == f.name for a in parent.assets
                    ):
                        parent.assets.append(Asset(f, f.name, action="link"))
                    parent.command = [f.as_posix()]
                else:
                    parent.command = [sys.executable, model.path.name]

                if any(m.use is not None for m in modules):
                    mp = [x.strip() for x in os.getenv("MODULEPATH", "").split(":") if x.strip()]
                    for m in modules:
                        if m.use:
                            mp.insert(0, m.use)
                    parent.environment["MODULEPATH"] = ":".join(mp)

                enabled, reason = model.get_enable(family, parameters=None, on_options=on_options)
                if test_mask is None and enabled is False:
                    test_mask = reason

                if test_mask is not None:
                    parent.mask = Mask.masked(test_mask)

                my_irs.append(parent)

            irs.extend(my_irs)

        return irs


class PYTLoader:
    def __init__(self, *, file: Path) -> None:
        self.file = file

    def parse(self) -> list[RecordedDirectiveCall]:
        import canary
        from _canary import set_file_scanning

        recorder = DirectiveRecorder(target=None, record_location=True)
        try:
            set_file_scanning(True)
            with monkeypatch.context() as mp:
                mp.setattr(canary, "directives", recorder)
                with open(self.file) as fp:
                    code = compile(fp.read(), self.file.as_posix(), "exec")
                exec(code, {"__name__": "__load__", "__file__": self.file.as_posix()})  # nosec
        finally:
            set_file_scanning(False)

        return recorder.recorded_calls


def parse_dependencies(
    arg: DependencyType | list[DependencyType], **kwargs: Any
) -> list[DependencySelector]:
    if not isinstance(arg, (str, list, dict, DependencySelector)):
        raise TypeError(f"expected string, dict, or list, got {type(arg).__name__}: {arg!r}")

    legacy_expect = kwargs.pop("expect", None)
    legacy_result = kwargs.pop("result", None)
    if kwargs:
        # unknown kwargs should be an error; otherwise typos silently pass
        raise TypeError(f"depends_on(): unexpected keyword(s): {', '.join(sorted(kwargs))}")

    if isinstance(arg, DependencySelector):
        return [arg]

    if isinstance(arg, str):
        when: str = legacy_result or "on_success"
        if legacy_result is not None:
            s = "DEPRECATED: depends_on(%r, result=%r, ...); use depends_on({'job': %r, when=%r, ...})"
            logger.warning(s, arg, legacy_result, arg, legacy_result)
        expects: str | int = legacy_expect or "+"
        if legacy_expect is not None:
            s = "DEPRECATED: depends_on(%r, expect=%r, ...); use depends_on({'job': %r, expects=%r, ...})"
            logger.warning(s, arg, legacy_expect, arg, legacy_expect)
        return [parse_dependency({"job": arg, "when": when, "expects": expects}, 0)]

    if legacy_expect is not None or legacy_result is not None:
        bad: list[str] = []
        if legacy_expect is not None:
            bad.append(f"expect={legacy_expect!r}")
        if legacy_result is not None:
            bad.append(f"result={legacy_result!r}")
        s = f"depends_on(arg, {', '.join(bad)}, ...) is only supported when 'arg' is a single string"
        raise TypeError(s)

    if isinstance(arg, dict):
        return [parse_dependency(arg, 0)]

    return [parse_dependency(a, i) for i, a in enumerate(arg)]


def parse_dependency(arg: DependencyType, index: int) -> DependencySelector:
    prefix = "depends_on" if index is None else f"depends_on[{index}]"
    if not isinstance(arg, (str, dict)):
        raise TypeError(f"{prefix}: expected string or dict, got {type(arg).__name__}: {arg!r}")

    if isinstance(arg, str):
        if not arg.strip():
            raise ValueError(f"{prefix}: job must be a non-empty string")
        return DependencySelector(pattern=arg, expects="+", when="on_success")

    if isinstance(arg, DependencySelector):
        return arg

    assert isinstance(arg, dict)

    choices = {"job", "when", "expects"}
    extra = set(arg) - choices
    if extra:
        x = ", ".join(sorted(extra))
        s = ", ".join(sorted(choices))
        raise TypeError(f"{prefix}: invalid keys: {x}.  (choose from {s})")

    when: str = arg.get("when") or "on_success"
    choices = {name.lower() for name in Outcome._member_names_ if name != "NONE"}
    choices.update({"on_success", "on_failure", "always", "*"})
    if when.lower() not in choices:
        s = ", ".join(sorted(choices))
        raise TypeError(f"{prefix}['when']: invalid choice: {when!r} (choose from {s})")
    if when == "*":
        when = "always"

    if "job" not in arg:
        raise TypeError(f"{prefix}: missing required keyword 'job'") from None
    job = arg["job"]

    expects = arg.get("expects", "+")
    if not isinstance(expects, (str, int)):
        raise TypeError(f"{prefix}['expects']: invalid type {type(expects).__name__!r}")
    if isinstance(expects, str):
        choices = {"+", "?", "*"}
        if expects not in choices:
            s = ", ".join(sorted(choices))
            raise TypeError(f"{prefix}['expects']: invalid choice: {expects!r} (choose from {s})")
    elif expects <= 0:
        raise ValueError(f"{prefix}['expects']: invalid value: {expects!r} (must be > 0)")

    return DependencySelector(pattern=job, expects=expects, when=when)
