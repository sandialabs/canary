from typing import TYPE_CHECKING

from .. import config
from ..reporters import Reporter
from ..reporters import cdash
from ..reporters import html
from ..session import Session
from ..util import tty

if TYPE_CHECKING:
    from argparse import Namespace

    from ..config.argparsing import Parser


description = "Generate test reports"


def setup_parser(parser: "Parser") -> None:
    parent = parser.add_subparsers(dest="parent_command", metavar="")
    cdash_parser = parent.add_parser("cdash", help="Generate and post CDash XML")
    sp = cdash_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create CDash XML files")
    p.add_argument("-p", "--project", required=True, help="The project name")
    p.add_argument("-t", "--track", help="The CDash build track (group)")
    p.add_argument("--site", help="The host tests were run on")
    p.add_argument("--stamp", help="The timestamp of the build")
    p.add_argument("--build", help="The build name")

    p = sp.add_parser("post", help="Post CDash XML files")
    p.add_argument("url", help="The URL of the CDash server")

    html_parser = parent.add_parser("html", help="Generate HTML reports")
    sp = html_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create local HTML report files")


def report(args: "Namespace") -> int:
    if not config.get("session:work_tree"):
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    reporter: Reporter
    if args.parent_command == "cdash":
        reporter = cdash.Reporter(session)
        if args.child_command == "create":
            reporter.create(
                args.project, args.build, site=args.site, buildgroup=args.track
            )
        elif args.child_command == "post":
            reporter.load()
            reporter.post(args.url)
        else:
            tty.die(f"{args.child_command}: unknown `nvtest report cdash` subcommand")
        return 0
    elif args.parent_command == "html":
        reporter = html.Reporter(session)
        if args.child_command == "create":
            reporter.create()
        else:
            tty.die(f"{args.child_command}: unknown `nvtest report html` subcommand")
        return 0
    else:
        tty.die(f"{args.parent_command}: unknown subcommand")
    return 1
