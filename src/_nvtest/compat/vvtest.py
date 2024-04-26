import importlib
import io
import json
import os
import re
import sys
import tokenize
import typing
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Generator
from typing import Union

from .. import config
from ..directives.enums import list_parameter_space
from ..third_party.color import colorize
from ..util.time import to_seconds

if TYPE_CHECKING:
    from ..test.case import TestCase
    from ..test.file import AbstractTestFile


non_code_token_nums = [
    getattr(tokenize, _)
    for _ in ("NL", "NEWLINE", "INDENT", "DEDENT", "ENCODING", "STRING", "COMMENT")
]

LPAREN = "("
RPAREN = ")"
COMMA = ","
COLON = ":"
EQUAL = "="


def load_vvt(file: "AbstractTestFile") -> None:
    try:
        args, _ = p_VVT(file.file)
    except ParseError as e:
        raise ValueError(f"Failed to parse {file.file} at command {e.args[0]}") from None
    for arg in args:
        if arg.command == "keywords":
            f_KEYWORDS(file, arg)
        elif arg.command in ("copy", "link", "sources"):
            f_SOURCES(file, arg)
        elif arg.command == "preload":
            f_PRELOAD(file, arg)
        elif arg.command == "parameterize":
            f_PARAMETERIZE(file, arg)
        elif arg.command == "analyze":
            f_ANALYZE(file, arg)
        elif arg.command in ("name", "testname"):
            f_NAME(file, arg)
        elif arg.command == "timeout":
            f_TIMEOUT(file, arg)
        elif arg.command == "skipif":
            f_SKIPIF(file, arg)
        elif arg.command == "baseline":
            f_BASELINE(file, arg)
        elif arg.command == "enable":
            f_ENABLE(file, arg)
        elif arg.command == "depends_on":
            f_DEPENDS_ON(file, arg)
        else:
            raise ValueError(f"Unknown command: {arg.command} at {arg.line_no}:{arg.line}")


def p_LINE(line: str) -> SimpleNamespace:
    """#VVT: COMMAND ( OPTIONS ) [:=] ARGS"""
    tokens = get_tokens(line)
    cmd_stack = []
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        if token.type == tokenize.OP:
            break
        cmd_stack.append(token.string.strip())
    command = "_".join(cmd_stack)
    options = None
    if (token.type, token.string) == (tokenize.OP, LPAREN):
        options = p_OPTIONS(tokens)
        token = next(tokens)
    args = None
    if token.type != tokenize.NEWLINE:
        if token.type != tokenize.OP and token.string not in (EQUAL, COLON):
            raise ParseError(f"Failed to parse {line}")
        end = token.end[-1]
        args = line[end:].strip()
    options = options or {}
    when = make_when_expr(options)
    return SimpleNamespace(
        command=command,
        when=when,
        options=options,
        argument=args,
        line=line,
        line_no=token.start[0],
    )


def p_VVT(filename: Union[Path, str]) -> tuple[list[SimpleNamespace], int]:
    commands: list[SimpleNamespace] = []
    lines, line_no = find_vvt_lines(filename)
    for line in lines:
        ns = p_LINE(line)
        commands.append(ns)
    return commands, line_no


def get_tokens(path):
    return tokenize.tokenize(io.BytesIO(path.encode("utf-8")).readline)


def make_when_expr(options):
    when_expr = io.StringIO()
    wildcards = "*?=><!"
    for key in list(options.keys()):
        if key in ("testname", "parameters", "options", "platforms"):
            value = options.pop(key)
            when_expr.write(f"{key}=")
            if len(value.split()) > 1 or any([_ in value for _ in wildcards]):
                when_expr.write(f"{value!r} ")
            else:
                when_expr.write(f"{value} ")
    return when_expr.getvalue().strip()


def find_vvt_lines(filename: Union[Path, str]) -> tuple[list[str], int]:
    """Find all lines starting with #VVT: COMMAND, or continuations #VVT::"""
    tokens = tokenize.tokenize(open(filename, "rb").readline)
    s = io.StringIO()
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        elif token.type == tokenize.COMMENT:
            match = re.search("^#\s*VVT:\s*:", token.line)
            if match:
                s.write(f" {token.line[match.end():].rstrip()}")
                continue
            match = re.search("^#\s*VVT:(?!(\s*:))", token.line)
            if match:
                s.write(f"\n{token.line[match.end():].strip()}")
                continue
        elif token.type not in non_code_token_nums:
            break
    lines = s.getvalue().strip().split("\n")
    return lines, token.start[0]


def strip_quotes(arg: str) -> str:
    s_quote, d_quote = "'''", '"""'
    tokens = get_tokens(arg)
    token = next(tokens)
    while token.type == tokenize.ENCODING:
        token = next(tokens)
    s = token.string
    if token.type == tokenize.STRING:
        if s.startswith((s_quote, d_quote)):
            return s[3:-3]
        return s[1:-1]
    return arg


def p_OPTION(string: str) -> tuple[str, object]:
    tokens = get_tokens(string)
    token = next(tokens)
    while token.type == tokenize.ENCODING:
        token = next(tokens)
    if token.type != tokenize.NAME:
        raise ParseError(string)
    name = token.string
    token = next(tokens)
    if token.type == tokenize.NEWLINE:
        return name, True
    if (token.type, token.string) != (tokenize.OP, EQUAL):
        raise ParseError(token)
    value = ""
    for token in tokens:
        if token.type == tokenize.NEWLINE:
            break
        value += f" {token.string}"
    return name, strip_quotes(value.strip())


def p_OPTIONS(
    tokens: Generator[tokenize.TokenInfo, None, None],
) -> dict[str, object]:
    i = 0
    stack = [i]
    s_opt = ""
    u_options: list[tuple[str, object]] = []
    for token in tokens:
        i += 1
        if (token.type, token.string) == (tokenize.OP, LPAREN):
            stack.append(i)
        elif (token.type, token.string) == (tokenize.OP, RPAREN):
            if not stack:
                raise IndexError(f"No matching closing parens at {i}")
            stack.pop()
        if not stack:
            break
        if (token.type, token.string) == (tokenize.OP, COMMA):
            option = p_OPTION(s_opt.strip())
            u_options.append(option)
            s_opt = ""
        else:
            s_opt += f" {token.string}"
    u_options.append(p_OPTION(s_opt.strip()))
    if stack:
        raise IndexError(f"No matching opening parens at: {stack.pop()}")
    if (token.type, token.string) != (tokenize.OP, RPAREN):
        raise ParseError(token)
    options = dict(u_options)
    for name in ("option", "platform", "parameter"):
        if name in options:
            options[f"{name}s"] = options.pop(name)
    return options


def f_KEYWORDS(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "keywords"
    file.m_keywords(*arg.argument.split(), when=arg.when)


def f_SOURCES(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command in ("copy", "link", "sources")
    fun = {"copy": file.m_copy, "link": file.m_link, "sources": file.m_sources}[arg.command]
    if arg.options and arg.options.get("rename"):
        s = re.sub(",\s*", ",", arg.argument)
        file_pairs = [_.split(",") for _ in s.split()]
        for file_pair in file_pairs:
            assert len(file_pair) == 2
            fun(*file_pair, when=arg.when, **arg.options)  # type: ignore
    else:
        files = arg.argument.split()
        fun(*files, when=arg.when, **arg.options)  # type: ignore


def f_PRELOAD(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "preload"
    parts = arg.argument.split()
    if parts[0] == "source-script":
        arg.argument = parts[1]
        arg.options["source"] = True
    file.m_preload(arg.argument, when=arg.when, **arg.options)  # type: ignore


def f_PARAMETERIZE(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    names, values, kwds = p_PARAMETERIZE(file, arg)
    file.m_parameterize(list(names), values, when=arg.when, **kwds)


def p_PARAMETERIZE(file: "AbstractTestFile", arg: SimpleNamespace) -> tuple[list, list, dict]:
    part1, part2 = arg.argument.split("=", 1)
    part2 = re.sub(",\s*", ",", part2)
    names = [_.strip() for _ in part1.split(",") if _.split()]
    values = []
    for group in part2.split():
        row = [loads(_) for _ in group.split(",") if _.split()]
        values.append(row)
    if not all(len(values[0]) == len(_) for _ in values[1:]):
        raise ValueError(
            f"{file.file}: invalid parameterize command at {arg.line_no}:{arg.line!r}"
        )
    kwds = dict(arg.options)
    for key in ("autotype", "int", "float", "str"):
        kwds.pop(key, None)
    kwds["type"] = list_parameter_space
    return names, values, kwds


def f_ANALYZE(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    options = dict(arg.options)
    if arg.argument:
        key = "flag" if arg.argument.startswith("-") else "script"
        options[key] = arg.argument
    file.m_analyze(when=arg.when, **options)


def f_TIMEOUT(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    seconds = to_seconds(arg.argument)
    file.m_timeout(seconds, when=arg.when)


def f_SKIPIF(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    skip, reason = p_SKIPIF(arg.argument, reason=arg.options.get("reason"))
    file.m_skipif(skip, reason=reason)


def f_BASELINE(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    argument = re.sub(",\s*", ",", arg.argument)
    file_pairs = [_.split(",") for _ in argument.split()]
    for file_pair in file_pairs:
        if len(file_pair) == 1 and file_pair[0].startswith("--"):
            file.m_baseline(when=arg.when, flag=file_pair[0], **arg.options)
        elif len(file_pair) != 2:
            raise ValueError(f"{file.file}: invalid baseline command at {arg.line!r}")
        else:
            file.m_baseline(file_pair[0], file_pair[1], when=arg.when, **arg.options)


def f_ENABLE(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    if arg.argument and arg.argument.lower() == "true":
        arg.argument = True
    elif arg.argument and arg.argument.lower() == "false":
        arg.argument = False
    elif arg.argument is None:
        arg.argument = True
    # if arg.options.get("platforms") == "":
    #    arg.options["platforms"] = "__"
    file.m_enable(arg.argument, when=arg.when, **arg.options)


def f_NAME(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    file.m_name(arg.argument.strip())


def f_DEPENDS_ON(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    if "expect" in arg.options:
        arg.options["expect"] = int(arg.options["expect"])
    file.m_depends_on(arg.argument.strip(), when=arg.when, **arg.options)


def importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def loads(arg: str) -> Union[int, float, str]:
    try:
        return int(arg)
    except ValueError:
        pass
    try:
        return float(arg)
    except ValueError:
        pass
    return arg


def safe_eval(expression: str) -> object:
    globals = {"os": os, "sys": sys, "importable": importable}
    return eval(expression, globals, {})


def cached(func):
    cache = {}

    @wraps(func)
    def inner(expression, *args, **kwargs):
        if expression not in cache:
            cache[expression] = func(expression, *args, **kwargs)
        return cache[expression]

    return inner


def evaluate_boolean_expression(expression: str) -> Union[bool, None]:
    try:
        result = safe_eval(expression)
    except Exception:
        return None
    return bool(result)


@cached
def p_SKIPIF(expression: str, **options: dict[str, str]) -> tuple[bool, str]:
    skip = evaluate_boolean_expression(expression)
    if skip is None:
        raise ValueError(f"failed to evaluate the expression {expression!r}")
    if not skip:
        return False, ""
    reason = str(options.get("reason") or "")
    if not reason:
        reason = colorize("deselected due to @*b{skipif=%s} evaluating to @*g{True}" % expression)
    return True, reason


def write_vvtest_util(case: "TestCase", baseline: bool = False, analyze: bool = False) -> None:
    attrs = get_vvtest_attrs(case, baseline, analyze)
    with open("vvtest_util.py", "w") as fh:
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
                fh.write(f"{key} = {json.dumps(value, indent=3)}\n")


def unique(sequence: list[str]) -> list[str]:
    result = []
    for item in sequence:
        if item not in result:
            result.append(item)
    return result


@typing.no_type_check
def get_vvtest_attrs(case: "TestCase", baseline: bool, analyze: bool) -> dict:
    attrs = {}
    compiler_spec = None
    if config.get("build:compiler:vendor") is None:
        vendor = config.get("build:compiler:vendor")
        version = config.get("build:compiler:version")
        compiler_spec = f"{vendor}@{version}"
    attrs["NAME"] = case.family
    attrs["TESTID"] = case.fullname
    attrs["PLATFORM"] = sys.platform.lower()
    attrs["COMPILER"] = compiler_spec
    attrs["TESTROOT"] = case.exec_root
    attrs["VVTESTSRC"] = ""
    attrs["PROJECT"] = ""
    attrs["OPTIONS"] = []  # FIXME
    attrs["OPTIONS_OFF"] = []  # FIXME
    attrs["SRCDIR"] = case.file_dir
    attrs["TIMEOUT"] = case.timeout
    attrs["KEYWORDS"] = case.keywords()
    attrs["diff_exit_status"] = 64
    attrs["skip_exit_status"] = 63
    attrs["opt_analyze"] = "'--execute-analysis-sections' in sys.argv[1:]"
    attrs["is_analyze"] = bool(case.analyze)
    attrs["is_baseline"] = baseline
    attrs["is_analysis_only"] = analyze
    attrs["PARAM_DICT"] = case.parameters or {}
    for key, val in case.parameters.items():
        attrs[key] = val
    if case.dependencies:
        paramset = {}
        for dep in case.dependencies:
            for key, value in dep.parameters.items():
                paramset.setdefault(key, []).append(value)
        for key, values in paramset.items():
            attrs[f"PARAM_{key}"] = unique(values)
        if len(paramset) > 1:
            key = "_".join(_ for _ in next(iter(case.dependencies)).parameters)
            table = [list(_) for _ in zip(*paramset.values())]
            attrs[f"PARAM_{key}"] = table
        attrs["DEPDIRS"] = [dep.exec_dir for dep in case.dependencies]
        attrs["DEPDIRMAP"] = {}  # FIXME
    return attrs


class ParseError(Exception):
    pass
