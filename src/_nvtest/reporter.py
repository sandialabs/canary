import argparse
import inspect
import os
import sys
import typing
from abc import ABC
from typing import Any
from typing import Callable
from typing import Generator
from typing import Type

from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.third_party.docstring_parser import parser as docstring_parser
from _nvtest.util import logging


class TestData:
    def __init__(self) -> None:
        self.start: float = sys.maxsize
        self.finish: float = -1
        self.status: int = 0
        self.cases: list["TestCase"] = []

    def __len__(self):
        return len(self.cases)

    def __iter__(self):
        for case in self.cases:
            yield case

    def update_status(self, case: "TestCase") -> None:
        if case.status == "diffed":
            self.status |= 2**1
        elif case.status == "failed":
            self.status |= 2**2
        elif case.status == "timeout":
            self.status |= 2**3
        elif case.status == "skipped":  # notdone
            self.status |= 2**4
        elif case.status == "ready":
            self.status |= 2**5
        elif case.status == "not_run":
            self.status |= 2**6

    def add_test(self, case: "TestCase") -> None:
        if case.start > 0 and case.start < self.start:
            self.start = case.start
        if case.finish > 0 and case.finish > self.finish:
            self.finish = case.finish
        self.update_status(case)
        self.cases.append(case)


class Reporter(ABC):
    REGISTRY: set[Type["Reporter"]] = set()

    def __init_subclass__(cls, **kwargs):
        Reporter.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    def __init__(self, session: "Session | None" = None) -> None:
        self._data: TestData | None = None
        self._session: Session | None = session

    @property
    def data(self) -> TestData:
        if self._data is None:
            self._data = TestData()
            cases_to_run: list["TestCase"] = [c for c in self.session.cases if c.status != "masked"]
            for case in cases_to_run:
                self._data.add_test(case)
        assert self._data is not None
        return self._data

    @property
    def session(self) -> Session:
        if self._session is None:
            with logging.level(logging.WARNING):
                self._session = Session(os.getcwd(), mode="r")
        assert self._session is not None
        return self._session

    @classmethod
    def label(cls) -> str:
        label = cls.__name__
        if label.endswith("Reporter"):
            return label[:-8]
        return label

    @classmethod
    def description(cls) -> str:
        return f"Create {cls.label()} reports"

    def create(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def post(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def execute(self, args: argparse.Namespace) -> None:
        a, kw = self.args_from_namespace(args)
        if args.subcommand == "create":
            self.create(*a, **kw)
        elif args.subcommand == "post":
            self.post(*a, **kw)
        else:
            raise ValueError(f"{args.subcommand}: unknown {self.label()} subcommand")

    @classmethod
    def overrides(cls, methodname: str) -> bool:
        method = getattr(cls, methodname, None)
        base_method = getattr(Reporter, methodname, None)
        if method is not None and base_method is not None:
            return method is not base_method
        return False

    @classmethod
    def setup_parser(cls, parser: Parser) -> None:
        sp = parser.add_subparsers(dest="subcommand", metavar="")
        if cls.overrides("create"):
            p = sp.add_parser("create", help=f"Create {cls.label()} report")
            cls.add_parser_arguments_from_method(p, cls.create)
        if cls.overrides("post"):
            p = sp.add_parser("post", help=f"Post {cls.label()} report")
            cls.add_parser_arguments_from_method(p, cls.post)

    @staticmethod
    def add_parser_arguments_from_method(parser: Parser, method: Callable) -> None:
        method_flags: list[dict[str, Any]] = []
        signature = inspect.signature(method)
        docstring = docstring_parser.parse(method.__doc__ or "")
        descriptions: dict[str, str | None] = {}
        for p in docstring.params:
            descriptions[p.arg_name] = p.description
        for param in signature.parameters.values():
            if param.name == "self":
                continue
            param_flags: dict[str, Any] = {}
            param_flags["dest"] = f"__r_{param.name}"
            param_flags["metavar"] = f"{param.name.upper()}"
            if param.default is param.empty and param.kind == param.POSITIONAL_ONLY:
                param_flags["name_or_flag"] = param.name
            else:
                param_flags["name_or_flag"] = flag_from_name(param.name)
                param_flags["required"] = param.default is param.empty
            type = get_annotation_type(param.annotation)
            if type is bool:
                if param.default is True:
                    param_flags["default"] = True
                    param_flags["action"] = "store_false"
                    param_flags["name_or_flag"] = flag_from_name(f"no_{param.name}")
                elif param.default in (None, False):
                    param_flags["default"] = False
                    param_flags["action"] = "store_true"
            elif param.default is not param.empty:
                param_flags["default"] = param.default
            if param.name in descriptions:
                param_flags["help"] = f"{descriptions[param.name]} [default: %(default)s]"
            else:
                param_flags["help"] = "[default: %(default)s]"
            method_flags.append(param_flags)
        for param_flags in method_flags:
            name_or_flag = param_flags.pop("name_or_flag")
            parser.add_argument(name_or_flag, **param_flags)

    @staticmethod
    def args_from_namespace(namespace):
        args = ()
        kwargs = {}
        for key, value in vars(namespace).items():
            if key.startswith("__r_"):
                kwargs[key[4:]] = value
        return args, kwargs


def get_annotation_type(annotation) -> float | int | bool | None:
    if annotation in (float, int, bool):
        return annotation
    elif typing.get_origin(annotation) is typing.Union:
        args = typing.get_args(annotation)
        if args[0] in (int, float, bool):
            return args[0]
    return None


def flag_from_name(name: str) -> str:
    if len(name) == 1:
        return f"-{name}"
    return f"--{name.replace('_', '-')}"


def reporters() -> Generator[Type[Reporter], None, None]:
    for reporter_class in Reporter.REGISTRY:
        yield reporter_class
