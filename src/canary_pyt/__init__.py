# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import inspect
from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Literal
from typing import Sequence

from _canary import enums
from _canary.generator import CanaryDSLSpecGenerator
from _canary.hookspec import hookimpl
from _canary.ir import DependencySelector
from _canary.paramset import ParameterSet
from _canary.status import Outcome
from _canary.third_party.monkeypatch import monkeypatch
from _canary.util import logging

WhenType = str | dict[str, str]
DependencyType = str | dict[str, Any] | DependencySelector
logger = logging.get_logger(__name__)


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


class PYTAdapter(CanaryDSLSpecGenerator):
    file_patterns: ClassVar[tuple[str, ...]] = ("*.pyt", "canary_*.py")

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self._directive_recorder: DirectiveRecorder | None = None
        self.load()

    def load(self) -> None:
        import canary
        from _canary import set_file_scanning

        try:
            set_file_scanning(True)
            recorder = DirectiveRecorder(target=self, record_location=True)
            self._directive_recorder = recorder
            with monkeypatch.context() as mp:
                mp.setattr(canary, "directives", recorder)
                code = compile(open(self.file).read(), self.file.as_posix(), "exec")
                safe_globals = {"__name__": "__load__", "__file__": self.file.as_posix()}
                try:
                    exec(code, safe_globals)  # nosec B102
                except SystemExit:
                    pass
        finally:
            set_file_scanning(False)

    # --------------------------------------------------------------------------------
    # f_* directive interface used by .pyt files
    # --------------------------------------------------------------------------------

    def f_testname(self, arg: str) -> None:
        self.add_family(arg)

    f_name = f_testname

    def f_keywords(self, *args: str, when: WhenType | None = None) -> None:
        self.add_keywords(*args, when=when)

    def f_owners(self, *args: str) -> None:
        self.add_owner(*args)

    def f_owner(self, arg: str) -> None:
        self.add_owner(arg)

    def f_timeout(self, arg: str | float | int, *, when: WhenType | None = None) -> None:
        self.add_timeout(arg, when=when)

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
            pset = ParameterSet.centered_parameter_space(names, values, file=self.file.as_posix())
        elif type is enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                names, values, samples=samples, random_seed=random_seed, file=self.file.as_posix()
            )
        else:
            pset = ParameterSet.list_parameter_space(names, values, file=self.file.as_posix())
        self.add_parameter_set(pset, when=when)

    def f_copy(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        for arg in args:
            self.add_source(action="copy", src=arg, when=when)
        if src is not None:
            self.add_source(action="copy", src=src, dst=dst, when=when)

    def f_link(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        for arg in args:
            self.add_source(action="link", src=arg, when=when)
        if src is not None:
            self.add_source(action="link", src=src, dst=dst, when=when)

    def f_sources(self, *args: str, when: WhenType | None = None) -> None:
        for arg in args:
            self.add_source(action="none", src=arg, when=when)

    def f_baseline(
        self,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
        flag: str | None = None,
    ) -> None:
        self.add_baseline(src=src, dst=dst, flag=flag, when=when)

    def f_depends_on(
        self,
        arg: DependencyType | list[DependencyType],
        when: WhenType | None = None,
        **kwargs: Any,
    ) -> None:
        dependencies = parse_dependencies(arg, **kwargs)
        for dep in dependencies:
            self.add_dependency(dep, when=when)

    def f_set_attribute(self, *, when: WhenType | None = None, **attributes: Any) -> None:
        self.set_attributes(when=when, **attributes)

    def f_load_module(
        self, arg: str, *, when: WhenType | None = None, use: str | None = None
    ) -> None:
        self.add_module(arg, use=use, when=when)

    def f_source(self, arg: str, *, when: WhenType | None = None) -> None:
        self.add_rcfile(arg, when=when)

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
        self.add_artifact(file, upon=mapped, when=when)

    def f_enable(self, *args: bool, when: WhenType | None = None) -> None:
        value = True if not args else bool(args[0])
        self.set_enable(value, when=when)

    def f_skipif(self, arg: bool, *, reason: str) -> None:
        self.set_skipif(bool(arg), reason=reason)

    def f_filter_warnings(self, arg: bool) -> None:
        self.set_filter_warnings(bool(arg))

    def f_preload(self, arg: str, *, when: WhenType | None = None) -> None:
        self.set_preload(arg, when=when)

    def f_exclusive(self, *, when: WhenType | None = None) -> None:
        self.set_exclusive(when=when)

    def f_xdiff(self, *, when: WhenType | None = None) -> None:
        self.set_xdiff(when=when)

    def f_xfail(self, *, code: int = -1, when: WhenType | None = None) -> None:
        self.set_xfail(code=code, when=when)

    def f_generate_composite_base_case(
        self,
        *,
        when: WhenType | None = None,
        flag: str | None = None,
        script: str | None = None,
        requires: str = "success",
    ) -> None:
        self.set_analyze(when=when, flag=flag, script=script, requires=requires)

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
        self.set_analyze(when=when, flag=flag, script=script, requires=requires)


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


@hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(PYTAdapter)
