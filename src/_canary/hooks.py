# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import importlib.util
import io
import os
import shlex
import tarfile
from datetime import datetime
from pathlib import Path
from string import Template
from textwrap import indent
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Literal

import rich

from . import config
from .config.argparsing import Parser
from .generator import AbstractTestGenerator
from .hookspec import hookimpl
from .third_party.monkeypatch import monkeypatch
from .util import logging
from .util.query_data import load_query_data
from .util.sendmail import sendmail
from .util.string import pluralize
from .util.term import terminal_size
from .workspace import Session
from .workspace import Workspace

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .job import Job
    from .workspace import Session


logger = logging.get_logger(__name__)


@hookimpl(wrapper=True)
def canary_addcommand(parser: "Parser") -> Generator[None, None, None]:
    yield
    if commands := config.pluginmanager.hook.canary_subcommand():
        # Backward compatible: prefer canary_addcommand
        for command in commands:
            parser.add_command(command)


@hookimpl(wrapper=True, specname="canary_addoption")
def default_canary_addoption(parser: "Parser") -> Generator[None, None, None]:
    with monkeypatch.context() as mp:
        mp.setattr(parser, "add_argument", parser.add_plugin_argument)
        mp.setattr(parser, "add_argument_group", parser.add_plugin_argument_group)
        yield


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_generator(
    root: str, path: str | None
) -> Generator[None, Any, AbstractTestGenerator | None]:
    res = yield
    if isinstance(res, type) and issubclass(res, AbstractTestGenerator):
        # old style hook returns a type, not the instance
        if res.matches(root if path is None else os.path.join(root, path)):
            return res(root, path=path)
    elif isinstance(res, AbstractTestGenerator):
        return res
    if generator := config.pluginmanager.hook.canary_generator(root=root, path=path):
        return generator
    return None


# ---- COMMAND LINE PARSING
@hookimpl(trylast=True)
def canary_cmdline_parse(parser: "Parser", args: list[str]) -> argparse.Namespace:
    """Expand command aliases and parse Canary command-line arguments.

    Looks for the first non-option argument in ``args`` and treats it as a
    potential Canary command alias. If the command matches an entry in the
    configured ``aliases`` mapping, the alias is expanded in place before
    delegating to ``parser.parse_args``.

    Alias strings are parsed as shell-like command fragments using
    ``shlex.split``. Template substitutions are performed with
    ``string.Template.safe_substitute``. The following template variables are
    supported:

    * ``$@``: Expands to the remaining command-line arguments after the alias.
      This is normalized internally to ``${args}`` before template expansion.
    * ``$canary``: Expands to the installed Canary package prefix.

    Unlike git's ordinary aliases, additional command-line arguments are not
    appended automatically after alias expansion. They are inserted only when
    the alias explicitly contains ``$@``.

    Examples:
        Given an alias such as::

            aliases:
              rwe: run -w $@ $canary/examples

        The command::

            canary rwe --my-args --are-these --and this

        is expanded before parsing to approximately::

            canary run -w --my-args --are-these --and this /path/to/canary/examples

    Args:
        parser: The Canary argument parser.
        args: Command-line arguments to parse. This list is modified in place
            if an alias expansion is performed.

    Returns:
        The parsed argparse namespace.

    Raises:
        RuntimeError: If an alias uses ``$canary`` and the Canary package
            prefix cannot be determined.
    """
    from . import config

    if aliases := config.get("aliases"):
        canary_prefix = get_canary_prefix()
        for i, arg in enumerate(args):
            if arg.startswith("-"):
                continue
            alias = aliases.get(arg)
            if not alias:
                break
            extra_args = args[i + 1 :]
            alias = alias.replace("$@", "${args}")
            expanded = Template(alias).safe_substitute(
                args=shlex.join(extra_args), canary=shlex.quote(str(canary_prefix))
            )
            args[i:] = shlex.split(expanded)
            break
    return parser.parse_args(args)


# ---- SESSION ARCHIVE
@hookimpl(specname="canary_addoption")
def add_archive_options(parser: Parser) -> None:
    parser.add_argument(
        "--archive",
        metavar="NAME",
        dest="archive_name",
        command="run",
        help="Archive job artifacts to a tgz archive by this name",
    )


@hookimpl(specname="canary_sessionfinish")
def archive_on_completion(session: Session) -> None:
    f = config.getoption("archive_name")
    if f is None:
        return
    dest = Path(f)
    mode: Literal["w:gz", "w"] = "w:gz" if str(dest).endswith((".tgz", ".tar.gz")) else "w"
    prefix = Path(session.prefix)
    dest.parent.mkdir(exist_ok=True, parents=True)
    seen: set[Path] = set()
    with tarfile.open(dest, mode, dereference=True) as tf:
        for job in session.jobs:
            if not job.workspace.dir.exists():
                continue
            for artifact in job.spec.artifacts:
                if not artifact.active(job.status):
                    continue
                for path in job.workspace.dir.glob(artifact.pattern):
                    rp = path.resolve()
                    if rp in seen:
                        continue
                    seen.add(rp)
                    relpath: Path
                    if path.is_relative_to(prefix):
                        relpath = path.relative_to(prefix)
                    else:
                        tmp = job.workspace.dir / path.relative_to(job.spec.file.parent)
                        relpath = tmp.relative_to(prefix)
                    tf.add(path, arcname=str(relpath), recursive=True)


# ---- OUTPUT CAPTURING
@hookimpl(specname="canary_addoption")
def add_show_capture_options(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        nargs="?",
        choices=("o", "e", "oe", "no"),
        group="console reporting",
        command="run",
        default="no",
        const="oe",
        help="Show captured stdout (o), stderr (e), or both (oe) "
        "for failed tests [default: %(default)s]",
    )


@hookimpl(specname="canary_sessionfinish", trylast=True)
def show_capture(session: "Session") -> None:
    what = config.getoption("show_capture")
    if what in ("no", None):
        return
    jobs = session.jobs
    failed = [job for job in jobs if job.status.is_failure()]
    if failed:
        _, width = terminal_size()
        string = f" {len(failed)} Test failures ".center(width, "=")
        rich.print(f"[bold red]{string}[/bold red]", end="\n\n")
        for job in failed:
            _show_capture(job, what=what)


def _show_capture(job: "Job", what="oe") -> None:
    _, width = terminal_size()
    fp = io.StringIO()
    fp.write("-" * width)
    fp.write(f"[bold]Status[/bold]: {job.status.display_name(style='rich')}\n")
    fp.write(f"[bold]Execution directory[/bold]: {job.workspace.dir}\n")
    command = job.get_attribute("command")
    fp.write(f"[bold]Command[/bold]: {command}\n")
    if what in ("o", "oe") and job.stdout:
        file = job.workspace.joinpath(job.stdout)
        if os.path.exists(file):
            with open(file) as fh:
                stdout = fh.read().strip()
            if stdout:
                fp.write("[bold]stdout[/bold]\n")
                fp.write(indent(stdout, "  ") + "\n")
    if what in ("e", "oe") and job.stderr:
        file = job.workspace.joinpath(job.stderr)
        if os.path.exists(file):
            with open(file) as fh:
                stderr = fh.read().strip()
            if stderr:
                fp.write("[bold]stderr[/bold]\n")
                fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        rich.print(text)


def get_canary_prefix() -> Path | None:
    spec = importlib.util.find_spec("canary")
    if spec is not None:
        if spec.submodule_search_locations:
            return Path(next(iter(spec.submodule_search_locations))).resolve()
        if spec.origin:
            return Path(spec.origin).resolve().parent
    return None


# ---- EMAIL
@hookimpl(specname="canary_addoption")
def add_mail_to_options(parser: Parser) -> None:
    parser.add_argument(
        "--mail-to",
        command="run",
        help="Send a test session summary to the comma separated list of email addresses",
    )
    parser.add_argument("--mail-from", command="run", help="Send mail from this user")


@hookimpl(trylast=True, specname="canary_sessionfinish")
def mail_on_finish(session: "Session") -> None:
    mail_to = config.getoption("mail_to")
    if mail_to is None:
        return
    sendaddr = config.getoption("mail_from")
    if sendaddr is None:
        raise RuntimeError("missing required argument --mail-from")
    recvaddrs = [_.strip() for _ in mail_to.split(",") if _.split()]
    html_report = generate_html_report(session)
    subject = "Canary Summary"
    logger.info(f"Sending summary to {', '.join(recvaddrs)}")
    sendmail(sendaddr, recvaddrs, subject, html_report, subtype="html")


def generate_html_report(session: "Session") -> str:
    totals: dict[str, list["Job"]] = {}
    for job in session.jobs:
        group = job.status.category.title()
        totals.setdefault(group, []).append(job)
    file = io.StringIO()
    file.write("<html><head><style>\n")
    file.write("table{font-family:arial,sans-serif;border-collapse:collapse;}\n")
    file.write("td, th {border: 1px solid #dddddd; text-align: left; ")
    file.write("padding: 8px; width: 100%}\n")
    file.write("tr:nth-child(even) {background-color: #dddddd;}\n")
    file.write("</style>")
    file.write("<body>\n<h1>Canary test summary</h1>\n<table>\n")
    file.write("<tr><th>Test</th><th>Duration</th><th>Status</th></tr>\n")
    for group, jobs in totals.items():
        for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
            file.write(
                f"<tr><td>{job.display_name()}</td>"
                f"<td>{job.timekeeper.duration():.2f}</td>"
                f"<td>{job.status.display_name(style='html')}</td></tr>\n"
            )
    file.write("</table>\n</body>\n</html>")
    return file.getvalue()


# ---- TEARDOWN
@hookimpl(specname="canary_addoption")
def add_teardown_options(parser: "Parser") -> None:
    parser.add_argument(
        "--teardown",
        "--post-clean",
        command="run",
        action="store_true",
        default=None,
        help="Clean up files created by a test if it finishes successfully [default: %(default)s]",
    )


@hookimpl(trylast=True, specname="canary_sessionfinish")
def teardown_session(session: "Session") -> None:
    if config.getoption("teardown"):
        workspace = Workspace.load()
        workspace.gc()


# ---- REPEAT
@hookimpl(specname="canary_addoption")
def add_repeat_options(parser: "Parser") -> None:
    group = "repeat"
    parser.add_argument(
        "--repeat-until-pass",
        type=int,
        metavar="N",
        command="run",
        group=group,
        help="Allow each test to run up to N times in order to pass",
    )
    parser.add_argument(
        "--repeat-after-timeout",
        type=int,
        metavar="N",
        command="run",
        group=group,
        help="Allow each test to run up to N times if it times out",
    )
    parser.add_argument(
        "--repeat-until-fail",
        type=int,
        metavar="N",
        command="run",
        group=group,
        help="Require each test to run N times without failing in order to pass",
    )


@hookimpl(specname="canary_runtest")
def repeat_until_pass(case: "Job") -> None:
    if case.status.is_failure() and (count := config.getoption("repeat_until_pass")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, i)
            if case.status.is_success():
                return
        logger.error(
            f"{case}: failed to finish successfully after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_runtest")
def repeat_after_timeout(case: "Job") -> None:
    if case.status.is_timeout() and (count := config.getoption("repeat_after_timeout")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, i)
            if not case.status.is_timeout():
                return
        logger.error(
            f"{case}: failed to finish without timing out after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_runtest")
def repeat_until_fail(case: "Job") -> None:
    if case.status.is_success() and (count := config.getoption("repeat_until_fail")):
        i: int = 1
        while i < count:
            i += 1
            rerun_case(case, i)
            if not case.status.is_success():
                break
        else:
            return
        n: int = count
        logger.error(
            f"{case}: failed to finish successfully {n} {pluralize('time', n)} without failing"
        )


# ---- RERUN
def rerun_case(job: "Job", attempt: int) -> None:
    try:
        job.restore_workspace()
        if summary := job_start_summary(job):
            logger.debug(summary)
        job.setup()
        job.run()
    finally:
        if summary := job_finish_summary(job, attempt=attempt):
            logger.debug(summary)


def job_start_summary(job: "Job") -> str:
    if logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    fmt.write("[bold]Repeating[/] %s: %s" % (job.id[:7], job.display_name(resolve=True)))
    return fmt.getvalue().strip()


def job_finish_summary(job: "Job", *, attempt: int) -> str:
    if logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    fmt.write(
        f"[bold]Finished[/] %s (attempt {attempt + 1}): %s %s"
        % (job.id[:7], job.display_name(resolve=True), job.status.display_name())
    )
    return fmt.getvalue().strip()


@hookimpl
def canary_capabilities() -> dict[str, Any] | None:
    return load_query_data("canary.data", "capabilities.json")


@hookimpl
def canary_skills() -> dict[str, Any] | None:
    return load_query_data("canary.data", "skills.json")


# ---------------------------------------------------------------------------
# Built-in canary query subcommand handlers
# ---------------------------------------------------------------------------
# Each function handles exactly one value of args.query_subcmd and returns
# None for any other value so pluggy can try the next implementation.


@hookimpl(trylast=True, specname="canary_query_execute")
def query_execute_job(args: "argparse.Namespace") -> "int | None":
    """Handle ``canary query job``."""
    if getattr(args, "query_subcmd", None) != "job":
        return None
    from .subcommands.query import _exec_job

    return _exec_job(args)


@hookimpl(trylast=True, specname="canary_query_execute")
def query_execute_session(args: "argparse.Namespace") -> "int | None":
    """Handle ``canary query session``."""
    if getattr(args, "query_subcmd", None) != "session":
        return None
    from .subcommands.query import _exec_session

    return _exec_session(args)


@hookimpl(trylast=True, specname="canary_query_execute")
def query_execute_sessions(args: "argparse.Namespace") -> "int | None":
    """Handle ``canary query sessions``."""
    if getattr(args, "query_subcmd", None) != "sessions":
        return None
    from .subcommands.query import _exec_sessions

    return _exec_sessions(args)


@hookimpl(trylast=True, specname="canary_query_execute")
def query_execute_db(args: "argparse.Namespace") -> "int | None":
    """Handle ``canary query db``."""
    if getattr(args, "query_subcmd", None) != "db":
        return None
    from .subcommands.query import _exec_db

    return _exec_db(args)
