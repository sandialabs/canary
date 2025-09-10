# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import os
import sys
from typing import Any

import canary
from _canary.util.string import csvsplit

from .cdash_html_summary import cdash_summary
from .gitlab_issue_generator import create_issues_from_failed_tests
from .xmlreporter import CDashXMLReporter


class CDashReporter(canary.CanaryReporter):
    type = "cdash"
    description = "CDash reporter"
    multipage = True

    def setup_parser(self, parser: "canary.Parser"):
        sp = parser.add_subparsers(dest="action", metavar="subcommands")
        p = sp.add_parser("create", help="Create CDash XML files")
        p.add_argument(
            "--name-format",
            choices=("short", "long"),
            default="short",
            help="Name as shown on the CDash landing page  [default: %(default)s]",
        )
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
            help="Read site, build, and buildstamp from this XML file (eg, Build.xml or Configure.xml)",
        )
        p.add_argument(
            "-d",
            dest="dest",
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
        p.add_argument(
            "-n",
            dest="chunk_size",
            default=500,
            type=int,
            metavar="CHUNK_SIZE",
            action="store",
            help="The results will be split into chunks of N entries per XML file. "
            "If N is -1 the XML will be not be split and will be stored as a single file.",
        )
        p.add_argument(
            "-L",
            metavar="LABEL",
            action="append",
            dest="subproject_labels",
            help="Label that will be treated as a subproject",
        )
        p.add_argument(
            "--subproject-labels",
            metavar="LABELS",
            action=SubprojectLabels,
            help="Comma-separated list of labels that will be treated as subprojects",
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
        p.add_argument(
            "--done", action="store_true", default=False, help="Post Done.xml to the build."
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
            dest="track",
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
            metavar="SKIP_SITE",
            help="Sites to skip (accepts Python regular expression)",
        )
        p.add_argument(
            "-o", dest="output", help="Filename to write the html summary [default: stdout]"
        )
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

    def post(self, session: "canary.Session | None" = None, **kwargs: Any) -> None:
        cdash_url = kwargs["cdash_url"]
        cdash_project = kwargs["cdash_project"]
        done = kwargs["done"] or False
        files = kwargs["files"] or []
        if files:
            url = CDashXMLReporter.post(cdash_url, cdash_project, *files, done=done)
            # write url to stdout so that tools can do cdash_url=$(canary report cdash post ...)
            sys.stdout.write("%s\n" % url)
        else:
            if session is None:
                raise ValueError("canary report html: session required")
            reporter = CDashXMLReporter.from_session(session, dest=kwargs["dest"])
            files.extend(glob.glob(os.path.join(reporter.dest, "*.xml")))
            if not files:
                raise ValueError("canary report cdash post: no xml files to post")
            url = reporter.post(cdash_url, cdash_project, *files, done=done)
            # write url to stdout so that tools can do cdash_url=$(canary report cdash post ...)
            sys.stdout.write("%s\n" % url)
        return

    def summary(self, session: "canary.Session | None" = None, **kwargs: Any) -> None:
        cdash_summary(
            url=kwargs["cdash_url"],
            project=kwargs["cdash_project"],
            buildgroups=kwargs["track"],
            mailto=kwargs["mailto"],
            file=kwargs["output"],
            skip_sites=kwargs["skip_site"],
        )
        return

    def make_gitlab_issues(self, session: "canary.Session | None" = None, **kwargs: Any) -> None:
        create_issues_from_failed_tests(
            access_token=kwargs["access_token"],
            cdash_url=kwargs["cdash_url"],
            cdash_project=kwargs["cdash_project"],
            gitlab_url=kwargs["gitlab_url"],
            gitlab_project_id=kwargs["gitlab_project_id"],
            date=kwargs["date"],
            filtergroups=kwargs["filter_groups"],
            skip_sites=kwargs["skip_site"],
            dont_close_missing=kwargs["dont_close_missing"],
        )
        return

    def create(self, session: "canary.Session | None" = None, **kwargs: Any) -> None:
        reporter: CDashXMLReporter
        if kwargs.get("json"):
            reporter = CDashXMLReporter.from_json(file=kwargs["json"], dest=kwargs["dest"])
        else:
            if session is None:
                raise ValueError("canary report html: session required")
            reporter = CDashXMLReporter.from_session(session, dest=kwargs["dest"])
        if kwargs["f"]:
            opts = dict(
                buildstamp=kwargs["buildstamp"],
                track=kwargs["track"],
                buildname=kwargs["buildname"],
            )
            if any(list(opts.values())):
                s = ", ".join(list(opts.keys()))
                raise ValueError(f"-f {kwargs['f']!r} incompatible with {s}")
            ns = reporter.read_site_info(kwargs["f"])
            if ns.subproject_labels and kwargs.get("subproject_labels"):
                ns.subproject_labels.extend(kwargs["subproject_labels"])
                kwargs.pop("subproject_labels")
            kwargs.update(vars(ns))
        kwargs.setdefault("chunk_size", 500)
        reporter.create(
            kwargs["buildname"],
            site=kwargs["site"],
            track=kwargs["track"],
            buildstamp=kwargs["buildstamp"],
            generator=kwargs.get("generator"),
            chunk_size=kwargs.get("chunk_size"),
            subproject_labels=kwargs.get("subproject_labels"),
        )
        return


class SubprojectLabels(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        values = getattr(namespace, self.dest, None) or []
        values.extend(csvsplit(value))
        setattr(namespace, self.dest, values)
