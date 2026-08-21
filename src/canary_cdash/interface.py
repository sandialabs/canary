# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import hashlib
import json
import os
import re
import xml.dom.minidom as dom
import xml.parsers.expat
import xml.sax.saxutils
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

import canary
from _canary.util.executable import Executable
from _canary.util.filesystem import force_remove

logger = canary.get_logger(__name__)


class api_filters:
    def __init__(self, combine_mode=None):
        assert combine_mode in ("and", "or", None)
        self.combine_mode = combine_mode or "and"
        self.filters = []

    def __iter__(self):
        return iter(self.filters)

    def __len__(self):
        return len(self.filters)

    @property
    def compmap(self):
        return {
            "equal": 41,
            "not equal": 42,
            "greater than": 43,
            "less than": 44,
            "is": 61,
            "is not": 62,
            "contains": 63,
            "does not contain": 64,
            "startswith": 64,
            "endswith": 65,
        }

    def add(self, *, field, comparison, value):
        assert comparison in self.compmap
        f = SimpleNamespace(field=field, compare=comparison, value=value)
        self.filters.append(f)

    def asdict(self):
        params = {}
        filtercount = len(self)
        params["filtercount"] = str(filtercount)
        for i, filter in enumerate(self, start=1):
            params[f"field{i}"] = filter.field
            params[f"compare{i}"] = str(self.compmap[filter.compare])
            params[f"value{i}"] = str(filter.value)
            params[f"comparison{i}"] = filter.compare
        if filtercount > 1:
            params["filtercombine"] = self.combine_mode
        return params


class server:
    def __init__(self, baseurl, project):
        """Upload the file ``filename`` to CDash

        Args:
          baseurl (str): The base CDash URL
          project (str): The CDash project name

        """
        self.baseurl = baseurl
        self.project = project
        self.v1_api_url = f"{self.baseurl}/api/v1"
        self._build_test_nodes_cache: dict[str, list[dict[str, Any]]] = {}

    def build_api_url(self, *, path, query=None):
        url = f"{self.v1_api_url}/{path}"
        if query is not None:
            url = f"{url}?{query}"
        return url

    def upload(self, *, filename, sitename, buildname, buildstamp, mdf5=False):
        """Upload the file ``filename`` to CDash

        Args:
          filename (str): The path to the file to upload
          sitename (str): The CDash site name
          buildname (str): The CDash build name
          buildstamp (str): The CDash build stamp

        """
        params = {
            "project": self.project,
            "build": buildname,
            "site": sitename,
            "stamp": buildstamp,
        }
        if mdf5:
            sha256sum = checksum(hashlib.sha256, filename, block_size=8192)
            params["SHA"] = sha256sum
        encoded_params = urlencode(params)
        url = f"{self.baseurl}/submit.php?{encoded_params}"
        logger.info(f"Uploading {os.path.basename(filename)} to {url}")
        return self.put(url, filename)

    @staticmethod
    def put(url, file):

        def _get_text(doc, tag):
            if els := doc.getElementsByTagName(tag):
                return get_text(els[0])
            return None

        with no_proxy():
            # Proxy settings must be turned off to submit to CDash
            curl = Executable("curl")
            curl.add_default_args("-v", "-L")
            args = ["--upload-file", file, url]
            efile = "cdash-put-err.txt"
            payload = {"status": "NA", "message": None, "buildid": None}
            try:
                with open(efile, "w") as fh:
                    result = curl(*args, output=str, error=fh)
                doc = dom.parseString(result.get_output())
                payload["status"] = _get_text(doc, "status")
                payload["buildid"] = _get_text(doc, "buildId")
            except xml.parsers.expat.ExpatError as e:
                payload["message"] = e.args[0]
            finally:
                if payload["status"] == "NA":
                    m = payload["message"]
                    logger.error(f"Failed to upload {os.path.basename(file)}: {m}")
                elif payload["status"] != "OK":
                    m = payload["message"] = _get_text(doc, "message")
                    lines = "\n    ".join([_.rstrip() for _ in open(efile).readlines()])
                    logger.error(f"Failed to upload {os.path.basename(file)}: {m}\n    {lines}")
                if not canary.config.get("debug"):
                    force_remove(efile)
            return payload

    @staticmethod
    def get(url, raw=False):
        """Get the response from the CDash API and parse it using the json library"""
        response = urlopen(url)  # nosec B310
        return response if raw else json.load(response)

    def buildid(self, *, sitename, buildstamp, buildname):
        """Get the build ID for the CDash build

        Args:
          sitename (str): The CDash site name
          buildstamp (str): The CDash build stamp
          buildname (str): The CDash build name

        Returns:
          buildid: The integer build ID if found, else ``None``

        """
        params = {"project": self.project, "name": buildname, "site": sitename, "stamp": buildstamp}
        query = urlencode(params)
        url = self.build_api_url(path="getbuildid.php", query=query)
        logger.debug(f"Getting build ID from CDash using the following query: {url}")
        curl = Executable("curl")
        try:
            result = curl("-k", "-L", url, output=str, error=os.devnull)
            doc = dom.parseString(result.get_output())
            if els := doc.getElementsByTagName("buildid"):
                buildid = get_text(els[0])
            else:
                buildid = "not found"
        except xml.parsers.expat.ExpatError:
            buildid = "not found"
        logger.debug(f"build id = {buildid}")
        return None if buildid == "not found" else int(buildid)

    @staticmethod
    def contains(site_name, sites_to_skip):
        if site_name in sites_to_skip:
            return True
        for site_to_skip in sites_to_skip:
            if re.search(site_to_skip, site_name):
                return True
        return False

    def builds(self, *, date=None, buildgroups=None, skip_sites=None):
        """Get all CDash builds on optional ``date``.

        Dynamic build groups such as Latest, Latest::Long, and Latest::Experimental
        are computed by CDash's index page.  The GraphQL schema does not expose
        these dynamic groups directly, so we intentionally use the index JSON for
        group membership and build summary data.

        The returned build dictionaries are normalized to the legacy shape expected
        by cdash_html_summary.py.
        """
        skip_sites = skip_sites or []

        logger.info(f"Getting build groups for {self.project}")
        groups = self.get_buildgroups(date, buildgroups=buildgroups)

        nbuild = sum(len(group["builds"]) for group in groups)
        logger.info(f"Found {len(groups)} build groups with {nbuild} builds")

        builds: list[dict] = []

        for group in groups:
            logger.info(f"Getting build summaries for build group {group['name']}")

            for build in group["builds"]:
                if self.contains(build["site"], skip_sites):
                    continue

                normalized = self.normalize_index_build(build, group)
                builds.append(normalized)

        return builds

    def normalize_index_build(self, build: dict, buildgroup: dict) -> dict:
        """Normalize a build entry from CDash index.php JSON.

        The index JSON already contains the build summary data needed by the HTML
        summary.  This method fills in legacy keys that other Canary code expects.
        """
        b = dict(build)

        buildname = b.get("buildname") or b.get("name") or ""
        b["buildname"] = buildname
        b.setdefault("name", buildname)

        b["buildgroup"] = buildgroup.get("name", "")
        b["unixtimestamp"] = buildgroup.get("unixtimestamp", 0)

        b.setdefault("site", "")
        b.setdefault("siteid", None)
        b.setdefault("id", None)

        # CDash index JSON uses hascompilation; some Canary paths historically
        # expected hasbuild.  Keep both aliases.
        if "hascompilation" in b and "hasbuild" not in b:
            b["hasbuild"] = b["hascompilation"]
        if "hasbuild" in b and "hascompilation" not in b:
            b["hascompilation"] = b["hasbuild"]

        b.setdefault("hasupdate", bool(b.get("update")))
        b.setdefault("hasconfigure", bool(b.get("configure")))
        b.setdefault("hascompilation", bool(b.get("compilation")))
        b.setdefault("hasbuild", bool(b.get("compilation")))
        b.setdefault("hastest", bool(b.get("test")))

        update = dict(b.get("update") or {})
        update.setdefault("files", "")
        update.setdefault("errors", 0)
        update.setdefault("time", "0s")
        update.setdefault("timefull", 0)
        b["update"] = update

        configure = dict(b.get("configure") or {})
        configure.setdefault("command", "")
        configure.setdefault("error", 0)
        configure.setdefault("warning", 0)
        configure.setdefault("warningdiff", 0)
        configure.setdefault("time", "0s")
        configure.setdefault("timefull", 0)
        b["configure"] = configure

        compilation = dict(b.get("compilation") or {})
        compilation.setdefault("error", 0)
        compilation.setdefault("warning", 0)
        compilation.setdefault("time", "0s")
        compilation.setdefault("timefull", 0)
        compilation.setdefault("nerrordiffp", None)
        compilation.setdefault("nerrordiffn", None)
        compilation.setdefault("nwarningdiffp", None)
        compilation.setdefault("nwarningdiffn", None)
        b["compilation"] = compilation

        test = self.empty_test_data()
        test.update(dict(b.get("test") or {}))
        b["test"] = test

        b.setdefault("compilername", "")
        b.setdefault("compilerversion", "")
        b.setdefault("generator", "")
        b.setdefault("command", configure.get("command", ""))
        b.setdefault("osname", "")
        b.setdefault("buildplatform", b.get("operatingSystemPlatform", ""))

        b["build_type"] = find_build_type(configure, b)

        return b

    def get_buildgroups(self, date, buildgroups=None):
        params = {"project": self.project}
        if date:
            params["date"] = date
        query = urlencode(params)
        url = self.build_api_url(path="index.php", query=query)
        logger.debug(f"Getting build groups from CDash using the following query: {url}")
        data = self.get(url)
        if buildgroups is not None:
            buildgroups = [_ for _ in data["buildgroups"] if _["name"] in buildgroups]
            data["buildgroups"] = buildgroups
        for buildgroup in data["buildgroups"]:
            buildgroup["unixtimestamp"] = data["unixtimestamp"]
        return data["buildgroups"]

    def failed_tests(
        self,
        *,
        date=None,
        buildgroups=None,
        skip_sites=None,
        skip_missing=False,
        skip_timeout=False,
    ):
        """Get all failed tests from CDash server

        Args:
          date (str): Get results from this date
          buildgroups (list[str]): List of build groups to retrieve.  Defaults to all
          skip_missing (bool): Skip missing tests
          skip_sites (list[str]): Skip tests at these sites
          skip_timeout (bool): Skip timed out tests

        Returns:
          failed: failed[n] is a dictionary describing the nth failed test

        """
        failed = []
        builds = self.builds(date=date, buildgroups=buildgroups, skip_sites=skip_sites)
        for i, build in enumerate(builds, start=1):
            logger.info(f"Getting failed tests for build {i} of {len(builds)}")
            if skip_timeout:
                for fail_reason in ("Failed", "Diffed"):
                    tests = self.get_failed_tests(
                        build, skip_missing=skip_missing, fail_reason=fail_reason
                    )
                    failed.extend(tests)
            else:
                tests = self.get_failed_tests(build, skip_missing=skip_missing)
                failed.extend(tests)
        logger.info(f"Found {len(failed)} tests across the {len(builds)} builds")
        return failed

    def tests(
        self,
        *,
        date=None,
        buildgroups=None,
        skip_missing=False,
        skip_sites=None,
        include_details=True,
    ):
        """Get all failed tests from CDash server

        Args:
          date (str): Get results from this date
          buildgroups (list[str]): List of build groups to retrieve.  Defaults to all
          skip_missing bool: Skip missing tests
          skip_sites (list[str]): Skip tests at these sites
          include_details (bool): Return details of each test (slow)

        Returns:
          tests (list): tests[n] is a dictionary describing the nth test

        """
        tests = []
        builds = self.builds(date=date, buildgroups=buildgroups, skip_sites=skip_sites)
        for i, build in enumerate(builds, start=1):
            logger.info(f"Getting tests for build {i} of {len(builds)}")
            build_tests = self.get_tests_from_build(
                build, skip_missing=skip_missing, include_details=include_details
            )
            logger.debug(f"Found {len(build_tests)} tests for {build['buildname']}")
            tests.extend(build_tests)
        return tests

    def get_tests_from_build(self, build, skip_missing=False, include_details=True, **kwargs):
        return self._get_tests_from_build(
            build, skip_missing=skip_missing, include_details=include_details, **kwargs
        )

    def build_test_nodes(self, buildid: int | str) -> list[dict[str, Any]]:
        key = str(buildid)
        if key in self._build_test_nodes_cache:
            return self._build_test_nodes_cache[key]

        query = """
        query BuildTests($buildid: ID!, $first: Int!, $after: String) {
        build(id: $buildid) {
            tests(first: $first, after: $after) {
            pageInfo {
                hasNextPage
                endCursor
            }
            edges {
                node {
                id
                name
                status
                timeStatusCategory
                runningTime
                meanRunningTime
                stdDevRunningTime
                startTime
                details
                path
                command
                }
            }
            }
        }
        }
        """

        nodes = self.paginate(query, {"buildid": key}, ("build", "tests"))
        self._build_test_nodes_cache[key] = nodes
        return nodes

    def normalize_test_node(self, node: dict[str, Any], build: dict[str, Any]) -> dict[str, Any]:
        test_id = node.get("id")
        status = normalize_cdash_status(node.get("status") or "")

        return {
            "buildtestid": as_int(test_id),
            "name": node.get("name") or "",
            "status": status,
            "time_status_category": node.get("timeStatusCategory") or "",
            "site": build.get("site", ""),
            "siteid": build.get("siteid"),
            "build": build.get("buildname", ""),
            "time": float(node.get("runningTime") or 0.0),
            "execTimeFull": float(node.get("runningTime") or 0.0),
            "details": node.get("details") or "",
            "path": node.get("path") or "",
            "command": node.get("command") or "",
            "details_link": self.test_details_link(test_id),
            "summary_link": self.build_summary_link(build.get("id")),
            "compilername": build.get("compilername", ""),
            "compilerversion": build.get("compilerversion", ""),
            "build_type": build.get("build_type", ""),
            "details_api_url": None,
        }

    def get_failed_tests(self, build, fail_reason=None, skip_missing=False, include_details=True):
        filters = api_filters()
        filters.add(field="status", comparison="is", value="Failed")

        if fail_reason is not None:
            assert fail_reason in ("Failed", "Diffed", "Timeout")
            filters.add(field="details", comparison="contains", value=fail_reason)

        return self._get_tests_from_build(
            build, include_details=include_details, skip_missing=skip_missing, **filters.asdict()
        )

    def get_failed_test_category_counts(self, build: dict[str, Any]) -> tuple[int, int, int]:
        """
        Return (diffed, timeout, failed_other) for one build.

        This intentionally avoids fill_test_details(), since the Build.tests GraphQL
        node already provides status/details fields needed for categorization.
        """
        failed = self.get_failed_tests(build, skip_missing=True, include_details=False)

        num_diffed = 0
        num_timeout = 0

        for test in failed:
            text = " ".join(
                str(test.get(key) or "") for key in ("details", "status", "time_status_category")
            ).lower()

            if "diffed" in text:
                num_diffed += 1
            elif "timeout" in text:
                num_timeout += 1

        num_failed = max(len(failed) - num_diffed - num_timeout, 0)
        return num_diffed, num_timeout, num_failed

    def _get_tests_from_build(self, build, *args, **kwargs):
        """Get tests from CDash using GraphQL.

        This replaces the old v1 ``viewTest.php`` endpoint.
        """
        skip_missing = kwargs.pop("skip_missing", False)
        include_details = kwargs.pop("include_details", True)

        nodes = self.build_test_nodes(build["id"])
        rows = [self.normalize_test_node(node, build) for node in nodes]

        rows = [row for row in rows if legacy_filters_match(row, kwargs)]

        if skip_missing:
            rows = [row for row in rows if row["status"] != "Missing"]

        if include_details:
            for row in rows:
                self.fill_test_details(row)

        return rows

    def fill_test_details(self, test):
        query = """
        query TestDetails($testid: ID!) {
        test(id: $testid) {
            id
            command
            output
            details
            testMeasurements {
            name
            value
            }
        }
        }
        """

        data = self.graphql(query, {"testid": str(test["buildtestid"])})
        details = data["test"]

        test["command"] = details.get("command") or test.get("command", "")
        test["output"] = details.get("output") or ""
        test["details"] = details.get("details") or test.get("details", "")
        test["revisionurl"] = ""

        for measurement in details.get("testMeasurements") or []:
            key = "_".join(measurement["name"].split()).lower()
            test[key] = measurement["value"]

    def build_summary_link(self, buildid: int | str | None) -> str:
        return f"{self.baseurl}/buildSummary.php?buildid={buildid}"

    def test_details_link(self, testid: int | str | None) -> str:
        return f"{self.baseurl}/testDetails.php?buildtestid={testid}"

    def graphql(self, query: str, variables: dict[str, object] | None = None) -> dict[str, Any]:
        """Execute a CDash GraphQL query and return the response data."""
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")

        request = Request(
            f"{self.baseurl}/graphql",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        with no_proxy():
            response = urlopen(request)  # nosec B310

        document = json.load(response)

        if errors := document.get("errors"):
            messages = "; ".join(str(error.get("message", error)) for error in errors)
            raise RuntimeError(f"CDash GraphQL query failed: {messages}")

        data = document.get("data")
        if data is None:
            raise RuntimeError("CDash GraphQL response did not contain a 'data' object")

        return data

    def paginate(
        self,
        query: str,
        variables: dict[str, object],
        connection_path: tuple[str, ...],
        *,
        first: int = 500,
    ) -> list[dict[str, Any]]:
        """Page through a Relay-style GraphQL connection and return node dictionaries."""
        nodes: list[dict[str, Any]] = []
        after: str | None = None

        while True:
            page_vars = dict(variables)
            page_vars["first"] = first
            page_vars["after"] = after

            data = self.graphql(query, page_vars)

            obj: Any = data
            for key in connection_path:
                obj = obj[key]

            connection = obj
            for edge in connection["edges"]:
                nodes.append(edge["node"])

            page_info = connection["pageInfo"]
            if not page_info.get("hasNextPage"):
                break

            after = page_info.get("endCursor")
            if not after:
                break

        return nodes

    @staticmethod
    def empty_test_data():
        test = {}
        test["fail_fail"] = 0
        test["nfaildiffn"] = 0
        test["nfaildiffp"] = None
        test["notrun"] = 0
        test["nnotrundiffn"] = None
        test["nnotrundiffp"] = None
        test["pass"] = 0
        test["npassdiffn"] = None
        test["npassdiffp"] = None
        test["fail_diff"] = 0
        test["fail_timeout"] = 0
        test["procTime"] = None
        test["procTimeFull"] = None
        test["time"] = None
        test["timefull"] = None
        return test


def get_text(el: dom.Element) -> str:
    return "".join(n.data for n in el.childNodes if n.nodeType == n.TEXT_NODE).strip()  # ty: ignore[unresolved-attribute]


def clean_log_event(event):
    """Convert log output from ASCII to Unicode and escape for XML"""
    event = vars(event)
    event["text"] = escapexml(event["text"])
    event["pre_context"] = escapexml("\n".join(event["pre_context"]))
    event["post_context"] = escapexml("\n".join(event["post_context"]))
    # source_file and source_line_no are either strings or
    # the tuple (None,).  Distinguish between these two cases.
    if event["source_file"][0] is None:
        event["source_file"] = ""
        event["source_line_no"] = ""
    else:
        event["source_file"] = escapexml(event["source_file"])
    return event


def escapexml(text):
    """Convert text from ASCII to Unicode and escape for XML"""
    return xml.sax.saxutils.escape(text)


@contextmanager
def no_proxy():
    """Context manager removing proxy variables from the environment.

    Notes
    -----
    For the SEMs CDash server, it is necessary to remove proxy settings from the
    environment in order to upload data.

    """
    save_env = dict(os.environ)
    keys = ("http_proxy", "https_proxy", "ftp_proxy", "no_proxy", "all_proxy")
    for key in keys:
        os.environ.pop(key, None)
        os.environ.pop(key.upper(), None)
    yield
    os.environ.clear()
    os.environ.update(save_env)


def checksum(hashlib_algo, filename, **kwargs):
    """Returns a hex digest of the filename generated using an
    algorithm from hashlib.
    """
    block_size = kwargs.get("block_size", 2**20)
    hasher = hashlib_algo()
    with open(filename, "rb") as file:
        while True:
            data = file.read(block_size)
            if not data:
                break
            hasher.update(data)
    return hasher.hexdigest()


def urlescape(item):
    return "+".join(item.split())


def find_build_type(configure, build):
    command = ""
    if isinstance(configure, dict):
        command = str(configure.get("command") or "")

    buildname = str(build.get("buildname") or build.get("name") or "")

    m = re.search(r"-D\s?CMAKE_BUILD_TYPE=(?P<x>\w+)", command)
    if m:
        return m.group("x")

    m = re.search(r"-D\s?CMAKE_BUILD_TYPE:STRING=(?P<x>\w+)", command)
    if m:
        return m.group("x")

    m = re.search(r"build_type=(?P<x>\w+)", buildname)
    if m:
        return m.group("x")

    if " dbg " in buildname:
        return "Debug"

    if " opt " in buildname:
        return "Release"

    m = re.search(r"AlegraNevada\/(?P<x>\w+)", buildname)
    if m:
        return m.group("x")

    if build.get("buildType"):
        return str(build["buildType"])

    return "RelWithDebInfo"


def normalize_cdash_status(value: str) -> str:
    text = str(value or "").replace("_", " ").strip().lower()
    mapping = {
        "passed": "Passed",
        "failed": "Failed",
        "not run": "Missing",
        "notrun": "Missing",
        "not_run": "Missing",
        "missing": "Missing",
    }
    return mapping.get(text, text.title())


def legacy_filters_match(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    filtercount = int(filters.get("filtercount", 0) or 0)
    if filtercount <= 0:
        return True

    mode = str(filters.get("filtercombine", "and")).lower()
    checks: list[bool] = []

    for i in range(1, filtercount + 1):
        field = filters.get(f"field{i}")
        value = filters.get(f"value{i}")
        comparison = filters.get(f"comparison{i}")

        if comparison is None:
            comparison = comparison_from_code(filters.get(f"compare{i}"))

        checks.append(compare_value(row.get(str(field), ""), str(comparison), str(value)))

    if mode == "or":
        return any(checks)
    return all(checks)


def comparison_from_code(code: Any) -> str:
    mapping = {
        "41": "equal",
        "42": "not equal",
        "43": "greater than",
        "44": "less than",
        "61": "is",
        "62": "is not",
        "63": "contains",
        "64": "does not contain",
        "65": "endswith",
    }
    return mapping.get(str(code), "contains")


def compare_value(actual: Any, comparison: str, expected: str) -> bool:
    actual_s = str(actual)
    comparison = comparison.lower()

    if comparison in ("equal", "is"):
        return actual_s == expected
    if comparison in ("not equal", "is not"):
        return actual_s != expected
    if comparison == "contains":
        return expected in actual_s
    if comparison == "does not contain":
        return expected not in actual_s
    if comparison == "startswith":
        return actual_s.startswith(expected)
    if comparison == "endswith":
        return actual_s.endswith(expected)
    if comparison == "greater than":
        try:
            return float(actual_s) > float(expected)
        except ValueError:
            return False
    if comparison == "less than":
        try:
            return float(actual_s) < float(expected)
        except ValueError:
            return False
    return False


def as_int(value: Any) -> int | str:
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def test_build_type():
    c = {"command": "-DFOOBAR=BAZ -DCMAKE_BUILD_TYPE=Release"}
    b = {"buildname": "BAZ"}
    bt = find_build_type(c, b)
    assert bt == "Release"

    c = {"command": "-DFOOBAR=BAZ -DCMAKE_BUILD_TYPE:STRING=Release"}
    b = {"buildname": "BAZ"}
    bt = find_build_type(c, b)
    assert bt == "Release"

    c = {"command": "-DFOOBAR=BAZ -D CMAKE_BUILD_TYPE=Debug"}
    b = {"buildname": "BAZ"}
    bt = find_build_type(c, b)
    assert bt == "Debug"

    c = {"command": "-DFOOBAR=BAZ"}
    b = {"buildname": "alegra opt spam"}
    bt = find_build_type(c, b)
    assert bt == "Release"

    c = {"command": "-DFOOBAR=BAZ"}
    b = {"buildname": "alegra dbg spam"}
    bt = find_build_type(c, b)
    assert bt == "Debug"

    c = {"command": "-DFOOBAR=BAZ"}
    b = {"buildname": "AlegraNevada/Release Stuff"}
    bt = find_build_type(c, b)
    assert bt == "Release"

    c = {"command": "-DFOOBAR=BAZ"}
    b = {"buildname": "AlegraNevada/Debug Stuff"}
    bt = find_build_type(c, b)
    assert bt == "Debug"

    c = {"command": "-DFOOBAR=BAZ"}
    b = {"buildname": "AlegraNevada Stuff"}
    bt = find_build_type(c, b)
    assert bt == "RelWithDebInfo"
    print("Passed")


if __name__ == "__main__":
    test_build_type()
