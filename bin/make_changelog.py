#!/usr/bin/env python3
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import argparse
import datetime
import io
import json
import logging
import sys
from pathlib import Path
from typing import Generator
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen


def main() -> int:
    parser = make_argument_parser()
    args = parser.parse_args()
    f = Path(args.name_map)
    if not f.exists():
        raise ValueError(f"namemap {f} not found!")
    namemap = json.load(open(f))
    df = datetime.datetime.strptime(args.date_from, "%Y-%m-%d")
    dt = datetime.datetime.strptime(args.date_to, "%Y-%m-%d")
    changelog = make_changelog(
        project=args.project,
        access_token=args.access_token,
        api_v4_url=args.api_v4_url,
        namemap=namemap,
        version=args.version,
        date_from=df,
        date_to=dt,
    )
    if args.output is None:
        print(changelog)
    else:
        with open(args.output, "w") as fh:
            fh.write(changelog)
    return 0


def make_changelog(
    *,
    project: str,
    project_id: int,
    access_token: str,
    api_v4_url: str,
    namemap: dict,
    version: str | None = None,
    date_from: datetime.datetime,
    date_to: datetime.datetime,
) -> str:
    logging.debug(f"Reading merge requests for {project}")
    merge_requests: list[dict] = []
    for mr in get_merge_requests(
        project_id=project_id,
        access_token=access_token,
        api_v4_url=api_v4_url,
        state="merged",
    ):
        dm = datetime.datetime.fromisoformat(mr["merged_at"])
        if date_in_range(dm, date_from, date_to):
            merge_requests.append(mr)

    logging.debug(f"Reading issues for {project}")
    issues: list[dict] = []
    for issue in get_issues(
        project_id=project_id,
        access_token=access_token,
        api_v4_url=api_v4_url,
        state="closed",
    ):
        dc = datetime.datetime.fromisoformat(issue["closed_at"])
        if date_in_range(dc, date_from, date_to):
            issues.append(issue)

    logging.debug(f"Reading commits for {project}")
    commits: list[dict] = []
    for commit in get_commits(
        project_id=project_id, access_token=access_token, api_v4_url=api_v4_url
    ):
        dc = datetime.datetime.fromisoformat(commit["authored_date"])
        if date_in_range(dc, date_from, date_to):
            commits.append(commit)

    authors: dict[tuple[str, str], int] = {}
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
    write_changelog(
        file,
        commits=commits,
        issues=issues,
        merge_requests=merge_requests,
        authors=authors,
        project=project,
        version=version,
    )
    return file.getvalue()


def write_changelog(
    file: io.StringIO,
    *,
    commits: list[dict],
    issues: list[dict],
    merge_requests: list[dict],
    authors: dict[tuple[str, str], int],
    project: str,
    version: str | None = None,
) -> None:
    version = version or "UNKNOWN-VERSION"
    title = f"{project} {version} release notes"
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

    title = f"Issues closed for {version}"
    file.write("\n{title}\n{rule}\n\n".format(title=title, rule="-" * len(title)))
    for issue in sorted(issues, key=lambda x: x["iid"]):
        fmt = "* `#{iid} <{url}>`__: {title}\n"
        file.write(fmt.format(iid=issue["iid"], url=issue["web_url"], title=issue["title"]))

    title = f"Merge requests for {version}"
    file.write("\n{title}\n{rule}\n\n".format(title=title, rule="-" * len(title)))
    for mr in sorted(merge_requests, key=lambda x: x["iid"]):
        fmt = "* `!{iid} <{url}>`__: {title}\n"
        file.write(fmt.format(iid=mr["iid"], url=mr["web_url"], title=mr["title"]))

    return


def make_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate RST change log for a gitlab project")
    parser.add_argument(
        "--from",
        dest="date_from",
        required=True,
        help="Generate changelog from this date forward, use YYYY-MM-DD",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        required=True,
        help="Generate changelog up to this date, use YYYY-MM-DD",
    )
    parser.add_argument(
        "--project",
        default="canary",
        required=True,
        help="The GitLab project name [default: %(default)s]",
    )
    parser.add_argument(
        "--api-v4-url",
        required=True,
        help="The GitLab API v4 root URL [default: %(default)s]",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        type=int,
        help="The GitLab ID of the project [default: %(default)s]",
    )
    parser.add_argument(
        "--access-token",
        required=True,
        help="The GitLab API access token [default: %(default)s]",
    )
    parser.add_argument("-o", dest="output", help="Write output to this file")
    parser.add_argument("--version", help="Generate changelog for this version")
    parser.add_argument("--name-map", default=None, help="Author name map [default: %(default)s]")
    return parser


def get_merge_requests(
    *, project_id: int, access_token: str, api_v4_url: str, state: str | None = None
) -> Generator[list[dict], None, None]:
    """Get merge_requests for this project"""
    header = {"PRIVATE-TOKEN": access_token}
    page = 1
    baseurl = f"{api_v4_url}/projects/{project_id}/merge_requests"
    while True:
        params = {"page": str(page), "per_page": "50"}
        if state is not None:
            params["state"] = state
        params = urlencode(params)
        url = f"{baseurl}?{params}"
        logging.debug(url)
        request = Request(url=url, headers=header)
        payload = json.load(urlopen(request))
        if not payload:
            break
        yield from payload
        page += 1
    return


def get_issues(
    *, project_id: int, access_token: str, api_v4_url: str, state: str | None = None
) -> Generator[dict, None, None]:
    """Get issues for this project"""
    header = {"PRIVATE-TOKEN": access_token}
    page = 1
    baseurl = f"{api_v4_url}/projects/{project_id}/issues"
    while True:
        params = {"page": str(page), "per_page": "100"}
        if state is not None:
            params["state"] = state
        params = urlencode(params)
        url = f"{baseurl}?{params}"
        logging.debug(url)
        request = Request(url=url, headers=header)
        payload = json.load(urlopen(request))
        if not payload:
            break
        yield from payload
        page += 1
    return


def get_commits(
    *, project_id: int, access_token: str, api_v4_url: str
) -> Generator[list[dict], None, None]:
    """Get issues for this project"""
    header = {"PRIVATE-TOKEN": access_token}
    page = 1
    baseurl = f"{api_v4_url}/projects/{project_id}/repository/commits"
    while True:
        params = {"page": str(page), "per_page": "100"}
        params = urlencode(params)
        url = f"{baseurl}?{params}"
        logging.debug(url)
        request = Request(url=url, headers=header)
        payload = json.load(urlopen(request))
        if not payload:
            break
        yield from payload
        page += 1
    return


def date_in_range(
    date: datetime.datetime, start: datetime.datetime, end: datetime.datetime
) -> bool:
    if (date.year, date.month, date.day) < (start.year, start.month, start.day):
        return False
    if (date.year, date.month, date.day) > (end.year, end.month, end.day):
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
