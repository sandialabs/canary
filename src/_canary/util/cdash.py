# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import hashlib
import json
import os
import re
import sys
import xml.dom.minidom as dom
import xml.parsers.expat
import xml.sax.saxutils
from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.request import urlopen

from ..third_party.color import cwrite
from ..third_party.ctest_log_parser import CTestLogParser  # noqa: F401
from ..util import logging
from .executable import Executable
from .filesystem import force_remove


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
            md5sum = checksum(hashlib.md5, filename, block_size=8192)
            params["MD5"] = md5sum
        encoded_params = urlencode(params)
        url = f"{self.baseurl}/submit.php?{encoded_params}"
        logging.info(f"Uploading {os.path.basename(filename)} to {url}", file=sys.stderr)
        return self.put(url, filename)

    @staticmethod
    def put(url, file):
        from .. import config

        with no_proxy():
            # Proxy settings must be turned off to submit to CDash
            curl = Executable("curl")
            curl.add_default_args("-v")
            args = ["-X", "PUT", url]
            args.extend(["-H", "Content-Type: text/xml"])
            args.extend(["-H", "Accept: text/xml"])
            args.extend(["--data-binary", f"@{file}"])
            efile = "cdash-put-err.txt"
            try:
                with open(efile, "w") as fh:
                    result = curl(*args, output=str, error=fh)
                doc = dom.parseString(result.get_output())
                stat = doc.getElementsByTagName("status")[0].firstChild.data.strip()
                status = 0 if stat == "OK" else 1
            except xml.parsers.expat.ExpatError as e:
                doc = None
                m = e.args[0]
                status = 1
            finally:
                if doc is None:
                    logging.error(f"Failed to upload {os.path.basename(file)}: {m}")
                elif status:
                    m = doc.getElementsByTagName("message")[0].firstChild.data.strip()
                    lines = "\n    ".join([_.rstrip() for _ in open(efile).readlines()])
                    logging.error(f"Failed to upload {os.path.basename(file)}: {m}\n    {lines}")
                if not config.debug:
                    force_remove(efile)
            return status

    @staticmethod
    def get(url, raw=False):
        """Get the response from the CDash API and parse it using the json library"""
        response = urlopen(url)
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
        params = {
            "project": self.project,
            "name": buildname,
            "site": sitename,
            "stamp": buildstamp,
        }
        query = urlencode(params)
        url = self.build_api_url(path="getbuildid.php", query=query)
        logging.debug(f"Getting build ID from CDash using the following query: {url}")
        curl = Executable("curl")
        try:
            result = curl("-k", url, output=str, error=os.devnull)
            doc = dom.parseString(result.get_output())
            buildid = doc.getElementsByTagName("buildid")[0].firstChild.data.strip()
        except xml.parsers.expat.ExpatError:
            buildid = "not found"
        logging.debug(f"build id = {buildid}")
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
        """Get all of the CDash builds on (optional) ``date``

        Args:
          date (str): The build date formatted as YYYY-MM-DD
          buildgroups (list[str]): Build groups to pull down from CDash
          skip_sites: List of sites to skip.  Can be a python regular expression to skip matching
            sites.  Eg, 'ascic10?' would match ascic101 but not ascic165.

        """
        skip_sites = skip_sites or []
        logging.info(f"Getting build groups for {self.project}")
        buildgroups = self.get_buildgroups(date, buildgroups=buildgroups)
        nbuild = sum([len(bg["builds"]) for bg in buildgroups])
        logging.info(f"Found {len(buildgroups)} build groups with {nbuild} builds")
        builds = []
        for buildgroup in buildgroups:
            n = len(buildgroup["builds"])
            logging.info(f"Getting build summaries for build group {buildgroup['name']}")
            for i, build in enumerate(buildgroup["builds"], start=1):
                cwrite("\r@*b{==>} Getting build summary for build %d of %d" % (i, n))
                if self.contains(build["site"], skip_sites):
                    continue
                build["unixtimestamp"] = buildgroup["unixtimestamp"]
                params = {"buildid": build["id"]}
                query = urlencode(params)
                url = self.build_api_url(path="buildSummary.php", query=query)
                data = self.get(url)
                build["compilername"] = data["build"]["compilername"]
                build["compilerversion"] = data["build"]["compilerversion"]
                build["generator"] = data["build"]["generator"]
                build["command"] = data["build"]["command"]
                build["osname"] = data["build"]["osname"]
                build["buildgroup"] = buildgroup["name"]
                if data.get("configure"):
                    build["build_type"] = find_build_type(data["configure"], build)
                else:
                    build["build_type"] = "Unknown"
                builds.append(build)
            cwrite("\n")
        return builds

    def get_buildgroups(self, date, buildgroups=None):
        params = {"project": self.project}
        if date:
            params["date"] = date
        query = urlencode(params)
        url = self.build_api_url(path="index.php", query=query)
        logging.debug(f"Getting build groups from CDash using the following query: {url}")
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
            logging.info(f"Getting failed tests for build {i} of {len(builds)}")
            if skip_timeout:
                for fail_reason in ("Failed", "Diffed"):
                    tests = self.get_failed_tests(
                        build, skip_missing=skip_missing, fail_reason=fail_reason
                    )
                    failed.extend(tests)
            else:
                tests = self.get_failed_tests(build, skip_missing=skip_missing)
                failed.extend(tests)
        logging.info(f"Found {len(failed)} tests across the {len(builds)} builds")
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
            logging.info(f"Getting tests for build {i} of {len(builds)}")
            build_tests = self.get_tests_from_build(
                build, skip_missing=skip_missing, include_details=include_details
            )
            logging.debug(f"Found {len(build_tests)} tests for {build['buildname']}")
            tests.extend(build_tests)
        return tests

    def get_failed_tests(
        self,
        build,
        fail_reason=None,
        skip_missing=False,
        include_details=True,
    ):
        """Get failed tests from CDash

        Args:
          fail_reason (str): The reason for the failure
          skip_missing (bool): Skip missing tests
          include_details (bool): Return details of each test (slow)

        Returns:
          ``list`` of ``dict`` describing the ith failed test

        """
        filters = api_filters()
        filters.add(field="status", comparison="is", value="Failed")
        if fail_reason is not None:
            assert fail_reason in ("Failed", "Diffed", "Timeout")
            filters.add(field="details", comparison="contains", value=fail_reason)
        failed = self._get_tests_from_build(
            build,
            include_details=include_details,
            skip_missing=skip_missing,
            **filters.asdict(),
        )
        return failed

    def get_tests_from_build(self, build, skip_missing=False, include_details=True, **kwargs):
        return self._get_tests_from_build(
            build,
            skip_missing=skip_missing,
            include_details=include_details,
            **kwargs,
        )

    def _get_tests_from_build(self, build, *args, **kwargs):
        """Get tests from CDash

        Returns
        -------
        list
            list[i] is a dictionary describing the ith failed test

        """
        skip_missing = kwargs.pop("skip_missing", False)
        include_details = kwargs.pop("include_details", True)
        kwargs["buildid"] = str(build["id"])
        query = urlencode(kwargs)
        if args:
            query = f"{'&'.join(args)}&{query}"
        url = self.build_api_url(path="viewTest.php", query=query)
        tests = server.get(url)
        for i, test in enumerate(tests["tests"]):
            if skip_missing and test["status"] == "Missing":
                test = None
            else:
                test["site"] = build["site"]
                test["siteid"] = build["siteid"]
                test["build"] = build["buildname"]
                test["time"] = float(test["execTimeFull"])
                test["details_link"] = f"{self.baseurl}/{test.pop('detailsLink')}"
                test["summary_link"] = f"{self.baseurl}/{test.pop('summaryLink')}"
                test["compilername"] = build["compilername"]
                test["compilerversion"] = build["compilerversion"]
                test["build_type"] = build["build_type"]
                q = urlencode({"buildtestid": test["buildtestid"]})
                details_api_url = self.build_api_url(path="testDetails.php", query=q)
                test["details_api_url"] = details_api_url
                if include_details:
                    self.fill_test_details(test)
            # Replace with flattened test
            tests["tests"][i] = test
        return [_ for _ in tests["tests"] if _ is not None]

    def fill_test_details(self, test):
        query = urlencode({"buildtestid": test["buildtestid"]})
        url = self.build_api_url(path="testDetails.php", query=query)
        data = server.get(url)
        details = data["test"]
        test["command"] = details["command"]
        test["revisionurl"] = details["update"]["revisionurl"]
        for measurement in details["measurements"]:
            key = "_".join(measurement["name"].split()).lower()
            test[key] = measurement["value"]

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
    keys = ("http_proxy", "https_proxy", "ftp_proxy", "no_proxy")
    for key in keys:
        os.environ.pop(key, None)
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
    m = re.search(r"-D\s?CMAKE_BUILD_TYPE=(?P<x>\w+)", configure["command"])
    if m:
        return m.group("x")
    m = re.search(r"-D\s?CMAKE_BUILD_TYPE:STRING=(?P<x>\w+)", configure["command"])
    if m:
        return m.group("x")
    m = re.search(r"build_type=(?P<x>\w+)", build["buildname"])
    if m:
        return m.group("x")
    if " dbg " in build["buildname"]:
        return "Debug"
    if " opt " in build["buildname"]:
        return "Release"
    m = re.search(r"AlegraNevada\/(?P<x>\w+)", build["buildname"])
    if m:
        return m.group("x")
    return "RelWithDebInfo"


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
