# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Generator

import canary
from _canary.util.query_data import load_query_data
from _canary.util.string import csvsplit

from .cdash_html_summary import cdash_summary
from .gitlab_issue_generator import create_issues_from_failed_tests
from .xmlreporter import CDashXMLReporter


@canary.hookimpl
def canary_reporter() -> canary.CanaryReporter:
    return CDashReporter()


@canary.hookimpl
def canary_capabilities() -> dict[str, Any] | None:
    return load_query_data("canary_cdash.data", "capabilities.json")


@canary.hookimpl
def canary_skills() -> dict[str, Any] | None:
    return load_query_data("canary_cdash.data", "skills.json")


class CDashReporter(canary.CanaryReporter):
    type = "cdash"
    description = "CDash reporter"

    def setup_parser(self, parser: "canary.Parser") -> None:
        sp = parser.add_subparsers(dest="action", metavar="subcommands", required=True)

        p = sp.add_parser("create", help="Create CDash XML files")
        self.setup_create_parser(p)
        p.set_defaults(_cdash_handler=self.run_create)

        p = sp.add_parser("post", help="Post CDash XML files")
        self.setup_post_parser(p)
        p.set_defaults(_cdash_handler=self.run_post)

        p = sp.add_parser("summary", help="Generate an html summary of the CDash dashboard")
        self.setup_summary_parser(p)
        p.set_defaults(_cdash_handler=self.run_summary)

        p = sp.add_parser("make-gitlab-issues", help="Create GitLab issues for failed tests")
        self.setup_make_gitlab_issues_parser(p)
        p.set_defaults(_cdash_handler=self.run_make_gitlab_issues)

    def run_from_args(self, args: Namespace) -> int:
        handler: Callable[[Namespace], None] | None = getattr(args, "_cdash_handler", None)
        if handler is None:
            raise ValueError("canary report cdash: missing action")
        handler(args)
        return 0

    def setup_create_parser(self, parser: "canary.Parser") -> None:
        parser.add_argument(
            "--name-format",
            choices=("short", "long"),
            default="short",
            help="Name as shown on the CDash landing page  [default: %(default)s]",
        )
        parser.add_argument(
            "--build",
            dest="buildname",
            metavar="name",
            help="The name of the build that will be reported to CDash.",
        )
        parser.add_argument(
            "--site",
            metavar="name",
            help="The site name that will be reported to CDash. [default: current system hostname]",
        )
        parser.add_argument(
            "-f",
            metavar="file",
            help="Read site, build, and buildstamp from this XML file (eg, Build.xml or Configure.xml)",
        )
        parser.add_argument(
            "-d",
            dest="dest",
            metavar="directory",
            help="Write reports to this directory [default: $session/_reports/cdash]",
        )

        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--track",
            metavar="track",
            help="Results will be reported to this group on CDash [default: Experimental]",
        )
        group.add_argument(
            "--build-stamp",
            dest="buildstamp",
            metavar="stamp",
            help=(
                "Instead of letting the CDash reporter prepare the buildstamp which, "
                "when combined with build name, site and project, uniquely identifies the "
                "build, provide this argument to identify the build yourself. "
                "Format: %%Y%%m%%d-%%H%%M-<track>"
            ),
        )

        parser.add_argument(
            "-n",
            dest="chunk_size",
            default=500,
            type=int,
            metavar="CHUNK_SIZE",
            action="store",
            help=(
                "The results will be split into chunks of N entries per XML file. "
                "If N is -1 the XML will be not be split and will be stored as a single file."
            ),
        )
        parser.add_argument(
            "-L",
            metavar="LABEL",
            action="append",
            dest="subproject_labels",
            help="Label that will be treated as a subproject",
        )
        parser.add_argument(
            "--subproject-labels",
            metavar="LABELS",
            action=SubprojectLabels,
            help="Comma-separated list of labels that will be treated as subprojects",
        )

    def setup_post_parser(self, parser: "canary.Parser") -> None:
        parser.add_argument(
            "--project",
            "--cdash-project",
            required=True,
            dest="cdash_project",
            help="The CDash project",
        )
        parser.add_argument(
            "--url",
            "--cdash-url",
            dest="cdash_url",
            required=True,
            help="The base CDash url (do not include project)",
        )
        parser.add_argument(
            "--done", action="store_true", default=False, help="Post Done.xml to the build."
        )
        parser.add_argument("files", nargs="*", help="XML files to post")

    def setup_summary_parser(self, parser: "canary.Parser") -> None:
        parser.add_argument(
            "--project", "--cdash-project", dest="cdash_project", help="The CDash project"
        )
        parser.add_argument(
            "--url",
            "--cdash-url",
            dest="cdash_url",
            help="The base CDash url (do not include project)",
        )
        parser.add_argument(
            "-t",
            "--track",
            default=None,
            dest="track",
            action="append",
            help="CDash build groups to pull from CDash [default: all]",
        )
        parser.add_argument(
            "-m",
            "--mailto",
            default=None,
            action="append",
            help="Email addresses to send the summary.",
        )
        parser.add_argument(
            "-s",
            "--skip-site",
            default=None,
            action="append",
            metavar="SKIP_SITE",
            help="Sites to skip (accepts Python regular expression)",
        )
        parser.add_argument(
            "-o", dest="output", help="Filename to write the html summary [default: stdout]"
        )

    def setup_make_gitlab_issues_parser(self, parser: "canary.Parser") -> None:
        parser.add_argument(
            "--cdash-url", required=True, help="The base CDash url, do not include project"
        )
        parser.add_argument("--cdash-project", required=True, help="The base CDash project")
        parser.add_argument("--gitlab-url", required=True, help="The GitLab project url")
        parser.add_argument("--gitlab-api-url", required=True, help="The GitLab project's API url")
        parser.add_argument(
            "--gitlab-project-id", type=int, required=True, help="The GitLab project's ID"
        )
        parser.add_argument(
            "-a", dest="access_token", help="The GitLab read/write API access token."
        )
        parser.add_argument("-d", "--date", help="Date to retrieve from CDash")
        parser.add_argument(
            "-f",
            "--filtergroups",
            dest="filter_groups",
            action="append",
            help="Groups to pull down from CDash",
        )
        parser.add_argument(
            "--skip-site",
            default=None,
            action="append",
            metavar="SKIP_SITE",
            help="Sites to skip (accepts Python regular expression)",
        )
        parser.add_argument(
            "--dont-close-missing",
            default=False,
            action="store_true",
            help="Don't close issues belonging to missing tests",
        )

    def run_create(self, args: Namespace) -> None:
        reporter: CDashXMLReporter = CDashXMLReporter.from_workspace(dest=args.dest)

        if args.f:
            opts = {"buildstamp": args.buildstamp, "track": args.track, "buildname": args.buildname}
            if any(opts.values()):
                s = ", ".join(opts.keys())
                raise ValueError(f"-f {args.f!r} incompatible with {s}")

            ns = reporter.read_site_info(args.f)

            if ns.subproject_labels and args.subproject_labels:
                args.subproject_labels = [*ns.subproject_labels, *args.subproject_labels]
            else:
                for key, val in vars(ns).items():
                    setattr(args, key, val)

        reporter.create(
            args.buildname,
            site=args.site,
            track=args.track,
            buildstamp=args.buildstamp,
            generator=getattr(args, "generator", None),
            chunk_size=args.chunk_size,
            subproject_labels=args.subproject_labels,
        )

    def run_post(self, args: Namespace) -> None:
        cdash_url = args.cdash_url
        cdash_project = args.cdash_project
        done = args.done or False
        files = list(args.files or [])

        if files:
            url = CDashXMLReporter.post(cdash_url, cdash_project, *files, done=done)
            # Write URL to stdout so tools can do:
            #   cdash_url=$(canary report cdash post ...)
            sys.stdout.write(f"{url}\n")
            return

        reporter = CDashXMLReporter.from_workspace(dest=None)
        files.extend(glob.glob(os.path.join(reporter.dest, "*.xml")))

        if not files:
            raise ValueError("canary report cdash post: no xml files to post")

        url = reporter.post(cdash_url, cdash_project, *files, done=done)
        sys.stdout.write(f"{url}\n")

    def run_summary(self, args: Namespace) -> None:
        cdash_summary(
            url=args.cdash_url,
            project=args.cdash_project,
            buildgroups=args.track,
            mailto=args.mailto,
            file=args.output,
            skip_sites=args.skip_site,
        )

    def run_make_gitlab_issues(self, args: Namespace) -> None:
        create_issues_from_failed_tests(
            access_token=args.access_token,
            cdash_url=args.cdash_url,
            cdash_project=args.cdash_project,
            gitlab_url=args.gitlab_url,
            gitlab_project_id=args.gitlab_project_id,
            date=args.date,
            filtergroups=args.filter_groups,
            skip_sites=args.skip_site,
            dont_close_missing=args.dont_close_missing,
        )


class SubprojectLabels(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        values = getattr(namespace, self.dest, None) or []
        values.extend(csvsplit(value))
        setattr(namespace, self.dest, values)


class CDashHooks:
    @canary.hookspec
    def canary_cdash_labels_for_subproject(self) -> list[str] | None:
        """Return a list of subproject labels to be added to Test.xml reports"""
        ...

    @canary.hookspec(firstresult=True)
    def canary_cdash_subproject_label(self, case: "canary.Job") -> str | None:
        """Return a subproject label for ``case`` that will be added in Test.xml reports"""
        ...

    @canary.hookspec(firstresult=True)
    def canary_cdash_labels(self, case: "canary.Job") -> list[str] | None:
        """Return CDash labels for ``case``"""
        ...

    @canary.hookspec
    def canary_cdash_artifacts(self, case: "canary.Job") -> list[dict[str, str]] | None:
        """Return artifacts to transmit to CDash"""
        ...

    @canary.hookspec(firstresult=True)
    def canary_cdash_name(self, case: "canary.Job") -> str | None:
        """Return the name to use on CDash"""
        ...

    @canary.hookspec
    def canary_cdash_named_measurements(self, case: "canary.Job") -> dict[str, Any] | None:
        """Return measurements to post to CDash"""
        ...


@canary.hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager"):
    pluginmanager.add_hookspecs(CDashHooks)


@canary.hookimpl(trylast=True)
def canary_cdash_labels(case: canary.Job) -> list[str]:
    """Default implementation: return the test case's keywords"""
    return list(case.spec.keywords)


@canary.hookimpl(trylast=True)
def canary_cdash_name(case: canary.Job) -> str:
    """Default implementation: return the test case's keywords"""
    if not case.spec.parameters:
        return case.spec.family
    s_params = case.spec.s_params()
    return f"{case.spec.family}[{s_params}]"


@canary.hookimpl(wrapper=True)
def canary_cdash_artifacts(case: canary.Job) -> Generator[None, list[str], list[str]]:
    result = yield
    candidates: set[str] = {a for b in result for a in b if b}
    artifacts: list[str] = []
    for candidate in candidates:
        f = Path(candidate)
        if f.exists():
            artifacts.append(f.absolute().as_posix())
        elif case.workspace.joinpath(f).exists():
            artifacts.append(case.workspace.joinpath(f).as_posix())
    return artifacts


@canary.hookimpl(wrapper=True)
def canary_cdash_named_measurements(
    case: canary.Job,
) -> Generator[None, list[dict[str, Any]], dict[str, Any]]:
    measurements: dict[str, Any] = {}
    result = yield
    for item in result:
        if item:
            measurements.update(item)
    return measurements
