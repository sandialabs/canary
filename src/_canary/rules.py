# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Rules for selecting and filtering ResolvedSpec objects.

This module defines a set of Rule classes used to determine whether a ResolvedSpec should be
included in test execution. Each rule evaluates specific attributes—such as keywords, parameters,
owners, IDs, file prefixes, regular expressions, or resource requirements—and returns a RuleOutcome
object indicating whether the spec passed or failed the rule.

Rules support serialization to and from dictionaries and JSON strings to allow persistence and
reconstruction across sessions.
"""

import importlib
import os
import re
from functools import cached_property
from typing import TYPE_CHECKING
from typing import Any
from typing import Hashable
from typing import Iterable
from typing import Type

from schema import Schema

from . import config
from . import when
from .util import filesystem
from .util import json_helper as json
from .util import logging

if TYPE_CHECKING:
    from .testcase import TestCase
    from .testspec import ResolvedSpec


logger = logging.get_logger(__name__)


class RuleOutcome:
    """Represents the result of evaluating a rule.

    Attributes:
        ok (bool): Whether the rule evaluation succeeded.
        reason (str | None): Optional explanation for a failure.
    """

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
    """Base class for all selection rules.

    Subclasses should override __call__ to evaluate whether a ResolvedSpec satisfies the rule.
    Rules may also define a default_reason explaining why a spec is rejected when the rule fails.
    """

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        raise NotImplementedError

    def __str__(self):
        return f"{self.__class__.__name__}: {self.__dict__}"

    def asdict(self) -> dict[str, Any]:
        """Return a dictionary representation of the rule.

        Returns:
            dict: A mapping containing the parameters required to
            reconstruct the rule.
        """
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, params: dict[str, Any]) -> "Rule":
        """Create a rule instance from serialized parameters.

        Args:
            params: A mapping of constructor parameters.

        Returns:
            Rule: A new rule instance with the given parameters.
        """
        return cls(**params)

    @cached_property
    def default_reason(self) -> str:
        """Return the generic failure reason for the rule.

        Returns:
            str: A human-readable description of why the rule would
            fail if no more specific reason is provided.
        """
        raise NotImplementedError

    def serialize(self) -> str:
        """Return a compact JSON string representing the rule.

        Returns:
            str: Serialized representation of the rule.
        """
        meta = {
            "module": self.__class__.__module__,
            "classname": self.__class__.__name__,
            "params": self.asdict(),
        }
        return json.dumps_min(meta)

    @staticmethod
    def validate(data) -> Any:
        schema = Schema({"module": str, "classname": str, "params": {str: object}})
        return schema.validate(data)

    @staticmethod
    def reconstruct(serialized: str) -> "Rule":
        """Reconstruct a rule from a serialized JSON string.

        Args:
            serialized: JSON string previously produced by serialize().

        Returns:
            Rule: The reconstructed rule instance.
        """
        meta = json.loads(serialized)
        Rule.validate(meta)
        module = importlib.import_module(meta["module"])
        cls: Type[Rule] = getattr(module, meta["classname"])
        if "default_reason" in meta["params"]:
            meta["params"].pop("default_reason")
        rule = cls.from_dict(meta["params"])
        return rule


class KeywordRule(Rule):
    """Selects specs based on keyword expressions.

    A spec passes if all keyword expressions match its explicit or implicit keywords, unless the
    expression list contains '__all__' or ':all:', in which case all specs pass."""

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
    """Selects specs based on parameter expressions.

    The spec passes if the parameter expression matches any of the spec's explicit or implicit
    parameters."""

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
    """Selects specs based on test ID prefixes.

    A spec passes if its ID begins with any of the configured prefixes.
    """

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
    """Selects specs based on declared owners.

    A spec passes if at least one of its owners appears in the rule's
    configured owner set.
    """

    def __init__(self, owners: Iterable[str] = ()) -> None:
        self.owners = set(owners)

    @cached_property
    def default_reason(self) -> str:
        return "not owned by @*{%s}" % ", ".join(self.owners)

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        if self.owners.intersection(spec.owners or []):
            return RuleOutcome(True)
        return RuleOutcome.failed(self.default_reason)


class PrefixRule(Rule):
    """Selects specs based on file path prefixes.

    A spec passes if its underlying file path begins with any of the
    configured prefixes.
    """

    def __init__(self, prefixes: Iterable[str] = ()) -> None:
        self.prefixes = list(prefixes)

    @cached_property
    def default_reason(self) -> str:
        return "test file not a child of %s" % ", ".join(self.prefixes)

    def __call__(self, spec: "ResolvedSpec") -> RuleOutcome:
        if any(str(spec.file).startswith(prefix) for prefix in self.prefixes):
            return RuleOutcome(True)
        return RuleOutcome.failed(f"test file not in any of {', '.join(self.prefixes)}")


class RegexRule(Rule):
    """Selects specs by searching for a regular expression in test files.

    A spec passes if the configured regular expression occurs in the spec's primary file or in any
    referenced asset file.
    """

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


class RuntimeRule:
    """Base class for all runtime selection rules.

    Subclasses should override __call__ to evaluate whether a TestCase satisfies the rule.
    Rules may also define a default_reason explaining why a spec is rejected when the rule fails.
    """

    def __call__(self, case: "TestCase") -> RuleOutcome:
        raise NotImplementedError

    @cached_property
    def default_reason(self) -> str:
        """Return the generic failure reason for the rule.

        Returns:
            str: A human-readable description of why the rule would
            fail if no more specific reason is provided.
        """
        raise NotImplementedError


class ResourceCapacityRule(RuntimeRule):
    """Selects cases based on system resource capacity.

    This rule queries plugin hooks to determine whether the available resource pool can accommodate
    the spec's declared resource needs.  Evaluation results are cached based on the resource set's
    hashable representation.
    """

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

    def __call__(self, case: "TestCase") -> RuleOutcome:
        resource_set = case.required_resources()
        frozen = self.freeze_resource_set(resource_set)
        if frozen not in self.cache:
            outcome: RuleOutcome | None = None
            pm = config.pluginmanager.hook
            try:
                result = pm.canary_resource_pool_accommodates(case=case)
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
