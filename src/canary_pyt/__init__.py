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
from _canary.generator import TestGenerator
from _canary.hookspec import hookimpl
from _canary.paramset import ParameterSet
from _canary.third_party.monkeypatch import monkeypatch

WhenType = str | dict[str, str]


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


class PYTAdapter(TestGenerator):
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
                code = compile(open(self.file).read(), self.file, "exec")
                safe_globals = {"__name__": "__load__", "__file__": self.file}
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
            pset = ParameterSet.centered_parameter_space(names, values, file=self.file)
        elif type is enums.random_parameter_space:
            pset = ParameterSet.random_parameter_space(
                names, values, samples=samples, random_seed=random_seed, file=self.file
            )
        else:
            pset = ParameterSet.list_parameter_space(names, values, file=self.file)
        self.add_parameter_set(pset, when=when)

    def f_copy(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        self.add_source("copy", *args, src=src, dst=dst, when=when)

    def f_link(
        self,
        *args: str,
        src: str | None = None,
        dst: str | None = None,
        when: WhenType | None = None,
    ) -> None:
        self.add_source("link", *args, src=src, dst=dst, when=when)

    def f_sources(self, *args: str, when: WhenType | None = None) -> None:
        self.add_source("sources", *args, when=when)

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
        *args: str,
        when: WhenType | None = None,
        expect: int | str | None = None,
        result: str | None = None,
    ) -> None:
        pattern = " ".join(args)
        self.add_dependency(pattern, expects=expect, result_match=result, when=when)

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


@hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(PYTAdapter)
