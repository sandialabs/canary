import argparse
import datetime
import importlib.resources as ir
import io
import json
from pathlib import Path

from _nvtest.config.argparsing import Parser
from _nvtest.util import gitlab
from _nvtest.util import logging

from .base import Command


class Changelog(Command):
    @property
    def description(self) -> str:
        return "Generate rst change log"

    @property
    def add_help(self) -> bool:
        return False

    def setup_parser(self, parser: Parser):
        parser.add_argument(
            "--from",
            dest="date_from",
            required=True,
            help="Generate changelog from this date forward, use YYY-MM-DD",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            required=True,
            help="Generate changelog up to this date, use YYY-MM-DD",
        )
        parser.add_argument("-o", dest="output", help="Write output to this file")
        parser.add_argument("--version", help="Generate changelog for this version")

    def execute(self, args: argparse.Namespace) -> int:
        repo = gitlab.repo(
            url="https://cee-gitlab.sandia.gov/ascic-test-infra/nvtest",
            api_url="https://cee-gitlab.sandia.gov/api/v4",
            project_id=49982,
            access_token="pzQ82ejiS1DrmRYmPKu3",
        )
        df = datetime.datetime.strptime(args.date_from, "%Y-%m-%d")
        dt = datetime.datetime.strptime(args.date_to, "%Y-%m-%d")

        logging.debug(f"Reading merge requests from {repo}")
        merge_requests: list[dict] = []
        for mr in repo.merge_requests(state="merged"):
            dm = datetime.datetime.fromisoformat(mr["merged_at"])
            if df.replace(tzinfo=dm.tzinfo) <= dm <= dt.replace(tzinfo=dm.tzinfo):
                merge_requests.append(mr)

        logging.debug(f"Reading issues from {repo}")
        issues: list[dict] = []
        for issue in repo.issues(state="closed"):
            dc = datetime.datetime.fromisoformat(issue["closed_at"])
            if df.replace(tzinfo=dc.tzinfo) <= dc <= dt.replace(tzinfo=dc.tzinfo):
                issues.append(issue)

        logging.debug(f"Reading commits from {repo}")
        commits: list[dict] = []
        for commit in repo.commits():
            dc = datetime.datetime.fromisoformat(commit["authored_date"])
            if df.replace(tzinfo=dc.tzinfo) <= dc <= dt.replace(tzinfo=dc.tzinfo):
                commits.append(commit)

        authors: dict[tuple[str, str], int] = {}
        namemap = self.get_namemap()
        for commit in commits:
            author = commit["author_name"]
            for nm in namemap:
                if nm["name"] == author:
                    break
                elif nm["username"] == author or author in nm["aliases"]:
                    author = nm["name"]
                    break
            first, *middle, last = author.split()
            authors.setdefault((first, last), 0)
            authors[(first, last)] += 1

        file = io.StringIO()
        title = f"nvtest {args.version or 'VERSION'} release notes"
        file.write("{title}\n{rule}\n\n".format(title=title, rule="=" * len(title)))
        file.write(".. contents::\n\n")
        file.write("SYNOPSIS\n\n")
        file.write("Authors\n-------\n\n")
        for author in sorted(authors, key=lambda x: x[1]):
            first, last = author
            count = authors[author]
            file.write(f"* {first} {last} ({count})\n")

        file.write(f"\nA total of {len(authors)} authors contributed {len(commits)} ")
        file.write("commits to this release.\n")

        title = f"Issues closed for {args.version or 'VERSION'}"
        file.write("\n{title}\n{rule}\n\n".format(title=title, rule="=" * len(title)))
        for issue in sorted(issues, key=lambda x: x["iid"]):
            fmt = "* `#{iid} <{url}>`__: {title}\n"
            file.write(fmt.format(iid=issue["iid"], url=issue["web_url"], title=issue["title"]))

        title = f"Merge requests for {args.version or 'VERSION'}"
        file.write("\n{title}\n{rule}\n\n".format(title=title, rule="=" * len(title)))
        for mr in sorted(merge_requests, key=lambda x: x["iid"]):
            fmt = "* !{iid} <{url}>`__: {title}\n"
            file.write(fmt.format(iid=mr["iid"], url=mr["web_url"], title=mr["title"]))

        if args.output is None:
            print(file.getvalue())
        else:
            with open(args.output, "w") as fh:
                fh.write(file.getvalue())

        return 0

    def get_namemap(self) -> list[dict]:
        file = Path(str(ir.files("_nvtest").joinpath("../../.namemap"))).absolute()
        if not file.exists():
            raise ValueError(f"namemap {file} not found!")
        return json.load(open(file))
