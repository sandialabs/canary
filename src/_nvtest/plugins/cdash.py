import argparse
import os

from _nvtest.io.cdash import Reporter as CDashReporter

description = "Write CDash XML files and (optionally) post to CDash"


def setup_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--url",
        help="Base url to CDash site (required to post to CDash)",
    )
    parser.add_argument(
        "--project",
        help="CDash project name (required to post to CDash)",
    )
    parser.add_argument("--buildname", default="Build", help="CDash build name")
    parser.add_argument(
        "--buildgroup",
        default="Experimental",
        help="Cdash build group [default: %(default)s]",
    )
    parser.add_argument(
        "--site", default=os.uname().nodename, help="Cdash site [default: %(default)s]"
    )
    parser.add_argument(
        "--dest",
        default="./cdash",
        help="Where to write CDash files [default: %(default)s]",
    )
    parser.add_argument(
        "-f", action="append", dest="files", help="nvtest Json test file"
    )


def cdash(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Collects data from bnb jobs and writes reports"""
    with CDashReporter(
        cdash_baseurl=args.url,
        cdash_project=args.project,
        cdash_buildname=args.buildname,
        cdash_buildgroup=args.buildgroup,
        cdash_site=args.site,
        dest=args.dest,
        files=args.files,
    ) as rc:
        rc.create_cdash_reports()
    return rc.returncode
