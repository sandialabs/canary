# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import importlib.util
import io
import json
import os
import re
import shlex
import sys
import tokenize
import typing
from functools import wraps
from itertools import repeat
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from typing import ClassVar
from typing import Generator
from typing import Type

from ... import config
from ...config.argparsing import Parser
from ...enums import list_parameter_space
from ...test.case import TestCase
from ...test.case import TestMultiCase
from ...third_party.color import colorize
from ...util import logging
from ...util import scalar
from ...util import string
from ...util.executable import Executable
from ...util.filesystem import force_symlink
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from .pyt import PYTTestGenerator


class VVTTestGenerator(PYTTestGenerator):
    def load(self, file: str | None = None) -> None:
        file = file or self.file
        for arg in p_VVT(file):
            match arg.command:
                case "keywords":
                    self.f_KEYWORDS(arg)
                case "copy" | "link" | "sources":
                    self.f_SOURCES(arg)
                case "preload":
                    self.f_PRELOAD(arg)
                case "parameterize":
                    self.f_PARAMETERIZE(arg)
                case "analyze":
                    self.f_ANALYZE(arg)
                case "name" | "testname":
                    self.f_NAME(arg)
                case "timeout":
                    self.f_TIMEOUT(arg)
                case "skipif":
                    self.f_SKIPIF(arg)
                case "baseline":
                    self.f_BASELINE(arg)
                case "enable":
                    self.f_ENABLE(arg)
                case "depends_on":
                    self.f_DEPENDS_ON(arg)
                case "include" | "insert_directive_file":
                    raise VVTParseError(
                        f"{arg.command}: include file should have already been included!", arg
                    )
                case _:
                    raise VVTParseError(f"Unknown command: {arg.command}", arg)

    @classmethod
    def matches(cls, path: str) -> bool:
        return path.endswith(".vvt")

    def f_KEYWORDS(self, arg: SimpleNamespace) -> None:
        """# VVT : keywords [:=] word1 word2 ... wordn"""
        assert arg.command == "keywords"
        self.m_keywords(*arg.argument.split(), when=arg.when)

    def f_SOURCES(self, arg: SimpleNamespace) -> None:
        """#VVT : (link|copy|sources) ( OPTIONS ) [:=] file1 file2 ..
        | (link|copy|sources) (rename) [:=] file1,file2 file3,file4 ...
        """
        assert arg.command in ("copy", "link", "sources")
        fun = {"copy": self.m_copy, "link": self.m_link, "sources": self.m_sources}[arg.command]
        kwds = dict(arg.options or {})
        if "rename" in kwds:
            kwds.pop("rename")
            file_pairs = make_table(arg.argument)
            for file_pair in file_pairs:
                if len(file_pair) != 2:
                    raise VVTParseError(
                        f"invalid rename option: {arg.line!r}.  rename requires src,dst file pairs",
                        arg,
                    )
                fun(src=file_pair[0], dst=file_pair[1], when=arg.when, **kwds)  # type: ignore
        else:
            files = arg.argument.split()
            fun(*files, when=arg.when, **kwds)  # type: ignore

    def f_PRELOAD(self, arg: SimpleNamespace) -> None:
        assert arg.command == "preload"
        options = dict(arg.options)
        self.m_preload(arg.argument, when=arg.when, **options)  # type: ignore

    def f_PARAMETERIZE(self, arg: SimpleNamespace) -> None:
        names, values, kwds, deps = p_PARAMETERIZE(arg)
        if deps:
            # construct a dependency for each case in values
            assert len(deps) == len(values)
            for i, dep in enumerate(deps):
                if dep is None:
                    continue
                # when expression ensures that dependencies added below are assigned to the ith
                # test case
                if isinstance(dep, str):
                    self.m_depends_on(dep, when=arg.when)
                else:
                    assert isinstance(dep, dict)
                    for dep_name, dep_params in dep.items():
                        p = ".".join(f"{k}={dep_params[k]}" for k in sorted(dep_params))
                        self.m_depends_on(f"{dep_name}.{p}", when=arg.when)
        self.m_parameterize(list(names), values, when=arg.when, **kwds)

    def f_ANALYZE(self, arg: SimpleNamespace) -> None:
        """# VVT: analyze ( OPTIONS ) [:=] --FLAG
        | analyze ( OPTIONS ) [:=] FILE
        """
        options = dict(arg.options)
        if arg.argument:
            key = "flag" if arg.argument.startswith("-") else "script"
            options[key] = arg.argument
        self.m_generate_composite_base_case(when=arg.when, **options)

    def f_TIMEOUT(self, arg: SimpleNamespace) -> None:
        """# VVT: timeout ( OPTIONS ) [:=] SECONDS"""
        try:
            seconds = to_seconds(arg.argument)
        except InvalidTimeFormat:
            raise VVTParseError(f"invalid time format: {arg.line!r}", arg) from None
        self.m_timeout(seconds, when=arg.when)

    def f_SKIPIF(self, arg: SimpleNamespace) -> None:
        """# VVT: skipif ( reason=STRING ) [:=] BOOL_EXPR"""
        skip, reason = p_SKIPIF(arg)
        self.m_skipif(skip, reason=reason)

    def f_BASELINE(self, arg: SimpleNamespace) -> None:
        """# VVT: baseline ( OPTIONS ) [:=] --FLAG
        | baseline ( OPTIONS ) [:=] file1,file2 file3,file4 ...
        """
        file_pairs = make_table(arg.argument)
        options = dict(arg.options)
        for file_pair in file_pairs:
            if len(file_pair) == 1 and file_pair[0].startswith("--"):
                self.m_baseline(when=arg.when, flag=file_pair[0], **options)
            elif len(file_pair) != 2:
                raise VVTParseError(f"invalid baseline command: {arg.line!r}", arg)
            else:
                self.m_baseline(file_pair[0], file_pair[1], when=arg.when, **options)

    def f_ENABLE(self, arg: SimpleNamespace) -> None:
        """# VVT: enable ( OPTIONS ) [:=] BOOL"""
        if arg.argument and arg.argument.lower() == "true":
            arg.argument = True
        elif arg.argument and arg.argument.lower() == "false":
            arg.argument = False
        elif arg.argument is None:
            arg.argument = True
        options = dict(arg.options)
        # if options.get("platforms") == "":
        #    options["platforms"] = "__"
        self.m_enable(arg.argument, when=arg.when, **options)

    def f_NAME(self, arg: SimpleNamespace) -> None:
        """# VVT: name ( OPTIONS ) [:=] NAME"""
        self.m_name(arg.argument.strip())

    def f_DEPENDS_ON(self, arg: SimpleNamespace) -> None:
        """# VVT: depends on ( OPTIONS ) [:=] STRING"""
        options = dict(arg.options)
        if "expect" in options:
            try:
                options["expect"] = int(options["expect"])
            except ValueError:
                pass
        if "result" in options:
            options["result"] = re.sub(r"(?i)\bpass\b", "success", options["result"])
            options["result"] = re.sub(r"(?i)\bdiff\b", "diffed", options["result"])
            options["result"] = re.sub(r"(?i)\bfail\b", "failed", options["result"])
            options["result"] = re.sub(r"(?i)\bskip\b", "skipped", options["result"])
        self.m_depends_on(arg.argument, when=arg.when, **options)


def csplit(text: str) -> list[Any]:
    # first remove any space around ``,`` so that we can split on white space
    s = re.sub(r"\s*,\s*", ",", text)
    groups = s.split()
    return [[string.strip_quotes(entry.strip()) for entry in group.split(",")] for group in groups]


@dataclasses.dataclass
class TableToken:
    line: str
    string: str
    type: str
    NC: ClassVar[str] = "==NC=="
    NR: ClassVar[str] = "==NR=="
    WORD: ClassVar[str] = "==WORD=="


def popnext(arg: list[str]) -> str:
    single_quote = "'"
    double_quote = '"'
    word = arg.pop(0)
    if word in (single_quote, double_quote):
        while True:
            try:
                word += arg.pop(0)
            except StopIteration:
                raise SyntaxError(f"{word!r}: no matching {word[0]} found")
            if word[0] == word[-1]:
                break
    return word


def tokenize_table_text(table_text: str) -> Generator[TableToken, None, None]:
    """Split text into a table.  Each row begins with a space and columns within the row are
    separated by a comma.

    .. code-block:: console

       a,b,c  d,e,f -> [[a, b, c], [d, e, f]]

    The splitting is complicated by accomodating spaces around the comma:

    .. code-block:: console

       a , b,   c  d   ,e  ,  f -> [[a, b, c], [d, e, f]]

    The following will also split properly:

    .. code-block:: console

       a , "b , 0",   c  d   ,e  ,  f !-> [[a, 'b , 0', c], [d, e, f]]

    """
    chars: list[str] = list(table_text.strip())
    prev: str = ""
    word: str = ""
    while True:
        try:
            char = popnext(chars)
        except IndexError:
            yield TableToken(table_text, word, TableToken.WORD)
            return
        if char == COMMA:
            yield TableToken(table_text, word, TableToken.WORD)
            yield TableToken(table_text, char, TableToken.NC)
            prev, word = TableToken.NC, ""
        elif char == SPACE:
            # compress spaces
            while char == SPACE:
                char = popnext(chars)
            if prev == TableToken.NC:
                prev, word = "", char
            elif char != COMMA:
                yield TableToken(table_text, word, TableToken.WORD)
                yield TableToken(table_text, SPACE, TableToken.NR)
                prev, word = TableToken.NR, char
            else:
                yield TableToken(table_text, word, TableToken.WORD)
                yield TableToken(table_text, ",", TableToken.NC)
                prev, word = TableToken.NC, ""
        else:
            word += char
            prev = ""


def make_table(text: str) -> list[list[str]]:
    table: list[list[str]] = []
    row: list[str] = []
    for token in tokenize_table_text(text):
        if token.type == TableToken.NR:
            table.append(row)
            row = []
        elif token.type == TableToken.WORD:
            row.append(token.string)
    if row:
        table.append(row)
    return table


non_code_token_nums = [
    getattr(tokenize, _)
    for _ in ("NL", "NEWLINE", "INDENT", "DEDENT", "ENCODING", "STRING", "COMMENT")
]

LPAREN = "("
RPAREN = ")"
COMMA = ","
COLON = ":"
EQUAL = "="
SPACE = " "


def p_GEN_PARAMETERIZE(arg: SimpleNamespace) -> tuple[list, list, dict, list | None]:
    """# VVT: parameterize ( OPTIONS,generator ) [:=] script [--options]"""
    script, *opts = shlex.split(arg.argument)
    if script in ("python", "python3"):
        script = sys.executable
    with working_dir("." if arg.file == "<string>" else os.path.dirname(arg.file)):
        exe = Executable(script)
        result = exe(*opts, stdout=str)
    output = [json.loads(_.strip()) for _ in result.get_output().splitlines() if _.split()]
    names = list(output[0][0].keys())
    values = []
    for params in output[0]:
        values.append([params[name] for name in names])
    kwds: dict[str, Any] = {}
    kwds["type"] = list_parameter_space
    for opt, value in arg.options:
        if opt in ("autotype", "int", "float", "str"):
            logging.warning(f"skipping parameter type {opt!r} -- type deduced by json generation")
        else:
            kwds[opt] = value
    assert kwds.pop("generator", None) is not None
    deps: list | None = None
    if len(output) == 2:
        deps = output[1]
        assert isinstance(deps, list)
        if len(deps) != len(values):
            raise VVTParseError("number of deps must equal number of parameterizations", arg)
    return names, values, kwds, deps


def p_PARAMETERIZE(arg: SimpleNamespace) -> tuple[list, list, dict, list | None]:
    """# VVT: parameterize ( OPTIONS ) [:=] names_spec = values_spec

    names_spec: name1,name2,...
    values_spec: val1_1,val2_1,... val1_2,val2_2,... ...

    """
    if "generator" in [opt[0] for opt in arg.options]:
        return p_GEN_PARAMETERIZE(arg)

    names_spec, values_spec = arg.argument.split("=", 1)
    names = [_.strip() for _ in names_spec.split(",") if _.split()]
    types: list[str] = []
    kwds: dict[str, Any] = {}
    kwds["type"] = list_parameter_space
    for opt, value in arg.options:
        if opt in ("autotype", "int", "float", "str"):
            assert value is True
            types.append(opt)
        else:
            kwds[opt] = value
    if not types:
        types = list(repeat("str", len(names)))
    elif len(types) == 1:
        types = list(repeat(types[0], len(names)))
    elif len(types) != len(names):
        raise VVTParseError(f"incorrect number of parameter types: {arg.line!r}", arg)
    for i, name in enumerate(names):
        if name in ("np", "ndevice", "nnode"):
            types[i] = "int"
    values = []
    table = make_table(values_spec)
    for row in table:
        if len(row) != len(names):
            raise VVTParseError(f"invalid parameterize command: {arg.line!r}", arg)
        values.append([scalar.cast(row[i], type) for i, type in enumerate(types)])
    return names, values, kwds, None


def p_LINE(file: Path | str, line: str) -> SimpleNamespace | None:
    """COMMAND ( OPTIONS ) [:=] ARGS"""
    if not line.split():
        return None
    filename = str(file if os.path.exists(file) else "<string>")
    tokens = string.get_tokens(line)
    cmd_stack = []
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        if token.type == tokenize.OP:
            break
        cmd_stack.append(token.string.strip())
    command = "_".join(cmd_stack)

    # Look for option block and parse it
    options = []
    filter_opts = {}
    if (token.type, token.string) == (tokenize.OP, LPAREN):
        # Entering an option block, look for closing paren and parse everything in between
        level, option_tokens = 1, []
        for token in tokens:
            if (token.type, token.string) == (tokenize.OP, RPAREN):
                level -= 1
                if not level:
                    break
            elif (token.type, token.string) == (tokenize.OP, LPAREN):
                level += 1
            option_tokens.append(token)
        else:
            msg = "failed to find end of options in {0} at line {1} of {2}"
            raise ParseError(msg.format(line, token.start[0], filename))
        f_opts = p_OPTIONS(filename, option_tokens)
        for opt, val in f_opts:
            if opt in ("testname", "parameters", "options", "platforms"):
                filter_opts[opt] = val
            else:
                options.append((opt, val))
        token = next(tokens)

    when = make_when_expr(filter_opts)

    # Everything left over is the args
    args = None
    if token.type != tokenize.NEWLINE:
        if token.type != tokenize.OP and token.string not in (EQUAL, COLON):
            msg = "failed to determine start of arguments in {0} at line {1} of {2}"
            raise ParseError(msg.format(line, token.start[0], filename))
        end = token.end[-1]
        args = line[end:].strip()

    return SimpleNamespace(
        file=filename,
        command=command,
        when=when,
        options=options,
        argument=args,
        line=line,
        line_no=token.start[0],
    )


def p_VVT(filename: Path | str) -> Generator[SimpleNamespace, None, None]:
    """# VVT: COMMAND ( OPTIONS ) [:=] ARGS"""
    lines, line_no = find_vvt_lines(filename)
    for line in lines:
        ns = p_LINE(filename, line)
        if ns and ns.command in ("include", "insert_directive_file"):
            inc_file = ns.argument.strip()
            if not os.path.exists(inc_file) and not os.path.isabs(inc_file):
                inc_file = os.path.join(os.path.dirname(filename), inc_file)
            if not os.path.exists(inc_file):
                raise VVTParseError(f"include file does not exist: {inc_file!r}", ns)
            for i_ns in p_VVT(inc_file):
                i_ns.when = combine_when_exprs(i_ns.when, ns.when)
                yield i_ns
        elif ns:
            yield ns


def combine_when_exprs(when1: dict[str, str], when2: dict[str, str]) -> dict[str, str]:
    if not when1 and not when2:
        return {}
    elif when1 and not when2:
        return when1
    elif when2 and not when1:
        return when2
    else:
        when_expr: dict[str, str] = {}
        keys = set(when1) | set(when2)
        for key in keys:
            exprs = [when1.get(key), when2.get(key)]
            when_expr[key] = " and ".join([_ for _ in exprs if _])
        return when_expr


def make_when_expr(options: dict) -> dict[str, str]:
    when_expr: dict[str, str] = {}
    wildcards = "*?=><!"
    for key, value in options.items():
        if key in ("testname", "parameters", "options", "platforms"):
            if len(value.split()) > 1 or any([_ in value for _ in wildcards]):
                when_expr[key] = repr(value)
            else:
                when_expr[key] = value
    return when_expr


def find_vvt_lines(filename: Path | str) -> tuple[list[str], int]:
    """Find all lines starting with ``#VVT: COMMAND``, or continuations ``#VVT::``"""
    tokens: Generator[tokenize.TokenInfo, None, None]
    if os.path.exists(filename):
        tokens = tokenize.tokenize(open(filename, "rb").readline)
    else:
        # assume ``filename`` is a string containing directives
        tokens = string.get_tokens(filename)
    s = io.StringIO()
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        elif token.type == tokenize.COMMENT:
            match = re.search(r"^\s*#\s*VVT\s*:\s*:", token.line)
            if match:
                s.write(f" {token.line[match.end() :].rstrip()}")
                continue
            match = re.search(r"^\s*#\s*VVT\s*:(?!(\s*:))", token.line)
            if match:
                s.write(f"\n{token.line[match.end() :].strip()}")
                continue
        elif token.type not in non_code_token_nums:
            break
    lines = s.getvalue().strip().split("\n")
    return lines, token.start[0]


def p_OPTION(filename: str, tokens: list[tokenize.TokenInfo]) -> tuple[str, Any]:
    """OPTION : NAME [true]
    | NAME EQUAL VALUE
    """

    def swap_alias(alias):
        if alias in ("option", "platform", "parameter"):
            return alias + "s"
        return alias

    token = tokens[0]
    if token.type != tokenize.NAME:
        raise ParseError(f"Error parsing token {token!r} in {filename}")
    name = token.string
    if len(tokens) == 1:
        return swap_alias(name), True
    token = tokens[1]
    if token.type == tokenize.NEWLINE:
        return swap_alias(name), True
    if (token.type, token.string) != (tokenize.OP, EQUAL):
        raise ParseError(f"Error parsing token {token!r} in {filename}")
    value = ""
    for token in tokens[2:]:
        if token.type == tokenize.NEWLINE:
            break
        value += f" {token.string}"
    return swap_alias(name), string.strip_quotes(value.strip())


def p_OPTIONS(filename: str, tokens: list[tokenize.TokenInfo]) -> list[tuple[str, Any]]:
    """OPTIONS : OPTION COMMA OPTION ..."""
    options: list[tuple[str, Any]] = []
    opt_tokens: list[tokenize.TokenInfo] = []
    for token in tokens:
        if (token.type, token.string) == (tokenize.OP, COMMA):
            options.append(p_OPTION(filename, opt_tokens))
            opt_tokens = []
        else:
            opt_tokens.append(token)
    if opt_tokens:
        options.append(p_OPTION(filename, opt_tokens))
    return options


def importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def safe_eval(expression: str) -> Any:
    globals = {"os": os, "sys": sys, "importable": importable}
    return eval(expression, globals, {})


def cached(func):
    cache = {}

    @wraps(func)
    def inner(arg, *args, **kwargs):
        expression = arg.argument
        if expression not in cache:
            cache[expression] = func(arg, *args, **kwargs)
        return cache[expression]

    return inner


def evaluate_boolean_expression(expression: str) -> bool | None:
    try:
        result = safe_eval(expression)
    except Exception:
        return None
    return bool(result)


@cached
def p_SKIPIF(arg: SimpleNamespace) -> tuple[bool, str]:
    expression = arg.argument
    options = dict(arg.options)
    reason = str(options.get("reason") or "")
    skip = evaluate_boolean_expression(expression)
    if skip is None:
        raise VVTParseError(f"failed to evaluate the expression {expression!r}", arg)
    if not skip:
        return False, ""
    if not reason:
        reason = colorize("skipif expression @*b{%s} evaluating to @*g{True}" % expression)
    return True, reason


def unique(sequence: list[str]) -> list[str]:
    result = []
    for item in sequence:
        if item not in result:
            result.append(item)
    return result


def to_seconds(arg: str | int | float, round: bool = False, negatives: bool = False) -> int | float:
    if isinstance(arg, (int, float)):
        return arg
    units = {
        "second": 1,
        "minute": 60,  # 60 sec/min * 1 min
        "hour": 3600,  # 60 min/hr * 60 sec/min * 1hr
        "day": 86400,  # 24 hr/day * 60 min/hr * 60 sec/min * 1 day
        "month": 2592000,  # 30 day/mo 24 hr/day * 60 min/hr * 60 sec/min * 1 mo
        "year": 31536000,  # 365 day/yr * 30 day/mo * 24 hr/day * 60 min/hr * 60 sec/min * 1 year
    }
    units["s"] = units["sec"] = units["secs"] = units["seconds"] = units["second"]
    units["m"] = units["min"] = units["mins"] = units["minutes"] = units["minute"]
    units["h"] = units["hr"] = units["hrs"] = units["hours"] = units["hour"]
    units["d"] = units["days"] = units["day"]
    units["mo"] = units["mos"] = units["months"] = units["month"]
    units["y"] = units["yr"] = units["yrs"] = units["years"] = units["year"]

    if re.search(r"^\d{1,2}:\d{1,2}:\d{1,2}(\.\d+)?$", arg):
        hours, minutes, seconds = [float(_) for _ in arg.split(":")]
        return hours * units["hours"] + minutes * units["minutes"] + seconds * units["seconds"]
    elif re.search(r"^\d{1,2}:\d{1,2}(\.\d+)?$", arg):
        minutes, seconds = [float(_) for _ in arg.split(":")]
        return minutes * units["minutes"] + seconds * units["seconds"]

    tokens = [
        token
        for token in tokenize.tokenize(io.BytesIO(arg.encode("utf-8")).readline)
        if token.type not in (tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.ENCODING)
    ]
    stack = []
    for token in tokens:
        if token.type == tokenize.OP and token.string == "-":
            stack.append(-1.0)
        elif token.type == tokenize.NUMBER:
            number = float(token.string)
            if stack and stack[-1] == -1.0:
                stack[-1] *= number
            else:
                stack.append(number)
        elif token.type == tokenize.NAME:
            if token.string.lower() in ("and", "plus"):
                continue
            fac = units.get(token.string.lower())
            if fac is None:
                raise InvalidTimeFormat(arg)
            if not stack:
                stack.append(1)
            stack[-1] *= fac
        elif token.type == tokenize.OP and token.string in (".",):
            continue
        else:
            raise InvalidTimeFormat(arg)
    seconds = sum(stack)
    if seconds < 0 and not negatives:
        raise InvalidTimeFormat(f"negative seconds from {arg!r}")
    if round:
        return int(seconds)
    return seconds


@typing.no_type_check
def get_vvtest_attrs(case: "TestCase") -> dict:
    attrs = {}
    compiler_spec = None
    if config.build.compiler.vendor is not None:
        vendor = config.build.compiler.vendor
        version = config.build.compiler.version
        compiler_spec = f"{vendor}@{version}"
    attrs["CASEID"] = case.id
    attrs["NAME"] = case.family
    attrs["TESTID"] = case.fullname
    attrs["PLATFORM"] = sys.platform.lower()
    attrs["COMPILER"] = compiler_spec or "UNKNOWN@UNKNOWN"
    attrs["TESTROOT"] = case.work_tree
    attrs["VVTESTSRC"] = ""
    attrs["PROJECT"] = ""
    attrs["OPTIONS"] = config.getoption("on_options") or []
    attrs["OPTIONS_OFF"] = config.getoption("off_options") or []
    attrs["SRCDIR"] = case.file_dir
    attrs["TIMEOUT"] = case.timeout
    attrs["KEYWORDS"] = case.keywords
    attrs["diff_exit_status"] = 64
    attrs["skip_exit_status"] = 63

    # tjfulle: the vvtest_util.opt_analyze and vvtest_util.is_analysis_only attributes seem to
    # always be the same to me.  so far as I can tell, if you set -a/--analyze on the command line
    # the runtime config 'analyze' is set to True.  When vvtest writes out vvtest_util.py it writes
    #   - ``vvtest_util.is_analysis_only = rtconfig.getAttr("analyze")``; and
    #   - ``vvtest_util.opt_analyze = '--execute-analysis-sections' in sys.argv[1:].
    # ``--execute-analysis-sections`` is a appended to a test script's command line if
    # rtconfig.getAttr("analyze") is True.  Thus, it seems that there is no differenece between
    # ``opt_analyze`` and ``is_analysis_only``.  In canary, --execute-analysis-sections is added
    # to the command if canary_testcase_modify below
    analyze_check = "'--execute-analysis-sections' in sys.argv[1:]"
    attrs["opt_analyze"] = attrs["is_analysis_only"] = analyze_check

    attrs["is_analyze"] = isinstance(case, TestMultiCase)
    attrs["is_baseline"] = config.getoption("command") == "rebaseline"
    attrs["PARAM_DICT"] = case.parameters or {}
    for key, val in case.parameters.items():
        attrs[key] = val
    if isinstance(case, TestMultiCase):
        for paramset in case.paramsets:
            key = "_".join(paramset.keys)
            table = attrs.setdefault(f"PARAM_{key}", [])
            for row in paramset.values:
                if len(paramset.keys) == 1:
                    table.append(row[0])
                else:
                    table.append(list(row))

    # DEPDIRS and DEPDIRMAP should always exist.
    attrs["DEPDIRS"] = [dep.working_directory for dep in getattr(case, "dependencies", [])]
    attrs["DEPDIRMAP"] = {}  # FIXME

    attrs["exec_dir"] = case.working_directory
    attrs["exec_root"] = case.work_tree
    attrs["exec_path"] = case.path
    attrs["file_root"] = case.file_root
    attrs["file_dir"] = case.file_dir
    attrs["file_path"] = case.file_path

    attrs["RESOURCE_np"] = case.cpus
    attrs["RESOURCE_IDS_np"] = [int(_) for _ in case.cpu_ids]
    attrs["RESOURCE_ndevice"] = case.gpus
    attrs["RESOURCE_IDS_ndevice"] = [int(_) for _ in case.gpu_ids]

    return attrs


def write_vvtest_util(case: "TestCase", stage: str = "run") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    attrs = get_vvtest_attrs(case)
    file = os.path.abspath("./vvtest_util.py")
    if os.path.dirname(file) != case.working_directory:
        raise ValueError("Incorrect directory for writing vvtest_util")
    with open(file, "w") as fh:
        fh.write("import os\n")
        fh.write("import sys\n")
        for key, value in attrs.items():
            if isinstance(value, bool):
                fh.write(f"{key} = {value!r}\n")
            elif value is None:
                fh.write(f"{key} = None\n")
            elif isinstance(value, str) and "in sys.argv" in value:
                fh.write(f"{key} = {value}\n")
            else:
                fh.write(f"{key} = {json.dumps(value, indent=4)}\n")


class ParseError(Exception):
    pass


class VVTParseError(Exception):
    def __init__(self, err, arg):
        message = f"{arg.file}:{arg.line_no}:\nerror: {err}"
        super().__init__(message)


class InvalidTimeFormat(Exception):
    def __init__(self, fmt):
        super().__init__(f"invalid time format: {fmt!r}")


@hookimpl
def canary_testcase_generator() -> Type[VVTTestGenerator]:
    return VVTTestGenerator


@hookimpl
def canary_testcase_setup(case: "TestCase", stage: str = "run") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    write_vvtest_util(case)
    f = os.path.join(case.working_directory, "execute.log")
    force_symlink(case.logfile(stage), f)


@hookimpl
def canary_testcase_finish(case: "TestCase") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    f = os.path.join(case.working_directory, "execute.log")
    force_symlink(case.logfile(), f)


class RerunAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        keywords = getattr(args, "keyword_exprs", None) or []
        keywords.append(":all:")
        setattr(args, "keyword_exprs", keywords)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "-R",
        action=RerunAction,
        nargs=0,
        command="run",
        group="vvtest options",
        dest="vvtest_runall",
        help="Rerun tests. Normally tests are not run if they previously completed.",
    )
    parser.add_argument(
        "-a",
        "--analyze",
        action="store_true",
        default=None,
        command="run",
        group="vvtest options",
        dest="vvtest_analyze",
        help="Only run the analysis sections of each test. Note that a test must be written to "
        "support this option (using the vvtest_util.is_analysis_only flag) otherwise the whole "
        "test is run.",
    )


@hookimpl
def canary_testcase_modify(case: "TestCase") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    if config.getoption("vvtest_analyze"):
        if config.session.level and "--execute-analysis-sections" not in case.postflags:
            case.postflags.append("--execute-analysis-sections")
