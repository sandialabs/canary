# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import io
import os
import re

from _canary.util import cdash
from _canary.util import gitlab
from _canary.util import logging


def create_issues_from_failed_tests(
    *,
    access_token: str | None = None,
    cdash_url: str | None = None,
    cdash_project: str | None = None,
    gitlab_url: str | None = None,
    gitlab_api_url: str | None = None,
    gitlab_project_id: int | str | None = None,
    date: str | None = None,
    filtergroups: list[str] | None = None,
    skip_sites: list[str] | None = None,
    dont_close_missing: bool = False,
) -> None:
    """Create issues on GitLab from failing tests on CDash

    Args:
        cdash_url: The base CDash url, do not include project
        cdash_project: The CDash project
        gitlab_url: The GitLab project url
        gitlab_project_id: The GitLab project's integer ID
        access_token: The GitLab access token.  Must have API read/write priveleges
        date: Date to retrieve from CDash
        filtergroups: Groups to pull down from CDash.  Defaults to "Nightly"
        skip_sites: Sites (systems) on which to ignore issues. Accepts Python
          regular expressions
        dont_close_missing: Don't close GitLab issues that are missing from CDash

    """
    if access_token is None:
        if "ACCESS_TOKEN" not in os.environ:
            raise MissingCIVariable("ACCESS_TOKEN")
        access_token = os.environ["ACCESS_TOKEN"]
    if cdash_url is None:
        if "CDASH_URL" not in os.environ:
            raise MissingCIVariable("CDASH_URL")
        cdash_url = os.environ["CDASH_URL"]
    if cdash_project is None:
        if "CDASH_PROJECT" not in os.environ:
            raise MissingCIVariable("CDASH_PROJECT")
        cdash_project = os.environ["CDASH_PROJECT"]
    if gitlab_url is None:
        if "CI_PROJECT_URL" not in os.environ:
            raise MissingCIVariable("CI_PROJECT_URL")
        gitlab_url = os.environ["CI_PROJECT_URL"]
    if gitlab_project_id is None:
        if "CI_PROJECT_ID" not in os.environ:
            raise MissingCIVariable("CI_PROJECT_ID")
        gitlab_project_id = int(os.environ["CI_PROJECT_ID"])
    if gitlab_api_url is None:
        if "CI_API_V4_URL" not in os.environ:
            raise MissingCIVariable("CI_API_V4_URL")
        gitlab_api_url = os.environ["CI_API_V4_URL"]

    filtergroups = filtergroups or ["Nightly"]
    server = cdash.server(cdash_url, cdash_project)
    builds = server.builds(date=date, buildgroups=filtergroups, skip_sites=skip_sites)
    tests: list[dict] = []
    for build in builds:
        tests.extend(server.get_failed_tests(build, skip_missing=True))
    test_groups = groupby_status_and_testname(tests)
    issue_data = []
    for _, group in test_groups.items():
        for test_name, test_realizations in group.items():
            issue = generate_test_issue(test_name, test_realizations)
            issue_data.append(issue)
    repo = gitlab.repo(
        url=gitlab_url,
        access_token=access_token,
        project_id=int(gitlab_project_id),
        api_url=gitlab_api_url,
    )
    for issue in issue_data:
        create_or_update_test_issues(repo, issue)
    if not dont_close_missing:
        close_test_issues_missing_from_cdash(repo, issue_data)


def groupby_status_and_testname(tests):
    """Group CDash tests by status and then name

    Notes
    -----
    Groups tests as:

    .. code-block: yaml

        {
            status: {
                test_name: [
                    test_realization_1,
                    test_realization_2,
                    ...,
                    test_realization_n
                ],
            }
        }

    """
    details_map = {
        "Timeout (Timeout)": "Timeout",
        "Completed (Diffed)": "Diffed",
        "Completed (Failed)": "Failed",
        "notrun (Not Run)": "Failed",
    }
    grouped = {}
    logging.info("Grouping failed tests by status and name")
    for test in tests:
        if re.search(r"\[.*\]", test["name"]):
            name = test["name"].split("[")[0]
        else:
            name = test["name"].split(".")[0]
        details = test.pop("details")
        status = details_map.get(details, "Unknown")
        test["fail_reason"] = status
        grouped.setdefault(status, {}).setdefault(name, []).append(test)
    logging.info("Done grouping failed tests by status and name")
    for gn, gt in grouped.items():
        logging.info(f"{len(gt)} tests {gn}")
    return grouped


def generate_test_issue(name, realizations):
    fail_reason = realizations[0]["fail_reason"]
    script_link = realizations[0]["script"]
    script_name = os.path.basename(script_link)
    description = io.StringIO()
    description.write(f"## {fail_reason} test\n\n")
    description.write(f"- Test name: `{name}`\n")
    description.write(f"- Test script: [{script_name}]({script_link})\n")
    description.write(
        "\n-------------\n"
        "Issue automatically generated from a corresponding failed test on CDash.\n"
    )
    s_today = datetime.date.today().strftime("%b %d, %Y")
    notes = io.StringIO()
    m = {"Diffed": "diffing", "Failed": "failing", "Timeout": "timing out"}
    notes.write(f"Realizations {m.get(fail_reason, 'Failed')} as of {s_today}:\n\n")
    sites = []
    for realization in realizations:
        site = realization["site"]
        link = realization["details_link"]
        rname = realization["name"]
        target = f"{rname} site={site}"
        build_type = realization["build_type"]
        cc = f"{realization['compilername']}@{realization['compilerversion']}"
        target += f" build_type={build_type} %{cc}"
        notes.write(f"- [`{target}`]({link})\n")
        sites.append(site)
    legacy_title = f"TEST {fail_reason.upper()}: {name}"
    title = f"{name}: {fail_reason}"
    issue_data = dict(
        status=fail_reason,
        name=name,
        description=description.getvalue(),
        notes=notes.getvalue(),
        legacy_title=legacy_title,
        title=title,
        sites=sites,
        fail_reason=fail_reason,
    )
    return issue_data


def create_or_update_test_issues(repo, issue_data):
    existing_issues = repo.issues()
    existing_test_issues = [_ for _ in existing_issues if is_test_issue(_)]
    existing = find_existing_issue(issue_data, existing_test_issues)
    if existing is not None:
        update_existing_issue(repo, existing, issue_data)
    else:
        create_new_issue(repo, issue_data)


def close_test_issues_missing_from_cdash(repo, current_issue_data):
    existing_issues = repo.issues()
    existing_test_issues = [_ for _ in existing_issues if is_test_issue(_)]
    for existing_issue in existing_test_issues:
        if existing_issue["state"] != "opened":
            continue
        for current_issue in current_issue_data:
            if existing_issue["title"] == current_issue["title"]:
                break
            elif existing_issue["title"] == current_issue["legacy_title"]:
                break
        else:
            # Issue is open, but not in the CDash failed tests. Must have been fixed and
            # not closed.
            logging.info(f"Closing issue {existing_issue['title']}")
            params = {"state_event": "close", "add_labels": "test::fixed"}
            repo.edit_issue(existing_issue["iid"], data=params)


def is_test_issue(issue, include_blacklisted=False):
    if not include_blacklisted:
        if "test::blacklisted" in issue["labels"]:
            return False
    return any([label.startswith("test::") for label in issue["labels"]])


def find_existing_issue(new_issue, existing_issues):
    label = test_status_label(new_issue["fail_reason"])
    for issue in existing_issues:
        if label in issue["labels"] and issue["title"] == new_issue["title"]:
            return issue
        elif label in issue["labels"] and issue["title"] == new_issue["legacy_title"]:
            return issue


def update_existing_issue(repo, existing, updated_issue_data):
    fail_reason = updated_issue_data["fail_reason"]
    title = updated_issue_data["title"]
    description = updated_issue_data["description"]
    labels = [test_status_label(fail_reason)]
    labels.append("Stage::To Do")
    labels.extend([site_label(_) for _ in updated_issue_data["sites"]])
    params = {"title": title, "description": description}
    add = [_ for _ in labels if _ not in existing["labels"]]
    if add:
        params["add_labels"] = ",".join(add)
    remove = []
    for label in existing["labels"]:
        if label.startswith("system: ") and label not in labels:
            remove.append(label)
        elif label.startswith("Stage::") and label != "Stage::To Do":
            remove.append(label)
    if remove:
        params["remove_labels"] = ",".join(remove)
    if existing["state"] == "closed":
        params["state_event"] = "reopen"
    s = "Reopening" if params.get("state_event") else "Updating"
    logging.info(f"{s} issue {title}")
    iid = existing["iid"]
    repo.edit_issue(iid, data=params)
    repo.edit_issue(iid, notes=updated_issue_data["notes"])


def create_new_issue(repo, new_issue_data):
    title = new_issue_data["title"]
    fail_reason = new_issue_data["fail_reason"]
    description = new_issue_data["description"]
    labels = [test_status_label(fail_reason)]
    labels.append("Stage::To Do")
    labels.extend([site_label(_) for _ in new_issue_data["sites"]])
    params = {"title": title, "description": description, "labels": ",".join(labels)}
    logging.info(f"Creating new issue for {title}, with labels {params['labels']}")
    iid = repo.new_issue(data=params)
    if iid:
        repo.edit_issue(iid, notes=new_issue_data["notes"])


def test_status_label(status):
    if status == "Diffed":
        label = "diffed"
    elif status == "Failed":
        label = "failed"
    elif status == "Timeout":
        label = "timeout"
    else:
        label = status
    if label not in ("diffed", "failed", "timeout"):
        label = "failed"
    scoped_label = f"test::{label}"
    return scoped_label


def site_label(site):
    return f"system: {site}"


class MissingCIVariable(Exception):
    pass
