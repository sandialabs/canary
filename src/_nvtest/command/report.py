from typing import TYPE_CHECKING

from .. import config
from ..reporters import cdash
from ..reporters import html
from ..session import Session
from ..util import tty

if TYPE_CHECKING:
    from argparse import Namespace

    from ..config.argparsing import Parser


description = "Generate test reports"


def setup_parser(parser: "Parser") -> None:
    sp = parser.add_subparsers(dest="subcommand", metavar="")
    p = sp.add_parser(
        "cdash", help="Generate CDash XML files and (optionally) post to CDash."
    )
    p.add_argument("--url", help="The URL of the CDash server")
    p.add_argument("-p", "--project", help="The project name")
    p.add_argument("-t", "--track", help="The CDash build track (group)")
    p.add_argument("--site", help="The host tests were run on")
    p.add_argument("--stamp", help="The timestamp of the build")
    p.add_argument("--build", help="The build name")
    p = sp.add_parser("html", help="Generate local HTML files for viewing test results")


def report(args: "Namespace") -> int:
    if not config.get("session:work_tree"):
        tty.die("report must be run from a work tree")
    session = Session.load(mode="r")
    if args.subcommand == "cdash":
        cdash.report(
            session,
            buildname=args.build,
            url=args.url,
            project=args.project,
            site=args.site,
            buildgroup=args.track,
        )
        return 0
    elif args.subcommand == "html":
        html.report(session)
        return 0
    tty.die(f"{args.subcommand}: unknown subcommand")
    return 1
