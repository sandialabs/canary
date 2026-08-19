# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.plugins.subcommands.run import RequestBuilder
from _canary.plugins.subcommands.run import ScanPathsRequest
from _canary.queue_executor import PhaseTimer
from _canary.util import json_helper as json


def test_phase_timer_json_roundtrip_if_serializable():
    timer = PhaseTimer()
    timer.start("Queued", at=1.0)
    timer.transition("Running", at=3.0)
    timer.stop(at=8.0)

    text = json.dumps(timer)
    out = json.loads(text)

    assert isinstance(out, PhaseTimer)
    assert out.value("Queued", live=False) == 2.0
    assert out.value("Running", live=False) == 5.0


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
