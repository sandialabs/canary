import argparse
import glob
import os

from _nvtest.reporter import Reporter
from _nvtest.session import Session
from _nvtest.util import logging

from .cdash_html_summary import cdash_summary
from .gitlab_issue_generator import create_issues_from_failed_tests
from .xml_generator import CDashXMLReporter


class CDashReporter(Reporter):
    @staticmethod
    def description() -> str:
        return "Create and post reports to CDash"

    @staticmethod
    def label() -> str:
        return "cdash"

    @staticmethod
    def setup_parser(parser):
        sp = parser.add_subparsers(dest="child_command", metavar="")
        p = sp.add_parser("create", help="Create CDash XML files")
        p.add_argument(
            "--build",
            dest="buildname",
            metavar="name",
            help="The name of the build that will be reported to CDash.",
        )
        p.add_argument(
            "--site",
            metavar="name",
            help="The site name that will be reported to CDash. [default: current system hostname]",
        )
        p.add_argument(
            "-f",
            metavar="file",
            help="Read site, build, and buildstamp from this XML "
            "file (eg, Build.xml or Configure.xml)",
        )
        p.add_argument(
            "-d",
            metavar="directory",
            help="Write reports to this directory [default: $session/_reports/cdash]",
        )
        p.add_argument(
            "-j",
            dest="json",
            metavar="file",
            help="Create reports from this JSON file [default: $session/_reports/cdash]",
        )
        group = p.add_mutually_exclusive_group()
        group.add_argument(
            "--track",
            metavar="track",
            help="Results will be reported to this group on CDash [default: Experimental]",
        )
        group.add_argument(
            "--build-stamp",
            dest="buildstamp",
            metavar="stamp",
            help="Instead of letting the CDash reporter prepare the buildstamp which, "
            "when combined with build name, site and project, uniquely identifies the "
            "build, provide this argument to identify the build yourself. "
            "Format: %%Y%%m%%d-%%H%%M-<track>",
        )

        p = sp.add_parser("post", help="Post CDash XML files")
        p.add_argument(
            "--project",
            "--cdash-project",
            required=True,
            dest="cdash_project",
            help="The CDash project",
        )
        p.add_argument(
            "--url",
            "--cdash-url",
            dest="cdash_url",
            required=True,
            help="The base CDash url (do not include project)",
        )
        p.add_argument("files", nargs="*", help="XML files to post")

        p = sp.add_parser("summary", help="Generate an html summary of the CDash dashboard")
        p.add_argument(
            "--project", "--cdash-project", dest="cdash_project", help="The CDash project"
        )
        p.add_argument(
            "--url",
            "--cdash-url",
            dest="cdash_url",
            help="The base CDash url (do not include project)",
        )
        p.add_argument(
            "-t",
            "--track",
            default=None,
            dest="tracks",
            action="append",
            help="CDash build groups to pull from CDash [default: all]",  # noqa: E501
        )
        p.add_argument(
            "-m",
            "--mailto",
            default=None,
            action="append",
            help="Email addresses to send the summary.",
        )
        p.add_argument(
            "-s",
            "--skip-site",
            default=None,
            action="append",
            dest="skip_sites",
            metavar="SKIP_SITE",
            help="Sites to skip (accepts Python regular expression)",
        )
        p.add_argument("-o", help="Filename to write the html summary [default: stdout]")
        p = sp.add_parser("make-gitlab-issues", help="Create GitLab issues for failed tests")
        p.add_argument(
            "--cdash-url", required=True, help="The base CDash url, do not include project"
        )
        p.add_argument("--cdash-project", required=True, help="The base CDash project")
        p.add_argument("--gitlab-url", required=True, help="The GitLab project url")
        p.add_argument("--gitlab-api-url", required=True, help="The GitLab project's API url")
        p.add_argument(
            "--gitlab-project-id", type=int, required=True, help="The GitLab project's ID"
        )
        p.add_argument("-a", dest="access_token", help="The GitLab read/write API access token.")
        p.add_argument("-d", "--date", help="Date to retrieve from CDash")
        p.add_argument(
            "-f",
            "--filtergroups",
            dest="filter_groups",
            action="append",
            help="Groups to pull down from CDash",
        )
        p.add_argument(
            "--skip-site",
            default=None,
            dest="skip_sites",
            action="append",
            metavar="SKIP_SITE",
            help="Sites to skip (accepts Python regular expression)",
        )
        p.add_argument(
            "--dont-close-missing",
            default=False,
            action="store_true",
            help="Don't close issues belonging to missing tests",
        )

    def execute(self, args: argparse.Namespace) -> None:
        if args.child_command == "post" and args.files:
            url = CDashXMLReporter.post(args.cdash_url, args.cdash_project, *args.files)
            print(url)
            return
        elif args.child_command == "summary":
            cdash_summary(
                url=args.cdash_url,
                project=args.cdash_project,
                buildgroups=args.tracks,
                mailto=args.mailto,
                file=args.o,
                skip_sites=args.skip_sites,
            )
            return
        elif args.child_command == "make-gitlab-issues":
            create_issues_from_failed_tests(
                access_token=args.access_token,
                cdash_url=args.cdash_url,
                cdash_project=args.cdash_project,
                gitlab_url=args.gitlab_url,
                gitlab_project_id=args.gitlab_project_id,
                date=args.date,
                filtergroups=args.filter_groups,
                skip_sites=args.skip_sites,
                dont_close_missing=args.dont_close_missing,
            )
            return
        else:
            if args.json:
                reporter = CDashXMLReporter.from_json(file=args.json, dest=args.d)
            else:
                with logging.level(logging.WARNING):
                    session = Session(os.getcwd(), mode="r")
                reporter = CDashXMLReporter(session, dest=args.d)
            if args.child_command == "create":
                if args.f:
                    opts = dict(
                        buildstamp=args.buildstamp,
                        track=args.track,
                        buildname=args.buildname,
                    )
                    if any(list(opts.values())):
                        s = ", ".join(list(opts.keys()))
                        raise ValueError(f"-f {args.f!r} incompatible with {s}")
                    reporter.read_site_info(args.f, namespace=args)
                reporter.create(
                    args.buildname,
                    site=args.site,
                    track=args.track,
                    buildstamp=args.buildstamp,
                    generator=getattr(args, "generator", None),
                )
            elif args.child_command == "post":
                if not args.files:
                    args.files = glob.glob(os.path.join(reporter.xml_dir, "*.xml"))
                if not args.files:
                    raise ValueError("nvtest report cdash post: no xml files to post")
                url = reporter.post(args.cdash_url, args.cdash_project, *args.files)
                logging.info(f"Files uploaded to {url}")
            else:
                raise ValueError(f"{args.child_command}: unknown `nvtest report cdash` subcommand")
            return
