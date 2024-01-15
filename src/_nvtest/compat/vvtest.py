import io
import json
import os
import re
import sys
import tokenize
import typing
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Generator
from typing import Union

from .. import config
from ..directives.enums import list_parameter_space
from ..util.executable import Executable
from ..util.filesystem import which
from ..util.time import to_seconds
from ..util.tty.color import colorize

if TYPE_CHECKING:
    from ..test.testcase import TestCase
    from ..test.testfile import AbstractTestFile


def load_vvt(file: "AbstractTestFile") -> None:
    try:
        args, _ = parse_vvt(file.file)
    except ParseError as e:
        raise ValueError(
            f"Failed to parse {file.file} at command {e.args[0]}"
        ) from None
    for arg in args:
        if arg.command == "keywords":
            f_keywords(file, arg)
        elif arg.command in ("copy", "link", "sources"):
            f_sources(file, arg)
        elif arg.command == "preload":
            f_preload(file, arg)
        elif arg.command == "parameterize":
            f_parameterize(file, arg)
        elif arg.command == "analyze":
            f_analyze(file, arg)
        elif arg.command in ("name", "testname"):
            f_name(file, arg)
        elif arg.command == "timeout":
            f_timeout(file, arg)
        elif arg.command == "skipif":
            f_skipif(file, arg)
        elif arg.command == "baseline":
            f_baseline(file, arg)
        elif arg.command == "enable":
            f_enable(file, arg)
        elif arg.command == "depends_on":
            f_depends_on(file, arg)
        else:
            raise ValueError(
                f"Unknown command: {arg.command} at {arg.line_no}:{arg.line}"
            )


def parse_vvt_directive(directive: str) -> SimpleNamespace:
    tokens = get_tokens(directive)
    cmd_stack = []
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        if token.type == tokenize.OP:
            break
        cmd_stack.append(token.string.strip())
    command = "_".join(cmd_stack)
    options = None
    if is_opening_paren(token):
        options = _parse_vvt_command_options(tokens)
        token = next(tokens)
    args = None
    if token.type != tokenize.NEWLINE:
        if not is_vvt_assignment_op(token):
            raise ParseError(f"Failed to parse {directive}")
        end = token.end[-1]
        args = directive[end:].strip()
    options = options or {}
    when = make_when_expr(options)
    return SimpleNamespace(
        command=command,
        when=when,
        options=options,
        argument=args,
        line=directive,
        line_no=token.start[0],
    )


def parse_vvt_directives(code: str) -> tuple[list[SimpleNamespace], int]:
    commands: list[SimpleNamespace] = []
    comments, line_no = collect_vvt_comments(code)
    for vvt_comment in comments:
        ns = parse_vvt_directive(vvt_comment)
        commands.append(ns)
    return commands, line_no


def parse_vvt(filename: Union[Path, str]) -> tuple[list[SimpleNamespace], int]:
    commands, line_no = parse_vvt_directives(open(filename).read())
    return commands, line_no


def get_tokens(code):
    fp = io.BytesIO(code.encode("utf-8"))
    tokens = tokenize.tokenize(fp.readline)
    return tokens


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


command_regex = re.compile("^#\s*VVT:")
continuation_regex = re.compile("^#\s*VVT:\s*:")


def is_vvt_continuation(string: str) -> bool:
    return bool(continuation_regex.search(string))


def is_vvt_command(string: str) -> bool:
    return bool(command_regex.search(string)) and not is_vvt_continuation(string)


def strip_vvt_prefix(string: str, continuation: bool = False) -> str:
    regex = continuation_regex if continuation else command_regex
    return regex.sub("", string).lstrip()


def collect_vvt_comments(code: str) -> tuple[list[str], int]:
    tokens = get_tokens(code)
    non_code_token_nums = (
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.STRING,
        tokenize.COMMENT,
    )
    vvt_comments: list[str] = []
    for token in tokens:
        toknum, tokval, _, _, _ = token
        if toknum == tokenize.ENCODING:
            continue
        elif toknum == tokenize.COMMENT:
            if is_vvt_continuation(tokval):
                s = strip_vvt_prefix(tokval, True)
                vvt_comments[-1] += f" {s}"
            elif is_vvt_command(tokval):
                s = strip_vvt_prefix(tokval)
                vvt_comments.append(s)
        elif toknum not in non_code_token_nums:
            break
    return vvt_comments, token.start[0]


def is_opening_paren(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.OP and token.string == "("


def is_closing_paren(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.OP and token.string == ")"


def is_comma(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.OP and token.string == ","


def is_assignment_op(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.OP and token.string == "="


def is_vvt_assignment_op(token: tokenize.TokenInfo) -> bool:
    return token.type == tokenize.OP and token.string in "=:"


def _remove_surrounding_quotes(arg: str) -> str:
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


def _parse_vvt_command_option(string: str) -> tuple[str, object]:
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
    if not is_assignment_op(token):
        raise ParseError(token)
    value = ""
    for token in tokens:
        if token.type == tokenize.NEWLINE:
            break
        value += f" {token.string}"
    return name, _remove_surrounding_quotes(value.strip())


def _parse_vvt_command_options(
    tokens: Generator[tokenize.TokenInfo, None, None],
) -> dict[str, object]:
    i = 0
    stack = [i]
    s_opt = ""
    u_options: list[tuple[str, object]] = []
    for token in tokens:
        i += 1
        if is_opening_paren(token):
            stack.append(i)
        elif is_closing_paren(token):
            if not stack:
                raise IndexError(f"No matching closing parens at {i}")
            stack.pop()
        if not stack:
            break
        if is_comma(token):
            option = _parse_vvt_command_option(s_opt.strip())
            u_options.append(option)
            s_opt = ""
        else:
            s_opt += f" {token.string}"
    u_options.append(_parse_vvt_command_option(s_opt.strip()))
    if stack:
        raise IndexError(f"No matching opening parens at: {stack.pop()}")
    if not is_closing_paren(token):
        raise ParseError(token)
    options = dict(u_options)
    for name in ("option", "platform", "parameter"):
        if name in options:
            options[f"{name}s"] = options.pop(name)
    return options


def f_keywords(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "keywords"
    file.m_keywords(*arg.argument.split(), when=arg.when)


def f_sources(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command in ("copy", "link", "sources")
    fun = {"copy": file.m_copy, "link": file.m_link, "sources": file.m_sources}[
        arg.command
    ]
    if arg.options and arg.options.get("rename"):
        s = re.sub(",\s*", ",", arg.argument)
        file_pairs = [_.split(",") for _ in s.split()]
        for file_pair in file_pairs:
            assert len(file_pair) == 2
            fun(*file_pair, when=arg.when, **arg.options)  # type: ignore
    else:
        files = arg.argument.split()
        fun(*files, when=arg.when, **arg.options)  # type: ignore


def f_preload(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "preload"
    parts = arg.argument.split()
    if parts[0] == "source-script":
        arg.argument = parts[1]
        arg.options["source"] = True
    file.m_preload(arg.argument, when=arg.when, **arg.options)  # type: ignore


def f_parameterize(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    names, values, kwds = p_parameterize(file, arg)
    file.m_parameterize(list(names), values, when=arg.when, **kwds)


def p_parameterize(
    file: "AbstractTestFile", arg: SimpleNamespace
) -> tuple[list, list, dict]:
    part1, part2 = arg.argument.split("=", 1)
    part2 = re.sub(",\s*", ",", part2)
    names = [_.strip() for _ in part1.split(",") if _.split()]
    values = []
    for group in part2.split():
        row = []
        for item in group.split(","):
            if item.split():
                try:
                    row.append(json.loads(item))
                except json.JSONDecodeError:
                    row.append(item)
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


def f_analyze(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    options = dict(arg.options)
    if arg.argument:
        key = "flag" if arg.argument.startswith("-") else "script"
        options[key] = arg.argument
    file.m_analyze(when=arg.when, **options)


def f_timeout(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    seconds = to_seconds(arg.argument)
    file.m_timeout(seconds, when=arg.when)


def f_skipif(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    skip, reason = parse_skipif(arg.argument, reason=arg.options.get("reason"))
    file.m_skipif(skip, reason=reason)


def f_baseline(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    argument = re.sub(",\s*", ",", arg.argument)
    file_pairs = [_.split(",") for _ in argument.split()]
    for file_pair in file_pairs:
        if len(file_pair) == 1 and file_pair[0].startswith("--"):
            file.m_baseline(when=arg.when, flag=file_pair[0], **arg.options)
        elif len(file_pair) != 2:
            raise ValueError(f"{file.file}: invalid baseline command at {arg.line!r}")
        else:
            file.m_baseline(file_pair[0], file_pair[1], when=arg.when, **arg.options)


def f_enable(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    if arg.argument and arg.argument.lower() == "true":
        arg.argument = True
    elif arg.argument and arg.argument.lower() == "false":
        arg.argument = False
    elif arg.argument is None:
        arg.argument = True
    # if arg.options.get("platforms") == "":
    #    arg.options["platforms"] = "__"
    file.m_enable(arg.argument, when=arg.when, **arg.options)


def f_name(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    file.m_name(arg.argument.strip())


def f_depends_on(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    if "expect" in arg.options:
        arg.options["expect"] = int(arg.options["expect"])
    file.m_depends_on(arg.argument.strip(), when=arg.when, **arg.options)


def importable(module: str) -> bool:
    try:
        __import__(module)
    except (ModuleNotFoundError, ImportError):
        return False
    return True


def safe_eval(expression: str) -> object:
    globals = {"os": os, "sys": sys, "importable": importable}
    return eval(expression, globals, {})


def evaluate_boolean_expression(expression: str) -> Union[bool, None]:
    try:
        result = safe_eval(expression)
    except Exception:
        return None
    return bool(result)


def parse_skipif(expression: str, **options: dict[str, str]) -> tuple[bool, str]:
    skip = evaluate_boolean_expression(expression)
    if skip is None:
        raise ValueError(f"failed to evaluate the expression {expression!r}")
    if not skip:
        return False, ""
    reason = str(options.get("reason") or "")
    if not reason:
        reason = colorize(
            "deselected because @*b{%s} evaluated to @*g{True}" % expression
        )
    return True, reason


def write_vvtest_util(
    case: "TestCase", baseline: bool = False, analyze: bool = False
) -> None:
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


def to_pyt(file: "AbstractTestFile") -> str:
    def join_args(string):
        return ", ".join(repr(_) for _ in string.split())

    def join_kwargs(kwargs):
        return ", ".join([f"{key}={val!r}" for (key, val) in kwargs.items()])

    try:
        vvt_args, line_no = parse_vvt(file.file)
    except ParseError as e:
        raise ValueError(
            f"Failed to parse {file.file} at command {e.args[0]}"
        ) from None
    new_file = f"{os.path.splitext(file.file)[0]}.pyt"
    fh = io.StringIO()
    fh.write("#!/usr/bin/env python3\n")
    fh.write("import sys\nimport nvtest\n")
    for vvt_arg in vvt_args:
        if vvt_arg.command == "keywords":
            args = join_args(vvt_arg.argument)
            fh.write(f"nvtest.directives.keywords({args}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            fh.write(")\n")
        elif vvt_arg.command in ("copy", "link"):
            fh.write(f"nvtest.directives.{vvt_arg.command}(")
            if vvt_arg.options.get("rename"):
                s = re.sub(",\s*", ",", vvt_arg.argument)
                file_pairs = [_.split(",") for _ in s.split()]
                for file_pair in file_pairs:
                    assert len(file_pair) == 2
                    fh.write(f"{file_pair[0]!r}, {file_pair[1]!r}, rename=True")
            else:
                args = join_args(vvt_arg.argument)
                fh.write(f"{args}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            fh.write(")\n")
        elif vvt_arg.command == "sources":
            args = join_args(vvt_arg.argument)
            fh.write("nvtest.directives.sources({args})\n")
        elif vvt_arg.command == "preload":
            parts = vvt_arg.argument.split()
            if parts[0] == "source-script":
                fh.write(f"nvtest.directives.preload({parts[1]!r}, source=True")
            else:
                fh.write(f"nvtest.directives.preload({vvt_arg.argument!r}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            fh.write(")\n")
        elif vvt_arg.command == "parameterize":
            names, values, kwds = p_parameterize(file, vvt_arg)
            s_names = ",".join(names)
            if len(names) == 1:
                s_values = "[{0}]".format(", ".join(f"{_[0]!r}" for _ in values))
            else:
                s_values = repr(values)
            fh.write(f"nvtest.directives.parameterize({s_names!r}, {s_values}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            fh.write(")\n")
        elif vvt_arg.command == "analyze":
            options = dict(vvt_arg.options)
            fh.write("nvtest.directives.analyze(True")
            if vvt_arg.argument:
                key = "flag" if vvt_arg.argument.startswith("-") else "script"
                options[key] = vvt_arg.argument
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            if options:
                kwargs = join_kwargs(options)
                fh.write(f", {kwargs}")
            fh.write(")\n")
        elif vvt_arg.command in ("testname", "name"):
            args = join_args(vvt_arg.argument)
            fh.write(f"nvtest.directives.name({args}")
            if vvt_arg.options:
                kwargs = join_kwargs(vvt_arg.options)
                fh.write(f", {kwargs}")
            fh.write(")\n")
        elif vvt_arg.command == "timeout":
            seconds = to_seconds(vvt_arg.argument)
            fh.write(f"nvtest.directives.timeout({seconds!r}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            if vvt_arg.options:
                kwargs = join_kwargs(vvt_arg.options)
                fh.write(f", {kwargs})\n")
            fh.write(")\n")
        elif vvt_arg.command == "skipif":
            skip, reason = parse_skipif(
                vvt_arg.argument, reason=vvt_arg.options.get("reason")
            )
            fh.write(f"nvtest.directives.skipif({skip!r}, reason={reason!r})\n")
        elif vvt_arg.command == "baseline":
            argument = re.sub(",\s*", ",", vvt_arg.argument)
            file_pairs = [_.split(",") for _ in argument.split()]
            for pair in file_pairs:
                if len(pair) != 2:
                    raise ValueError(
                        f"{file.file}: invalid baseline command at {vvt_arg.line!r}"
                    )
                fh.write(f"nvtest.directives.baseline({pair[0]!r}, {pair[1]!r})\n")
        elif vvt_arg.command == "enable":
            if vvt_arg.argument and vvt_arg.argument.lower() == "true":
                arg = True
            elif vvt_arg.argument and vvt_arg.argument.lower() == "false":
                arg = False
            elif vvt_arg.argument is None:
                arg = True
            else:
                arg = True
            fh.write(f"nvtest.directives.enable({arg!r}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            if vvt_arg.options:
                kwargs = join_kwargs(vvt_arg.options)
                fh.write(f", {kwargs})\n")
            fh.write(")\n")
        elif vvt_arg.command == "depends_on":
            arg = vvt_arg.argument.strip()
            fh.write(f"nvtest.directives.depends_on({arg!r}")
            if vvt_arg.when:
                fh.write(f', when="{vvt_arg.when}"')
            if vvt_arg.options:
                if "expect" in vvt_arg.options:
                    vvt_arg.options["expect"] = int(vvt_arg.options["expect"])
                kwargs = join_kwargs(vvt_arg.options)
                fh.write(f", {kwargs}")
            fh.write(")\n")
        else:
            raise ValueError(f"Unknown command: {vvt_arg.command} at {vvt_arg.line}")
    with open(new_file, "w") as f1:
        f1.write(fh.getvalue())
        with open(file.file, "r") as f2:
            lines = f2.readlines()
            for line in lines[line_no + 1 :]:
                f1.write(line)
    black = which("black")
    if black is not None:
        Executable(black)(new_file)
    return new_file


class ParseError(Exception):
    pass
