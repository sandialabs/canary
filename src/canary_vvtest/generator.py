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
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import Generator

import canary
from _canary.enums import list_parameter_space
from _canary.generator import CanaryDSLSpecGenerator
from _canary.paramset import ParameterSet
from _canary.util import string

from . import scalar

if TYPE_CHECKING:
    pass

logger = canary.get_logger(__name__)


class VVTestAdapter(CanaryDSLSpecGenerator):
    file_patterns: ClassVar[tuple[str, ...]] = ("*.vvt",)

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.load()

    def load(self, file: str | None = None) -> None:
        file = file or self.file
        for arg in p_VVT(file):
            match arg.name:
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
                case "filter_warnings":
                    self.f_FILTER_WARNINGS(arg)
                case "baseline":
                    self.f_BASELINE(arg)
                case "enable":
                    self.f_ENABLE(arg)
                case "depends_on":
                    self.f_DEPENDS_ON(arg)
                case "include" | "insert_directive_file":
                    raise VVTParseError(
                        f"{arg.name}: include file should have already been included!", arg
                    )
                case _:
                    raise VVTParseError(f"Unknown command: {arg.name}", arg)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.path})"

    def describe(self, on_options: list[str] | None = None) -> str:
        from _canary.generate import resolve
        from _canary.util import graph
        from _canary.util.field import Field
        from _canary.util.string import pluralize

        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Keywords: {', '.join(self.get_keywords(on_options=on_options))}\n")
        options = self._option_expressions()
        if options:
            file.write(f"Recognized options: {', '.join(options)}\n")

        # Print raw (unsubstituted) source specs if present
        if hasattr(self, "sources") and isinstance(getattr(self, "sources"), Field):
            src_field = getattr(self, "sources")
            if src_field.items:
                file.write("Source files:\n")
                grouped: dict[str, list[tuple[str, str | None]]] = {}
                for c in src_field.items:
                    s = c.value
                    grouped.setdefault(s.action, []).append((s.src, s.dst))
                for action, files in grouped.items():
                    file.write(f"  {action.title()}:\n")
                    for src, dst in files:
                        file.write(f"    {src}")
                        if dst and dst != os.path.basename(src):
                            file.write(f" -> {dst}")
                        file.write("\n")

        try:
            specs = self.lock(on_options=on_options)
            resolved = resolve(specs)
            n = len(specs)
            opts = ", ".join(on_options or [])
            file.write(f"{n} test {pluralize('spec', n)} using on_options={opts}:\n")
            try:
                graph.print(resolved, file=file)
            except Exception:  # nosec B110
                pass
        except Exception:
            logger.warning("Unable to generate dependency graph")
        return file.getvalue()

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = super().info()
        info["keywords"] = self.get_keywords()
        info["options"] = self._option_expressions()
        return info

    def _option_expressions(self) -> list[str]:
        from _canary.util.field import Field

        option_expressions: set[str] = set()
        for _, attr in vars(self).items():
            if not isinstance(attr, Field):
                continue
            for c in attr.items:
                expr = c.when.option_expr
                if expr:
                    option_expressions.add(expr)
        return sorted(option_expressions)

    def f_KEYWORDS(self, arg: "Directive") -> None:
        assert arg.name == "keywords"
        self.add_keywords(*arg.argument.split(), when=arg.when)

    def f_SOURCES(self, arg: "Directive") -> None:
        assert arg.name in ("copy", "link", "sources")
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
                self.add_source(arg.name, src=file_pair[0], dst=file_pair[1], when=arg.when, **kwds)  # type: ignore[arg-type]
        else:
            files = arg.argument.split() if arg.argument else []
            self.add_source(arg.name, *files, when=arg.when, **kwds)  # type: ignore[arg-type]

    def f_PRELOAD(self, arg: "Directive") -> None:
        assert arg.name == "preload"
        # VVT preload options existed historically but pyt.preload has no effect; keep signature minimal
        self.set_preload(arg.argument, when=arg.when)

    def f_PARAMETERIZE(self, arg: "Directive") -> None:
        names, values, kwds, deps = p_PARAMETERIZE(arg)

        if deps:
            assert len(deps) == len(values)
            for dep in deps:
                if dep is None:
                    continue
                if isinstance(dep, str):
                    d = canary.DependencySpec(pattern=dep, when="on_success", expects="+")
                    self.add_dependency(d, when=arg.when)
                else:
                    assert isinstance(dep, dict)
                    for dep_name, dep_params in dep.items():
                        p = ".".join(f"{k}={dep_params[k]}" for k in sorted(dep_params))
                        d = canary.DependencySpec(
                            pattern=f"{dep_name}.{p}", when="on_success", expects="+"
                        )
                        self.add_dependency(d, when=arg.when)

        ps = ParameterSet.list_parameter_space(list(names), values, file=self.file)
        self.add_parameter_set(ps, when=arg.when)

    def f_ANALYZE(self, arg: "Directive") -> None:
        options = dict(arg.options or {})
        if arg.argument:
            key = "flag" if arg.argument.startswith("-") else "script"
            options[key] = arg.argument
        self.set_analyze(when=arg.when, **options)

    def f_TIMEOUT(self, arg: "Directive") -> None:
        try:
            seconds = to_seconds(arg.argument)
        except InvalidTimeFormat:
            raise VVTParseError(f"invalid time format: {arg.line!r}", arg) from None
        self.add_timeout(seconds, when=arg.when)

    def f_FILTER_WARNINGS(self, arg: "Directive") -> None:
        fw = p_FILTER_WARNINGS(arg)
        self.set_filter_warnings(fw)

    def f_SKIPIF(self, arg: "Directive") -> None:
        skip, reason = p_SKIPIF(arg)
        self.set_skipif(skip, reason=reason)

    def f_BASELINE(self, arg: "Directive") -> None:
        file_pairs = make_table(arg.argument)
        options = dict(arg.options or {})
        # baseline currently only supports src/dst or flag; ignore other options for now
        for file_pair in file_pairs:
            if len(file_pair) == 1 and file_pair[0].startswith("--"):
                self.add_baseline(flag=file_pair[0], when=arg.when)
            elif len(file_pair) != 2:
                raise VVTParseError(f"invalid baseline command: {arg.line!r}", arg)
            else:
                self.add_baseline(src=file_pair[0], dst=file_pair[1], when=arg.when)

    def f_ENABLE(self, arg: "Directive") -> None:
        if arg.argument and arg.argument.lower() == "true":
            value = True
        elif arg.argument and arg.argument.lower() == "false":
            value = False
        elif arg.argument is None:
            value = True
        else:
            value = bool(arg.argument)

        self.set_enable(value, when=arg.when)

    def f_NAME(self, arg: "Directive") -> None:
        # VVT name/testname: create an additional family
        name = (arg.argument or "").strip()
        if name:
            self.add_family(name)

    def f_DEPENDS_ON(self, arg: "Directive") -> None:
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
        d = canary.DependencySpec(pattern=arg.argument, expects=expects, when=when.lower())
        self.add_dependency(d, when=arg.when)


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


@dataclasses.dataclass(slots=True)
class Directive:
    name: str
    file: str
    when: dict[str, str]
    options: list[tuple[str, Any]]
    argument: str
    line: str
    line_no: int


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


def p_GEN_PARAMETERIZE(arg: "Directive") -> tuple[list, list, dict, list | None]:
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


def p_PARAMETERIZE(arg: "Directive") -> tuple[list, list, dict, list | None]:
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


def p_VVT(filename: Path | str) -> Generator["Directive", None, None]:
    """# VVT: COMMAND ( OPTIONS ) [:=] ARGS"""
    lines, line_no = find_vvt_lines(filename)
    for line in lines:
        ns = p_LINE(filename, line)
        if ns and ns.name in ("include", "insert_directive_file"):
            inc_file = ns.argument.strip()  # type: ignore[union-attr]
            if not os.path.exists(inc_file) and not os.path.isabs(inc_file):
                inc_file = os.path.join(os.path.dirname(filename), inc_file)
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


def p_FILTER_WARNINGS(arg: "Directive") -> bool:
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


def p_SKIPIF(arg: "Directive") -> tuple[bool, str]:
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
