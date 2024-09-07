from argparse import Namespace

from ..config.argparsing import Parser
from . import cdash
from . import gitlab
from . import html
from . import json
from . import junit
from . import markdown


def setup_parsers(parser: Parser) -> None:
    parent = parser.add_subparsers(dest="parent_command", metavar="")

    p = parent.add_parser("cdash", help="Generate cdash report")
    cdash.setup_parser(p)

    p = parent.add_parser("gitlab-mr", help="Generate gitlab-mr report")
    gitlab.setup_parser(p)

    p = parent.add_parser("html", help="Generate html report")
    html.setup_parser(p)

    p = parent.add_parser("json", help="Generate json report")
    json.setup_parser(p)

    p = parent.add_parser("junit", help="Generate junit report")
    junit.setup_parser(p)

    p = parent.add_parser("markdown", help="Generate markdown report")
    markdown.setup_parser(p)


def main(args: Namespace) -> int:
    if args.parent_command == "cdash":
        return cdash.create_reports(args)
    elif args.parent_command == "gitlab-mr":
        return gitlab.create_report(args)
    elif args.parent_command == "html":
        return html.create_report(args)
    elif args.parent_command == "json":
        return json.create_report(args)
    elif args.parent_command == "junit":
        return junit.create_report(args)
    elif args.parent_command == "markdown":
        return markdown.create_report(args)
    else:
        raise ValueError(f"nvtest report: unknown subcommand {args.parent_command!r}")
