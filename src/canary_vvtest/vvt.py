# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import importlib.util
import io
import json
import json.decoder
import os
import re
import shlex
import sys
import tokenize
from itertools import repeat
from pathlib import Path
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Generator
from typing import Literal
from typing import cast

import canary
import canary_pyt.pyt as pyt
from _canary.enums import list_parameter_space
from _canary.ir import DependencySelector
from _canary.paramset import ParameterSet
from _canary.util import string

from . import scalar

logger = canary.get_logger(__name__)
ActionT = Literal["copy", "link", "none"]


@dataclasses.dataclass(slots=True)
class Directive:
    name: str
    file: str
    when: dict[str, str]
    options: list[tuple[str, Any]]
    argument: str
    line: str
    line_no: int


class VVTestModel(pyt.PYTModel): ...


class VVTestLockEmitter(pyt.PYTLockEmitter): ...


class VVTestLoader:
    def __init__(self, *, file: Path) -> None:
        self.file = file

    def parse(self) -> list[Directive]:
        directives: list[Directive] = []
        for directive in p_VVT(self.file):
            if directive.name in ("include", "insert_directive_file"):
                raise VVTParseError(
                    f"{directive.name}: include file should have already been included!", directive
                )
            directives.append(directive)
        return directives


class VVTestAdapter:
    def __init__(self, model: VVTestModel) -> None:
        self.m = model

    def apply(self, directives: list[Directive]) -> None:
        for directive in directives:
            fn: Callable[[Directive], None]
            if directive.name in ("copy", "link", "sources"):
                fn = self.f_SOURCES
            elif directive.name in ("name", "testname"):
                fn = self.f_NAME
            elif not hasattr(self, f"f_{directive.name.upper()}"):
                raise VVTParseError(f"Unknown command: {directive.name}", directive)
            else:
                fn = getattr(self, f"f_{directive.name.upper()}")
            fn(directive)

    def f_KEYWORDS(self, arg: Directive) -> None:
        assert arg.name == "keywords"
        self.m.add_keywords(*arg.argument.split(), when=arg.when)

    def f_SOURCES(self, arg: Directive) -> None:
        action = cast(ActionT, arg.name if arg.name in ("copy", "link") else "none")
        assert action in ("copy", "link", "none")
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
                self.m.add_source(action=action, src=file_pair[0], dst=file_pair[1], when=arg.when)
        else:
            files = arg.argument.split() if arg.argument else []
            for f in files:
                self.m.add_source(action=action, src=f, when=arg.when)

    def f_PRELOAD(self, arg: Directive) -> None:
        assert arg.name == "preload"
        # VVT preload options existed historically but pyt.preload has no effect; keep signature minimal
        self.m.set_preload(arg.argument, when=arg.when)

    def f_PARAMETERIZE(self, arg: Directive) -> None:
        names, values, kwds, deps = p_PARAMETERIZE(arg)

        if deps:
            assert len(deps) == len(values)
            for dep in deps:
                if dep is None:
                    continue
                if isinstance(dep, str):
                    d = DependencySelector(pattern=dep, when="on_success", expects="+")
                    self.m.add_dependency(d, when=arg.when)
                else:
                    assert isinstance(dep, dict)
                    for dep_name, dep_params in dep.items():
                        p = ".".join(f"{k}={dep_params[k]}" for k in sorted(dep_params))
                        d = DependencySelector(
                            pattern=f"{dep_name}.{p}", when="on_success", expects="+"
                        )
                        self.m.add_dependency(d, when=arg.when)

        ps = ParameterSet.list_parameter_space(list(names), values, file=self.m.file.as_posix())
        self.m.add_parameter_set(ps, when=arg.when)

    def f_ANALYZE(self, arg: Directive) -> None:
        options = dict(arg.options or {})
        if arg.argument:
            key = "flag" if arg.argument.startswith("-") else "script"
            options[key] = arg.argument
        self.m.set_analyze(when=arg.when, **options)

    def f_TIMEOUT(self, arg: Directive) -> None:
        try:
            seconds = to_seconds(arg.argument)
        except InvalidTimeFormat:
            raise VVTParseError(f"invalid time format: {arg.line!r}", arg) from None
        self.m.add_timeout(seconds, when=arg.when)

    def f_FILTER_WARNINGS(self, arg: Directive) -> None:
        fw = p_FILTER_WARNINGS(arg)
        self.m.set_filter_warnings(fw)

    def f_SKIPIF(self, arg: Directive) -> None:
        skip, reason = p_SKIPIF(arg)
        self.m.set_skipif(skip, reason=reason)

    def f_BASELINE(self, arg: Directive) -> None:
        items = make_table(arg.argument)
        options = dict(arg.options or {})
        # baseline currently only supports src/dst or flag; ignore other options for now
        for item in items:
            if len(item) == 1 and item[0].startswith("--"):
                self.m.add_baseline(flag=item[0], when=arg.when)
            elif len(item) == 2:
                self.m.add_baseline(src=item[0], dst=item[1], when=arg.when)
            else:
                raise VVTParseError(f"invalid baseline command: {arg.line!r}", arg)

    def f_ENABLE(self, arg: Directive) -> None:
        if arg.argument and arg.argument.lower() == "true":
            value = True
        elif arg.argument and arg.argument.lower() == "false":
            value = False
        elif not arg.argument:
            value = True
        else:
            value = bool(arg.argument)

        self.m.set_enable(value, when=arg.when)

    def f_NAME(self, arg: Directive) -> None:
        # VVT name/testname: create an additional family
        name = (arg.argument or "").strip()
        if name:
            self.m.add_family(name)

    def f_DEPENDS_ON(self, arg: Directive) -> None:
        options = dict(arg.options or {})
        expects = "+"
        if expect := options.get("expect"):
            try:
                expect = int(expect)
            except ValueError:
                pass
            expects = expect
        when: str = "on_success"
        if result := options.get("result"):
            result = re.sub(r"(?i)\bpass\b", "success", result)
            result = re.sub(r"(?i)\bdiff\b", "diffed", result)
            result = re.sub(r"(?i)\bfail\b", "failed", result)
            result = re.sub(r"(?i)\bskip\b", "skipped", result)
            when = result
        d = DependencySelector(pattern=arg.argument, expects=expects, when=when.lower())
        self.m.add_dependency(d, when=arg.when)


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


def p_GEN_PARAMETERIZE(arg: Directive) -> tuple[list, list, dict, list | None]:
    """# VVT: parameterize ( OPTIONS,generator ) [:=] script [--options]"""
    script, *opts = shlex.split(arg.argument)
    if script in ("python", "python3"):
        script = sys.executable
    with canary.filesystem.working_dir(
        "." if arg.file == "<string>" else os.path.dirname(arg.file)
    ):
        exe = canary.Executable(script)
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
            logger.warning(f"skipping parameter type {opt!r} -- type deduced by json generation")
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


def p_PARAMETERIZE(arg: Directive) -> tuple[list, list, dict, list | None]:
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


def p_LINE(file: Path | str, line: str) -> Directive | None:
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
    args = ""
    if token.type != tokenize.NEWLINE:
        if token.type != tokenize.OP and token.string not in (EQUAL, COLON):
            msg = "failed to determine start of arguments in {0} at line {1} of {2}"
            raise ParseError(msg.format(line, token.start[0], filename))
        end = token.end[-1]
        args = line[end:].strip()

    return Directive(
        name=command,
        file=filename,
        when=when,
        options=options,
        argument=args,
        line=line,
        line_no=token.start[0],
    )


def p_VVT(arg: Path | str) -> Generator[Directive, None, None]:
    """# VVT: COMMAND ( OPTIONS ) [:=] ARGS"""
    lines, _ = find_vvt_lines(arg)
    for line in lines:
        ns = p_LINE(arg, line)
        if ns and ns.name in ("include", "insert_directive_file"):
            inc_file = ns.argument.strip()  # type: ignore[union-attr]
            if not os.path.exists(inc_file) and not os.path.isabs(inc_file):
                inc_file = os.path.join(os.path.dirname(arg), inc_file)
            if not os.path.exists(inc_file):
                raise VVTParseError(f"include file does not exist: {inc_file!r}", ns)
            for i_ns in p_VVT(inc_file):
                yield Directive(
                    name=i_ns.name,
                    file=i_ns.file,
                    when=combine_when_exprs(i_ns.when, ns.when),
                    options=i_ns.options,
                    argument=i_ns.argument,
                    line=i_ns.line,
                    line_no=i_ns.line_no,
                )
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


def find_vvt_lines(arg: Path | str) -> tuple[list[str], int]:
    """Find all lines starting with ``#VVT: COMMAND``, or continuations ``#VVT::``"""
    tokens: Generator[tokenize.TokenInfo, None, None]
    if isinstance(arg, Path):
        if not arg.exists():
            raise FileNotFoundError(arg)
        tokens = tokenize.tokenize(open(arg, "rb").readline)
    elif os.path.exists(arg):
        tokens = tokenize.tokenize(open(arg, "rb").readline)
    else:
        tokens = string.get_tokens(arg)
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


def p_FILTER_WARNINGS(arg: Directive) -> bool:
    expression = arg.argument
    filter_warnings = evaluate_boolean_expression(expression)
    if filter_warnings is None:
        raise VVTParseError(f"failed to evaluate the expression {expression!r}", arg)
    return filter_warnings


def importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def safe_eval(expression: str) -> Any:
    globals = {"os": os, "sys": sys, "importable": importable}
    return eval(expression, globals, {})  # nosec B307


def evaluate_boolean_expression(expression: str) -> bool | None:
    result: Any
    try:
        result = json.loads(expression)
    except json.decoder.JSONDecodeError:
        pass
    else:
        if isinstance(result, (int, bool)):
            return bool(result)
    try:
        result = safe_eval(expression)
    except Exception:
        return None
    return bool(result)


def p_SKIPIF(arg: Directive) -> tuple[bool, str]:
    expression = arg.argument
    options = dict(arg.options)
    reason = str(options.get("reason") or "")
    skip = evaluate_boolean_expression(expression)
    if skip is None:
        raise VVTParseError(f"failed to evaluate the expression {expression!r}", arg)
    if not skip:
        return False, ""
    if not reason:
        reason = f"skipif expression [bold blue]{expression}[/] evaluating to [bold green]True[/]"
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


class ParseError(Exception):
    pass


class VVTParseError(Exception):
    def __init__(self, err, arg):
        message = f"{arg.file}:{arg.line_no}:\nerror: {err}"
        super().__init__(message)


class InvalidTimeFormat(Exception):
    def __init__(self, fmt):
        super().__init__(f"invalid time format: {fmt!r}")
