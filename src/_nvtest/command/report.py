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
    p.add_argument(
        "--project",
        required=True,
        help="The name of the project that will be reported to CDash",
    )
    p.add_argument(
        "--build",
        required=True,
        help="The name of the build that will be reported to CDash.",
    )
    p.add_argument(
        "--site",
        help=" The site name that will be reported to CDash "
        "[default: current system hostname]",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--track",
        help="Results will be reported to this group on CDash [default: Experimental]",
    )
    group.add_argument(
        "--build-stamp",
        help="Instead of letting the CDash reporter prepare the buildstamp which, "
        "when combined with build name, site and project, uniquely identifies the "
        "build, provide this argument to identify the build yourself. "
        "Format: %%Y%%m%%d-%%H%%M-<track>",
    )

    p = sp.add_parser("post", help="Post CDash XML files")
    p.add_argument("url", help="The URL of the CDash server")

    p = sp.add_parser("summary", help="Create HTML summary of CDash site")
    p.add_argument(
        "--url",
        required=True,
        help="CDash URL",
    )
    p.add_argument(
        "--project",
        required=True,
        help="The name of the CDash project",
    )
    p.add_argument(
        "-t",
        action="append",
        dest="build_groups",
        help="CDash build groups to fetch",
    )
    p.add_argument(
        "-s",
        action="append",
        dest="skip_sites",
        help="Skip builds from these sites",
    )
    p.add_argument(
        "-m",
        action="append",
        dest="mailto",
        help="mail report to these addresses",
    )
    p.add_argument(
        "-o",
        dest="file",
        help="write report to this file",
    )

    html_parser = parent.add_parser("html", help="Generate HTML reports")
    sp = html_parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create local HTML report files")


def report(args: "Namespace") -> int:
    if args.parent_command == "cdash" and args.child_command == "summary":
        cdash.cdash_summary(
            url=args.url,
            project=args.project,
            buildgroups=args.build_groups,
            mailto=args.mailto,
            skip_sites=args.skip_sites,
            file=args.file,
        )
        return 0
    if not config.get("session:work_tree"):
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    reporter: Reporter
    if args.parent_command == "cdash":
        reporter = cdash.Reporter(session)
        if args.child_command == "create":
            reporter.create(
                args.project,
                args.build,
                site=args.site,
                track=args.track,
                build_stamp=args.build_stamp,
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
