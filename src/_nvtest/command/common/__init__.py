import argparse
import os
import sys
from typing import TYPE_CHECKING
from typing import Optional, Sequence, Any, Union

if TYPE_CHECKING:
    from _nvtest.config import Config
    from _nvtest.session import Session

from _nvtest.test.enums import Result
from _nvtest.test.testcase import TestCase
from _nvtest.util import tty
from _nvtest.util.tty.color import colorize

default_timeout = 60 * 60


def add_mark_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-k",
        dest="keyword_expr",
        default="",
        metavar="EXPRESSION",
        help="Only run tests matching given keyword expression. "
        "For example: -k 'key1 and not key2'.",
    )
    parser.add_argument(
        "-o",
        dest="on_options",
        default=[],
        metavar="OPTION",
        action="append",
        help="Turn option(s) on, such as '-o dbg' or '-o intel'",
    )


valid_cdash_options = {
    "url": "The URL of the CDash server",
    "project": "The project name",
    "track": "The CDash build track (group)",
    "site": "The host tests were run on",
    "stamp": "The timestamp of the build",
    "build": "The build name",
}
class CDashOption(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        options: dict[str, str] = getattr(namespace, self.dest, None) or {}
        assert isinstance(option, str)
        u_options: list[str] = option.replace(",", " ").split()
        for u_option in u_options:
            opt, value = u_option.split("=")
            if opt not in valid_cdash_options:
                raise argparse.ArgumentError(self, f"{opt!r} is not a valid CDash option")
            options[opt] = value
        setattr(namespace, self.dest, options)


def add_cdash_arguments(parser: argparse.ArgumentParser) -> None:
    s_opt = ", ".join(colorize("@*{%s}: %s" % item) for item in valid_cdash_options.items())
    help_msg = colorize(
        "Write CDash XML files and (optionally) post to CDash. "
        "Pass @*{option} to the CDash writer. @*{option} is an '=' separated "
        "key, value pair.  Multiple options can be separated by commas. "
        "For example, --cdash "
        "track=Experimental,project=MyProject,url=http://my-project.cdash.com"
        "Recognized options are %s" % s_opt
    )
    group = parser.get_group("post processing options")
    group.add_argument(
        "--cdash",
        action=CDashOption,
        dest="cdash_options",
        metavar="option",
        help=help_msg,
    )


class Command:
    name: str
    add_help: bool = True
    aliases: Optional[list[str]] = None
    description: Optional[str] = None
    epilog: Optional[str] = None
    family: Optional[str] = None

    def __init__(self, config: "Config", session: "Session") -> None:
        self.config = config
        self.session = session

    @property
    def mode(self) -> str:
        raise NotImplementedError

    @staticmethod
    def add_options(parser: argparse.ArgumentParser):
        raise NotImplementedError

    def setup(self, *args, **kwargs):
        ...

    def run(self, *args, **kwargs):
        raise NotImplementedError

    def finish(self, *args, **kwargs):
        ...


class ConsolePrinter:
    session: "Session"
    cases: list[TestCase]
    log_level: int = tty.INFO

    def print_text(self, text: str):
        if self.log_level < tty.INFO:
            return
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def print_section_header(self, label, char="="):
        _, width = tty.terminal_size()
        repl = "." * tty.clen(label)
        text = f" {repl} ".center(width, char)
        self.print_text(text.replace(repl, label))

    def print_front_matter(self):
        session = self.session
        n = N = session.config.machine.cpu_count
        p = session.config.machine.platform
        v = session.config.python.version
        self.print_text(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}")
        self.print_text(f"rootdir: {session.invocation_params.dir}")

    def print_test_results_summary(self, duration: float = -1):
        if self.log_level < tty.WARN:
            return
        if duration == -1:
            finish = max(_.finish for _ in self.cases)
            start = min(_.start for _ in self.cases)
            duration = finish - start
        if self.log_level > tty.INFO:
            tty.section("Test files")
            groups: dict[str, list[str]] = {}
            for case in self.cases:
                color = case.result.color
                group = groups.setdefault(case.result.name, [])
                label = colorize("%s @%s{%s}" % (case.name, color, case.result.name))
                group.append(label)
            for result in Result.members:
                for label in groups.get(result, []):
                    self.print_text(label)

        totals: dict[str, list[TestCase]] = {}
        for case in self.cases:
            totals.setdefault(case.result.name, []).append(case)

        if Result.FAIL in totals or Result.DIFF in totals or Result.SKIP in totals:
            tty.section("Short test summary info")
            for result in (Result.FAIL, Result.DIFF):
                if result not in totals:
                    continue
                for case in totals[result]:
                    f = case.logfile
                    if f.startswith(os.getcwd()):
                        f = os.path.relpath(f)
                    reasons = [case.result.reason]
                    if not case.result.reason and not os.path.exists(f):
                        reasons.append("No log file found")
                    else:
                        reasons.append(f"See {f}")
                    reason = ". ".join(_ for _ in reasons if _.split())
                    self.print_text(
                        "%s %s: %s" % (case.result.cname, str(case), reason)
                    )
            if Result.NOTDONE in totals:
                for case in totals[Result.NOTDONE]:
                    self.print_text("%s %s" % (case.result.cname, str(case)))
            if Result.SKIP in totals:

                for case in totals[Result.SKIP]:
                    cname = case.result.cname
                    reason = case.skip.reason
                    self.print_text(
                        "%s %s: Skipped due to %s" % (cname, str(case), reason)
                    )

        summary_parts = []
        for member in Result.members:
            if self.log_level <= tty.INFO and member == Result.NOTRUN:
                continue
            n = len(totals.get(member, []))
            if n:
                c = Result.colors[member]
                summary_parts.append(colorize("@%s{%d %s}" % (c, n, member.lower())))
        text = ", ".join(summary_parts)
        tty.section(text + f" in {duration:.2f}s.")

    def print_testcase_summary(self):
        files: list[str] = list({case.file for case in self.cases})
        t = "@*{collected %d tests from %d files}" % (len(self.cases), len(files))
        self.print_text(colorize(t))
        cases_to_run = [
            case
            for case in self.cases
            if not case.skip
            and case.result in (Result.NOTRUN, Result.NOTDONE, Result.SETUP)
        ]
        max_workers = getattr(self.option, "max_workers", -1)
        self.print_text(
            colorize(
                "@*g{running} %d test cases with %d workers"
                % (len(cases_to_run), max_workers)
            )
        )

        skipped = [case for case in self.cases if case.skip]
        skipped_reasons: dict[str, int] = {}
        for case in skipped:
            reason = case.skip.reason
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
        self.print_text(colorize("@*b{skipping} %d test cases" % len(skipped)))
        for (reason, n) in skipped_reasons.items():
            self.print_text(f"  - {n} {reason.lstrip()}")
        return
