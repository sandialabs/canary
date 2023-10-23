from typing import TYPE_CHECKING

from ..config.argparsing import identity
from ..reporters import cdash
from ..session import Session

if TYPE_CHECKING:
    from argparse import Namespace

    from ..config import Config
    from ..config.argparsing import Parser


description = "Generate test reports"


def setup_parser(parser: "Parser") -> None:
    sp = parser.add_subparsers(dest="subcommand", metavar="")
    p = sp.add_parser(
        "cdash", help="Write CDash XML files and (optionally) post to CDash."
    )
    p.register("type", None, identity)
    p.add_argument("--url", help="The URL of the CDash server")
    p.add_argument("-p", "--project", help="The project name")
    p.add_argument("-t", "--track", help="The CDash build track (group)")
    p.add_argument("--site", help="The host tests were run on")
    p.add_argument("--stamp", help="The timestamp of the build")
    p.add_argument("--build", help="The build name")
    p.add_argument("workdir", help="Test results directory")


def report(config: "Config", args: "Namespace") -> int:
    session = Session.load(workdir=args.workdir, config=config, mode="r")
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
    raise ValueError(f"{args.subcommand}: unknown subcommand")
