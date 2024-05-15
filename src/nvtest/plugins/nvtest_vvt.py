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
from typing import Optional
from typing import Union

import nvtest
from _nvtest import config
from _nvtest.enums import list_parameter_space
from _nvtest.test.generator import AbstractTestFile
from _nvtest.third_party.color import colorize
from _nvtest.util import scalar
from _nvtest.util.time import to_seconds

if TYPE_CHECKING:
    from _nvtest.test.case import TestCase


class VVTTestFile(AbstractTestFile):
    file_type = ".vvt"

    def load(self) -> None:
        try:
            args, _ = p_VVT(self.file)
        except ParseError as e:
            raise ValueError(f"Failed to parse {self.file} at command {e.args[0]}") from None
        for arg in args:
            if arg.command == "keywords":
                self.f_KEYWORDS(arg)
            elif arg.command in ("copy", "link", "sources"):
                self.f_SOURCES(arg)
            elif arg.command == "preload":
                self.f_PRELOAD(arg)
            elif arg.command == "parameterize":
                self.f_PARAMETERIZE(arg)
            elif arg.command == "analyze":
                self.f_ANALYZE(arg)
            elif arg.command in ("name", "testname"):
                self.f_NAME(arg)
            elif arg.command == "timeout":
                self.f_TIMEOUT(arg)
            elif arg.command == "skipif":
                self.f_SKIPIF(arg)
            elif arg.command == "baseline":
                self.f_BASELINE(arg)
            elif arg.command == "enable":
                self.f_ENABLE(arg)
            elif arg.command == "depends_on":
                self.f_DEPENDS_ON(arg)
            else:
                raise ValueError(f"Unknown command: {arg.command} at {arg.line_no}:{arg.line}")

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
        if arg.options and arg.options.get("rename"):
            s = re.sub(",\s*", ",", arg.argument)
            file_pairs = [_.split(",") for _ in s.split()]
            for file_pair in file_pairs:
                assert len(file_pair) == 2
                fun(*file_pair, when=arg.when, **arg.options)  # type: ignore
        else:
            files = arg.argument.split()
            fun(*files, when=arg.when, **arg.options)  # type: ignore

    def f_PRELOAD(self, arg: SimpleNamespace) -> None:
        assert arg.command == "preload"
        parts = arg.argument.split()
        if parts[0] == "source-script":
            arg.argument = parts[1]
            arg.options["source"] = True
        self.m_preload(arg.argument, when=arg.when, **arg.options)  # type: ignore

    def f_PARAMETERIZE(self, arg: SimpleNamespace) -> None:
        names, values, kwds = p_PARAMETERIZE(arg)
        self.m_parameterize(list(names), values, when=arg.when, **kwds)

    def f_ANALYZE(self, arg: SimpleNamespace) -> None:
        """# VVT: analyze ( OPTIONS ) [:=] --FLAG
        | analyze ( OPTIONS ) [:=] FILE
        """
        options = dict(arg.options)
        if arg.argument:
            key = "flag" if arg.argument.startswith("-") else "script"
            options[key] = arg.argument
        self.m_analyze(when=arg.when, **options)

    def f_TIMEOUT(self, arg: SimpleNamespace) -> None:
        """# VVT: timeout ( OPTIONS ) [:=] SECONDS"""
        seconds = to_seconds(arg.argument)
        self.m_timeout(seconds, when=arg.when)

    def f_SKIPIF(self, arg: SimpleNamespace) -> None:
        """# VVT: skipif ( reason=STRING ) [:=] BOOL_EXPR"""
        skip, reason = p_SKIPIF(arg.argument, reason=arg.options.get("reason"))
        self.m_skipif(skip, reason=reason)

    def f_BASELINE(self, arg: SimpleNamespace) -> None:
        """# VVT: baseline ( OPTIONS ) [:=] --FLAG
        | baseline ( OPTIONS ) [:=] file1,file2 file3,file4 ...
        """
        argument = re.sub(",\s*", ",", arg.argument)
        file_pairs = [_.split(",") for _ in argument.split()]
        for file_pair in file_pairs:
            if len(file_pair) == 1 and file_pair[0].startswith("--"):
                self.m_baseline(when=arg.when, flag=file_pair[0], **arg.options)
            elif len(file_pair) != 2:
                raise ValueError(f"{self.file}: invalid baseline command at {arg.line!r}")
            else:
                self.m_baseline(file_pair[0], file_pair[1], when=arg.when, **arg.options)

    def f_ENABLE(self, arg: SimpleNamespace) -> None:
        """# VVT: enable ( OPTIONS ) [:=] BOOL"""
        if arg.argument and arg.argument.lower() == "true":
            arg.argument = True
        elif arg.argument and arg.argument.lower() == "false":
            arg.argument = False
        elif arg.argument is None:
            arg.argument = True
        # if arg.options.get("platforms") == "":
        #    arg.options["platforms"] = "__"
        self.m_enable(arg.argument, when=arg.when, **arg.options)

    def f_NAME(self, arg: SimpleNamespace) -> None:
        """# VVT: name ( OPTIONS ) [:=] NAME"""
        self.m_name(arg.argument.strip())

    def f_DEPENDS_ON(self, arg: SimpleNamespace) -> None:
        """# VVT: depends on ( OPTIONS ) [:=] STRING"""
        if "expect" in arg.options:
            arg.options["expect"] = int(arg.options["expect"])
        self.m_depends_on(arg.argument.strip(), when=arg.when, **arg.options)


non_code_token_nums = [
    getattr(tokenize, _)
    for _ in ("NL", "NEWLINE", "INDENT", "DEDENT", "ENCODING", "STRING", "COMMENT")
]

LPAREN = "("
RPAREN = ")"
COMMA = ","
COLON = ":"
EQUAL = "="


def p_PARAMETERIZE(arg: SimpleNamespace) -> tuple[list, list, dict]:
    """# VVT: parameterize ( OPTIONS ) [:=] names_spec = values_spec

    names_spec: name1,name2,...
    values_spec: val1_1,val2_1,... val1_2,val2_2,... ...

    """
    names_spec, values_spec = arg.argument.split("=", 1)
    values_spec = re.sub(",\s*", ",", values_spec)
    names = [_.strip() for _ in names_spec.split(",") if _.split()]
    values = []
    for group in values_spec.split():
        row = [loads(_) for _ in group.split(",") if _.split()]
        if len(row) != len(names):
            raise ParseError(f"invalid parameterize command at {arg.line_no}:{arg.line!r}")
        values.append(row)
    kwds = dict(arg.options)
    for key in ("autotype", "int", "float", "str"):
        kwds.pop(key, None)
    kwds["type"] = list_parameter_space
    return names, values, kwds


def p_LINE(line: str) -> Optional[SimpleNamespace]:
    """COMMAND ( OPTIONS ) [:=] ARGS"""
    if not line.split():
        return None
    tokens = get_tokens(line)
    cmd_stack = []
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        if token.type == tokenize.OP:
            break
        cmd_stack.append(token.string.strip())
    command = "_".join(cmd_stack)

    # Look for option block and parse it
    options = {}
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
            raise ParseError(f"Failed to find end of options in {line}")
        options.update(p_OPTIONS(option_tokens))
        token = next(tokens)
    when = make_when_expr(options)

    # Everything left over is the args
    args = None
    if token.type != tokenize.NEWLINE:
        if token.type != tokenize.OP and token.string not in (EQUAL, COLON):
            raise ParseError(f"Could not determine start of arguments in {line}")
        end = token.end[-1]
        args = line[end:].strip()

    return SimpleNamespace(
        command=command,
        when=when,
        options=options,
        argument=args,
        line=line,
        line_no=token.start[0],
    )


def p_VVT(filename: Union[Path, str]) -> tuple[list[SimpleNamespace], int]:
    """# VVT: COMMAND ( OPTIONS ) [:=] ARGS"""
    commands: list[SimpleNamespace] = []
    lines, line_no = find_vvt_lines(filename)
    for line in lines:
        ns = p_LINE(line)
        if ns:
            commands.append(ns)
    return commands, line_no


def get_tokens(path) -> Generator[tokenize.TokenInfo, None, None]:
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
    tokens: Generator[tokenize.TokenInfo, None, None]
    if os.path.exists(filename):
        tokens = tokenize.tokenize(open(filename, "rb").readline)
    else:
        tokens = get_tokens(filename)
    s = io.StringIO()
    for token in tokens:
        if token.type == tokenize.ENCODING:
            continue
        elif token.type == tokenize.COMMENT:
            match = re.search("^\s*#\s*VVT\s*:\s*:", token.line)
            if match:
                s.write(f" {token.line[match.end():].rstrip()}")
                continue
            match = re.search("^\s*#\s*VVT\s*:(?!(\s*:))", token.line)
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


def p_OPTION(tokens: list[tokenize.TokenInfo]) -> tuple[str, object]:
    """OPTION : NAME [true]
    | NAME EQUAL VALUE
    """
    token = tokens[0]
    if token.type != tokenize.NAME:
        raise ParseError(token)
    name = token.string
    if len(tokens) == 1:
        return name, True
    token = tokens[1]
    if token.type == tokenize.NEWLINE:
        return name, True
    if (token.type, token.string) != (tokenize.OP, EQUAL):
        raise ParseError(token)
    value = ""
    for token in tokens[2:]:
        if token.type == tokenize.NEWLINE:
            break
        value += f" {token.string}"
    return name, strip_quotes(value.strip())


def p_OPTIONS(tokens: list[tokenize.TokenInfo]) -> dict[str, object]:
    """OPTIONS : OPTION COMMA OPTION ..."""
    u_options: list[tuple[str, object]] = []
    opt_tokens: list[tokenize.TokenInfo] = []
    for token in tokens:
        if (token.type, token.string) == (tokenize.OP, COMMA):
            u_options.append(p_OPTION(opt_tokens))
            opt_tokens = []
        else:
            opt_tokens.append(token)
    if opt_tokens:
        u_options.append(p_OPTION(opt_tokens))
    options = dict(u_options)
    for name in ("option", "platform", "parameter"):
        if name in options:
            options[f"{name}s"] = options.pop(name)
    return options


def importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def loads(arg: str) -> Union[int, float, str]:
    x: Union[scalar.Integer, scalar.Float, scalar.String]
    try:
        x = scalar.Integer(arg)
    except ValueError:
        try:
            x = scalar.Float(arg)
        except ValueError:
            x = scalar.String(arg)
    x.string = arg
    return x


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


def unique(sequence: list[str]) -> list[str]:
    result = []
    for item in sequence:
        if item not in result:
            result.append(item)
    return result


@typing.no_type_check
def get_vvtest_attrs(case: "TestCase", baseline: bool = False, analyze: bool = False) -> dict:
    from _nvtest.test.case import AnalyzeTestCase

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
    attrs["is_analyze"] = isinstance(case, AnalyzeTestCase)
    attrs["is_baseline"] = baseline
    attrs["is_analysis_only"] = analyze
    attrs["PARAM_DICT"] = case.parameters or {}
    for key, val in case.parameters.items():
        attrs[key] = val
    if isinstance(case, AnalyzeTestCase):
        for paramset in case.paramsets:
            key = "_".join(paramset.keys)
            table = attrs.setdefault(f"PARAM_{key}", [])
            for row in paramset.values:
                if len(paramset.keys) == 1:
                    table.append(row[0])
                else:
                    table.append(list(row))
        attrs["DEPDIRS"] = [dep.exec_dir for dep in case.dependencies]
        attrs["DEPDIRMAP"] = {}  # FIXME

    attrs["exec_dir"] = case.exec_dir
    attrs["exec_root"] = case.exec_root
    attrs["exec_path"] = case.exec_path
    attrs["file_root"] = case.file_root
    attrs["file_dir"] = case.file_dir
    attrs["file_path"] = case.file_path

    return attrs


nvtest.plugin.test_generator(VVTTestFile)


@nvtest.plugin.register(scope="test", stage="setup")
def write_vvtest_util(case: "TestCase", baseline: bool = False, analyze: bool = False) -> None:
    if not case.file_path.endswith(".vvt"):
        return
    attrs = get_vvtest_attrs(case, baseline=baseline, analyze=analyze)
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
                fh.write(f"{key} = {json.dumps(value, indent=4)}\n")


@nvtest.plugin.register(scope="test", stage="finish")
def write_execute_log(case: "TestCase") -> None:
    if not case.file_path.endswith(".vvt"):
        return
    f = os.path.join(case.exec_dir, "execute.log")
    nvtest.filesystem.force_symlink(case.logfile(), f)


class ParseError(Exception):
    pass
