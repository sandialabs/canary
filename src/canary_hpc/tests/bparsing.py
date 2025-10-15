# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.config.argparsing import Parser as CanaryParser
from canary_hpc import LegacyParserAdapter
from canary_hpc import binpack
from canary_hpc import setup_parser
from canary_hpc.argparsing import CanaryHPCBatchSpec


class Parser(CanaryParser):
    def add_argument(self, *args, **kwargs):
        kwargs.pop("group", None)
        kwargs.pop("command", None)
        return super().add_argument(*args, **kwargs)


def make_legacy_parser():
    parser = Parser()
    return LegacyParserAdapter(parser)


def test_parsing_0():
    parser = make_legacy_parser()
    setup_parser(parser)
    args = parser.parse_args(
        [
            "--hpc-scheduler-args=--account=XYZ123",
            "--hpc-scheduler-args=--licenses=pscratch",
            "--hpc-scheduler-args=--foo=bar,--baz=spam",
            "--hpc-scheduler-args=--a=b,-c d",
            "--hpc-scheduler-args=--clusters='spam,baz'",
            "--hpc-scheduler-args=--clusters='horse,fly',--licenses='foo,bar'",
        ]
    )
    assert args.canary_hpc_scheduler_args == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c d",
        "--clusters='spam,baz'",
        "--clusters='horse,fly'",
        "--licenses='foo,bar'",
    ]

    args = parser.parse_args(["--hpc-batch-spec=count:1"])
    assert args.canary_hpc_batchspec["count"] == 1
    args = parser.parse_args(["--hpc-batch-spec=duration:1"])
    assert args.canary_hpc_batchspec["duration"] == 1.0
    args = parser.parse_args(["--hpc-batch-spec=layout:atomic"])
    assert args.canary_hpc_batchspec["layout"] == "atomic"
    args = parser.parse_args(["--hpc-batch-spec=layout:flat"])
    assert args.canary_hpc_batchspec["layout"] == "flat"
    args = parser.parse_args(["--hpc-batch-spec=count:auto"])
    assert args.canary_hpc_batchspec["count"] == binpack.AUTO
    args = parser.parse_args(["--hpc-batch-spec=count:max"])
    assert args.canary_hpc_batchspec["count"] == binpack.ONE_PER_BIN

    args = parser.parse_args(["--hpc-scheduler=shell"])
    spec = getattr(args, "canary_hpc_batchspec", None) or {}
    CanaryHPCBatchSpec.validate_and_set_defaults(spec)
    setattr(args, "canary_hpc_batchspec", spec)
    assert args.canary_hpc_scheduler == "shell"
    assert args.canary_hpc_batchspec["layout"] == "flat"
    assert args.canary_hpc_batchspec["duration"] == 60 * 30
    assert args.canary_hpc_batchspec["nodes"] == "any"


def test_parsing_1():
    parser = Parser()
    setup_parser(parser)
    args = parser.parse_args(
        [
            "--scheduler-args=--account=XYZ123",
            "--scheduler-args=--licenses=pscratch",
            "--scheduler-args=--foo=bar,--baz=spam",
            "--scheduler-args=--a=b,-c d",
            "--scheduler-args=--clusters='spam,baz'",
            "--scheduler-args=--clusters='horse,fly',--licenses='foo,bar'",
        ]
    )
    assert args.canary_hpc_scheduler_args == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c d",
        "--clusters='spam,baz'",
        "--clusters='horse,fly'",
        "--licenses='foo,bar'",
    ]

    args = parser.parse_args(["--batch-spec=count:1"])
    assert args.canary_hpc_batchspec["count"] == 1
    args = parser.parse_args(["--batch-spec=duration:1"])
    assert args.canary_hpc_batchspec["duration"] == 1.0
    args = parser.parse_args(["--batch-spec=layout:atomic"])
    assert args.canary_hpc_batchspec["layout"] == "atomic"
    args = parser.parse_args(["--batch-spec=layout:flat"])
    assert args.canary_hpc_batchspec["layout"] == "flat"
    args = parser.parse_args(["--batch-spec=count:auto"])
    assert args.canary_hpc_batchspec["count"] == binpack.AUTO
    args = parser.parse_args(["--batch-spec=count:max"])
    assert args.canary_hpc_batchspec["count"] == binpack.ONE_PER_BIN

    args = parser.parse_args(["--scheduler=shell"])
    spec = getattr(args, "canary_hpc_batchspec", None) or {}
    CanaryHPCBatchSpec.validate_and_set_defaults(spec)
    setattr(args, "canary_hpc_batchspec", spec)
    assert args.canary_hpc_scheduler == "shell"
    assert args.canary_hpc_batchspec["layout"] == "flat"
    assert args.canary_hpc_batchspec["duration"] == 60 * 30
    assert args.canary_hpc_batchspec["nodes"] == "any"


def test_parsing_legacy():
    parser = make_legacy_parser()
    setup_parser(parser)
    args = parser.parse_args(
        [
            "-b",
            "option=--account=XYZ123",
            "-b",
            "option=--licenses=pscratch",
            "-b",
            "option=--foo=bar,--baz=spam",
            "-b",
            "option=--a=b,-c d",
            "-b",
            "option=--clusters='spam,baz'",
            "-b",
            "option=--clusters='horse,fly',--licenses='foo,bar'",
        ]
    )
    assert args.canary_hpc_scheduler_args == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c d",
        "--clusters='spam,baz'",
        "--clusters='horse,fly'",
        "--licenses='foo,bar'",
    ]

    args = parser.parse_args(["-b", "spec=count:1"])
    assert args.canary_hpc_batchspec["count"] == 1
    args = parser.parse_args(["-b", "spec=duration:1"])
    assert args.canary_hpc_batchspec["duration"] == 1.0
    args = parser.parse_args(["-b", "spec=layout:atomic"])
    assert args.canary_hpc_batchspec["layout"] == "atomic"
    args = parser.parse_args(["-b", "spec=layout:flat"])
    assert args.canary_hpc_batchspec["layout"] == "flat"
    args = parser.parse_args(["-b", "spec=count:auto"])
    assert args.canary_hpc_batchspec["count"] == binpack.AUTO
    args = parser.parse_args(["-b", "spec=count:max"])
    assert args.canary_hpc_batchspec["count"] == binpack.ONE_PER_BIN

    args = parser.parse_args(["-b", "scheduler=shell"])
    spec = getattr(args, "canary_hpc_batchspec", None) or {}
    CanaryHPCBatchSpec.validate_and_set_defaults(spec)
    setattr(args, "canary_hpc_batchspec", spec)
    assert args.canary_hpc_scheduler == "shell"
    assert args.canary_hpc_batchspec["layout"] == "flat"
    assert args.canary_hpc_batchspec["duration"] == 60 * 30
    assert args.canary_hpc_batchspec["nodes"] == "any"

    args = parser.parse_args(["-b", "backend=shell"])
    spec = getattr(args, "canary_hpc_batchspec", None) or {}
    CanaryHPCBatchSpec.validate_and_set_defaults(spec)
    setattr(args, "canary_hpc_batchspec", spec)
    assert args.canary_hpc_scheduler == "shell"
    assert args.canary_hpc_batchspec["layout"] == "flat"
    assert args.canary_hpc_batchspec["duration"] == 60 * 30
    assert args.canary_hpc_batchspec["nodes"] == "any"
