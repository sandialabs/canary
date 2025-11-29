import importlib
import os
import re
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any
from typing import Hashable
from typing import Iterable
from typing import Type

from . import config
from . import when
from .util import filesystem
from .util import json_helper as json
from .util import logging

if TYPE_CHECKING:
    from .testspec import ResolvedSpec


logger = logging.get_logger(__name__)


class RuleOutcome:
    __slots__ = ("ok", "reason")

    def __init__(self, ok: bool = True, reason: str | None = None) -> None:
        self.ok = ok
        self.reason = reason

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def failed(cls, reason: str) -> "RuleOutcome":
        return cls(ok=False, reason=reason)


class Rule:
    """A rule to decide whether a spec should be selected

    The __call__ method should return:
      - True: select the spec
      - False: drop the spec
    """

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        raise NotImplementedError

    def asdict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, params: dict[str, Any]) -> "Rule":
        return cls(**params)

    @cached_property
    def default_reason(self) -> str:
        raise NotImplementedError

    def serialize(self) -> str:
        meta = {
            "module": self.__class__.__module__,
            "classname": self.__class__.__name__,
            "params": self.asdict(),
        }
        return json.dumps_min(meta)

    @staticmethod
    def reconstruct(serialized: str) -> "Rule":
        meta = json.loads(serialized)
        module = importlib.import_module(meta["module"])
        cls: Type[Rule] = getattr(module, meta["classname"])
        rule = cls.from_dict(meta["params"])
        return rule


class KeywordRule(Rule):
    def __init__(self, keyword_exprs: list[str]):
        self.keyword_exprs = keyword_exprs

    @cached_property
    def default_reason(self) -> str:
        return "One or more keyword expressions did not match"

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        kwds = set(spec.keywords)
        kwds.update(spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
        kwd_all = contains_any(("__all__", ":all:"), self.keyword_exprs)
        if not kwd_all:
            for keyword_expr in self.keyword_exprs:
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    return RuleOutcome.failed(
                        "keyword expression @*{%r} did not match" % keyword_expr
                    )
        return RuleOutcome(True)


class ParameterRule(Rule):
    def __init__(self, parameter_expr: str) -> None:
        self.parameter_expr = parameter_expr

    @cached_property
    def default_reason(self) -> str:
        return "parameter expression @*{%s} did not match" % self.parameter_expr

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        match = when.when(
            {"parameters": self.parameter_expr},
            parameters=spec.parameters | spec.implicit_parameters,  # ty: ignore[unsupported-operator]
        )
        if match:
            return RuleOutcome(True)
        return RuleOutcome.failed(self.default_reason)


class IDsRule(Rule):
    def __init__(self, ids: Iterable[str] = ()) -> None:
        self.ids = list(ids)

    @cached_property
    def default_reason(self) -> str:
        return "test ID not in @*{%s}" % ",".join(self.ids)

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        if not any(spec.id.startswith(id) for id in self.ids):
            return RuleOutcome.failed(self.default_reason)
        return RuleOutcome(True)


class OwnersRule(Rule):
    def __init__(self, owners: Iterable[str] = ()) -> None:
        self.owners = set(owners)

    @cached_property
    def default_reason(self) -> str:
        return "not owned by @*{%s}" % ", ".join(self.owners)

    def asdict(self) -> dict[str, Any]:
        return {"owners": list(self.owners)}

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        if self.owners.intersection(spec.owners or []):
            return RuleOutcome(True)
        return RuleOutcome.failed(self.default_reason)


class PrefixRule(Rule):
    def __init__(self, prefixes: Iterable[str] = ()) -> None:
        self.prefixes = list(prefixes)

    @cached_property
    def default_reason(self) -> str:
        return "test file not a child of %s" % ", ".join(self.prefixes)

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        for prefix in self.prefixes:
            if not str(spec.file).startswith(prefix):
                return RuleOutcome.failed(f"test file not a child of {prefix}")
        return RuleOutcome(True)


class RegexRule(Rule):
    def __init__(self, regex: str) -> None:
        logger.warning("Regular expression search can be slow for large test suites")
        self.string: str = regex
        self.rx: re.Pattern = re.compile(regex)

    @cached_property
    def default_reason(self) -> str:
        return "@*{re.search(%r) is None} evaluated to @*g{True}" % self.string

    def asdict(self) -> dict[str, Any]:
        return {"regex": self.string}

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        if not filesystem.grep(self.rx, spec.file):
            for asset in spec.assets:
                if os.path.isfile(asset.src) and filesystem.grep(self.rx, asset.src):
                    break
            else:
                return RuleOutcome.failed(self.default_reason)
        return RuleOutcome(True)


class ResourceCapacityRule(Rule):
    def __init__(self) -> None:
        self.cache: dict[tuple[tuple[str, Any], ...], RuleOutcome] = {}

    @cached_property
    def default_reason(self) -> str:
        return "not enough resources"

    def asdict(self) -> dict[str, Any]:
        return {}

    def freeze_resource_set(
        self, resource_set: list[dict[str, Any]]
    ) -> tuple[tuple[str, Hashable], ...]:
        frozen = [(r["type"], r["slots"]) for r in resource_set]
        return tuple(sorted(frozen))

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        resource_set = spec.required_resources()
        frozen = self.freeze_resource_set(resource_set)
        if frozen not in self.cache:
            outcome: RuleOutcome | None = None
            pm = config.pluginmanager.hook
            try:
                result = pm.canary_resource_pool_accommodates(case=spec)
                outcome = RuleOutcome(ok=result.ok, reason=result.reason)
            except Exception as e:
                outcome = RuleOutcome.failed("@*{%s}(%r)" % (e.__class__.__name__, e.args[0]))
                if config.get("debug"):
                    raise
            finally:
                if outcome is None:
                    outcome = RuleOutcome.failed("Resource capacity evaluation failed")
                self.cache[frozen] = outcome
        return self.cache[frozen]


def contains_any(elements: tuple[str, ...], test_elements: list[str]) -> bool:
    return any(element in test_elements for element in elements)
