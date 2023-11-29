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

from .. import paths
from ..mark.structures import AbstractParameterSet
from ..util.time import to_seconds
from ..util.tty.color import colorize

if TYPE_CHECKING:
    from ..test.testcase import TestCase
    from ..test.testfile import AbstractTestFile


def load_vvt(file: "AbstractTestFile") -> None:
    try:
        args = parse_vvt(file.file)
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
            raise ValueError(f"Unknown command: {arg.command} at {arg.line}")


def parse_vvt_directives(code: str) -> list[SimpleNamespace]:
    commands: list[SimpleNamespace] = []
    for vvt_comment in collect_vvt_comments(code):
        ns = parse_vvt_directive(vvt_comment)
        commands.append(ns)
    return commands


def parse_vvt(filename: Union[Path, str]) -> list[SimpleNamespace]:
    commands = parse_vvt_directives(open(filename).read())
    return commands


def get_tokens(code):
    fp = io.BytesIO(code.encode("utf-8"))
    tokens = tokenize.tokenize(fp.readline)
    return tokens


command_regex = re.compile("^#\s*VVT:")
continuation_regex = re.compile("^#\s*VVT:\s*:")


def is_vvt_continuation(string: str) -> bool:
    return bool(continuation_regex.search(string))


def is_vvt_command(string: str) -> bool:
    return bool(command_regex.search(string)) and not is_vvt_continuation(string)


def strip_vvt_prefix(string: str, continuation: bool = False) -> str:
    regex = continuation_regex if continuation else command_regex
    return regex.sub("", string).lstrip()


def collect_vvt_comments(code: str) -> list[str]:
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
    return vvt_comments


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
    tokens: Generator[tokenize.TokenInfo, None, None]
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
    for name in ("option", "platform"):
        if name in options:
            options[f"{name}s"] = options.pop(name)
    return options


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
    return SimpleNamespace(
        command=command, options=options or {}, argument=args, line=directive
    )


def f_keywords(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "keywords"
    file.m_keywords(*arg.argument.split(), **arg.options)


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
            fun(*file_pair, **arg.options)  # type: ignore
    else:
        files = arg.argument.split()
        fun(*files, **arg.options)  # type: ignore


def f_preload(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    assert arg.command == "preload"
    file.m_preload(arg.argument, **arg.options)  # type: ignore


def f_parameterize(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
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
                # row[-1].raw = item
        values.append(row)
    if not all(len(values[0]) == len(_) for _ in values[1:]):
        raise ValueError(f"{file.file}: invalid parameterize command at {arg.line!r}")
    if arg.options:
        arg.options.pop("autotype", None)
    file._paramsets.append(AbstractParameterSet(list(names), values, **arg.options))


def f_analyze(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    options = dict(arg.options)
    if arg.argument:
        key = "flag" if arg.argument.startswith("-") else "script"
        options[key] = arg.argument
    file.m_analyze(True, **options)


def f_timeout(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    seconds = to_seconds(arg.argument)
    file.m_timeout(seconds, **arg.options)


def f_skipif(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    skip, reason = parse_skipif(arg.argument, reason=arg.options.get("reason"))
    file.m_skipif(skip, reason=reason)


def f_baseline(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    argument = re.sub(",\s*", ",", arg.argument)
    file_pairs = [_.split(",") for _ in argument.split()]
    for file_pair in file_pairs:
        if len(file_pair) != 2:
            raise ValueError(f"{file.file}: invalid baseline command at {arg.line!r}")
        file.m_baseline(file_pair[0], file_pair[1], **arg.options)


def f_enable(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    if arg.argument and arg.argument.lower() == "true":
        arg.argument = True
    elif arg.argument and arg.argument.lower() == "false":
        arg.argument = False
    elif arg.argument is None:
        arg.argument = True
    # if arg.options.get("platforms") == "":
    #    arg.options["platforms"] = "__"
    file.m_enable(arg.argument, **arg.options)


def f_name(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    file.m_name(arg.argument.strip(), **arg.options)


def f_depends_on(file: "AbstractTestFile", arg: SimpleNamespace) -> None:
    file.m_depends_on(arg.argument.strip(), **arg.options)


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


def write_vvtest_util(case: "TestCase") -> None:
    attrs = get_vvtest_attrs(case)
    with open("vvtest_util.py", "w") as fh:
        fh.write("import os\n")
        fh.write("import sys\n")
        for key, value in attrs.items():
            fh.write(f"{key} = {json.dumps(value, indent=3)}\n")


def unique(sequence: list[str]) -> list[str]:
    result = []
    for item in sequence:
        if item not in result:
            result.append(item)
    return result


@typing.no_type_check
def get_vvtest_attrs(case: "TestCase") -> dict:
    attrs = {}
    attrs["NAME"] = case.family
    attrs["TESTID"] = case.fullname
    attrs["PLATFORM"] = sys.platform.lower()
    attrs["COMPILER"] = ""  # FIXME
    attrs["VVTESTSRC"] = paths.prefix
    attrs["TESTROOT"] = case.exec_root
    attrs["PROJECT"] = ""
    attrs["OPTIONS"] = []  # FIXME
    attrs["OPTIONS_OFF"] = []  # FIXME
    attrs["SRCDIR"] = case.file_dir
    attrs["TIMEOUT"] = case.timeout
    attrs["KEYWORDS"] = case.keywords()
    attrs["diff_exit_status"] = 64
    attrs["skip_exit_status"] = 63
    attrs["opt_analyze"] = "'--execute-analysis-sections' in sys.argv[1:]"
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
