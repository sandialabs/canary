# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.subcommands.run import RequestBuilder
from _canary.subcommands.run import ScanPathsRequest
from _canary.util import json_helper as json


def test_request_builder_roundtrip():
    builder = RequestBuilder()
    builder.kind = "scanpaths"
    builder.scanpaths = {"/tmp/tests": ["a.pyt"]}

    out = json.loads(json.dumps(builder))

    assert isinstance(out, RequestBuilder)
    assert out.kind == "scanpaths"
    assert out.scanpaths == {"/tmp/tests": ["a.pyt"]}


def test_scanpaths_request_roundtrip():
    req = ScanPathsRequest(value={"/tmp/tests": ["a.pyt"]})

    out = json.loads(json.dumps(req))

    assert isinstance(out, ScanPathsRequest)
    assert out.value == {"/tmp/tests": ["a.pyt"]}
