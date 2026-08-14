# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import Any

import pytest

import _canary.util.json_helper as json
from _canary import config
from _canary.config.argparsing import make_argument_parser
from _canary.plugins.subcommands.run import RequestBuilder
from _canary.plugins.subcommands.run import RequestNode
from _canary.plugins.subcommands.run import ScanPathsRequest


def assert_json_serializable(obj: Any) -> None:
    json.dumps(obj)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--debug"],
        ["-c", "debug:true"],
        ["-e", "SPAM=EGGS"],
        ["run", "--empty-ok"],
        ["run", "--style", "live=no"],
        ["find", "--files"],
        ["config", "show"],
        ["help"],
    ],
)
def test_parsed_core_command_options_are_snapshot_serializable(argv: list[str]) -> None:
    parser = make_argument_parser()
    parser.add_main_epilog(parser)

    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)

    args = parser.parse_args(argv)

    with config.override():
        config.set_main_options(args)
        snapshot = config.snapshot()

    assert_json_serializable(snapshot)


def test_argparse_defaults_do_not_store_live_command_objects() -> None:
    """
    Regression test for accidentally putting command instances or other live
    Python objects into argparse defaults. Config snapshots must remain JSON
    serializable for child processes and schedulers.
    """
    parser = make_argument_parser()
    parser.add_main_epilog(parser)

    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)

    args = parser.parse_args(["help"])

    bad: list[tuple[str, object]] = []

    for key, value in vars(args).items():
        if isinstance(value, (str, int, float, bool, type(None), list, tuple, dict, set)):
            continue
        if isinstance(value, argparse.Namespace):
            continue
        bad.append((key, value))

    assert not bad, f"Non-JSON-like argparse defaults found: {bad}"


def test_request_builder_json_helper_roundtrip():
    builder = RequestBuilder()
    builder.require_kind("scanpaths", [], "scanpaths")
    builder.scanpaths["/tmp/tests"] = ["a.pyt", "b.pyt"]

    text = json.dumps(builder)
    out = json.loads(text)

    assert isinstance(out, RequestBuilder)
    assert out.kind == "scanpaths"
    assert out.scanpaths == {"/tmp/tests": ["a.pyt", "b.pyt"]}


def test_request_node_json_helper_roundtrip():
    req = ScanPathsRequest(value={"/tmp/tests": ["a.pyt"]})

    text = json.dumps(req)
    out = json.loads(text)

    assert isinstance(out, RequestNode)
    assert out.kind == "scanpaths"
    assert out.value == {"/tmp/tests": ["a.pyt"]}
