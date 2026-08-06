# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.config.argparsing import Parser as CanaryParser
from canary_hpc.argparsing import CanaryHPCBatchSpec
from canary_hpc.conductor import CanaryHPCConductor


class Parser(CanaryParser):
    def add_argument(self, *args, **kwargs):
        kwargs.pop("group", None)
        kwargs.pop("command", None)
        return super().add_argument(*args, **kwargs)


def make_legacy_parser():
    parser = Parser()
    CanaryHPCConductor.setup_legacy_parser(parser)
    return parser


def validate(args):
    spec = getattr(args, "hpc_batchspec", None) or {}
    CanaryHPCBatchSpec.validate_and_set_defaults(spec)
    setattr(args, "hpc_batchspec", spec)
    return args


def test_parsing_0():
    parser = Parser()
    CanaryHPCConductor.setup_legacy_parser(parser)
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
    assert args.hpc_scheduler_args == [
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
    assert args.hpc_batchspec["count"] == 1

    args = parser.parse_args(["--hpc-batch-spec=duration:1"])
    assert args.hpc_batchspec["duration"] == 1.0

    args = parser.parse_args(["--hpc-batch-spec=layout:atomic"])
    assert args.hpc_batchspec["layout"] == "atomic"

    args = parser.parse_args(["--hpc-batch-spec=layout:flat"])
    assert args.hpc_batchspec["layout"] == "flat"

    with pytest.raises(ValueError, match="count=auto"):
        parser.parse_args(["--hpc-batch-spec=count:auto"])

    args = parser.parse_args(["--hpc-batch-spec=count:max"])
    assert args.hpc_batchspec["count"] == "max"

    args = parser.parse_args(["--hpc-backend=local"])
    validate(args)

    assert args.hpc_backend == "local"
    assert args.hpc_batchspec["layout"] == "flat"
    assert args.hpc_batchspec["duration"] == 60 * 30
    assert args.hpc_batchspec["nodes"] == "same"


def test_parsing_1():
    parser = Parser()
    CanaryHPCConductor.setup_parser(parser)
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
    assert args.hpc_scheduler_args == [
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
    assert args.hpc_batchspec["count"] == 1

    args = parser.parse_args(["--batch-spec=duration:1"])
    assert args.hpc_batchspec["duration"] == 1.0

    args = parser.parse_args(["--batch-spec=layout:atomic"])
    assert args.hpc_batchspec["layout"] == "atomic"

    args = parser.parse_args(["--batch-spec=layout:flat"])
    assert args.hpc_batchspec["layout"] == "flat"

    with pytest.raises(ValueError, match="count=auto"):
        parser.parse_args(["--batch-spec=count:auto"])

    args = parser.parse_args(["--batch-spec=count:max"])
    assert args.hpc_batchspec["count"] == "max"

    args = parser.parse_args(["--backend=shell"])
    validate(args)

    assert args.hpc_backend == "shell"
    assert args.hpc_batchspec["layout"] == "flat"
    assert args.hpc_batchspec["duration"] == 60 * 30
    assert args.hpc_batchspec["nodes"] == "same"


def test_parsing_legacy():
    parser = Parser()
    CanaryHPCConductor.setup_legacy_parser(parser)
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
    assert args.hpc_scheduler_args == [
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
    assert args.hpc_batchspec["count"] == 1

    args = parser.parse_args(["-b", "spec=duration:1"])
    assert args.hpc_batchspec["duration"] == 1.0

    args = parser.parse_args(["-b", "spec=layout:atomic"])
    assert args.hpc_batchspec["layout"] == "atomic"

    args = parser.parse_args(["-b", "spec=layout:flat"])
    assert args.hpc_batchspec["layout"] == "flat"

    with pytest.raises(ValueError, match="count=auto"):
        parser.parse_args(["-b", "spec=count:auto"])

    args = parser.parse_args(["-b", "spec=count:max"])
    assert args.hpc_batchspec["count"] == "max"

    args = parser.parse_args(["-b", "backend=shell"])
    validate(args)

    assert args.hpc_backend == "shell"
    assert args.hpc_batchspec["layout"] == "flat"
    assert args.hpc_batchspec["duration"] == 60 * 30
    assert args.hpc_batchspec["nodes"] == "same"


def test_atomic_defaults_to_nodes_any_and_count_max() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic")

    CanaryHPCBatchSpec.validate_and_set_defaults(spec)

    assert spec["layout"] == "atomic"
    assert spec["nodes"] == "any"
    assert spec["count"] == "max"
    assert spec["duration"] is None


def test_atomic_count_max_valid() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,count=max")

    CanaryHPCBatchSpec.validate_and_set_defaults(spec)

    assert spec["layout"] == "atomic"
    assert spec["nodes"] == "any"
    assert spec["count"] == "max"
    assert spec["duration"] is None


def test_atomic_nodes_same_invalid() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,nodes=same,count=2")

    with pytest.raises(ValueError, match="layout=atomic requires nodes=any"):
        CanaryHPCBatchSpec.validate_and_set_defaults(spec)


def test_atomic_nodes_any_count_valid() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,nodes=any,count=2")

    CanaryHPCBatchSpec.validate_and_set_defaults(spec)

    assert spec["layout"] == "atomic"
    assert spec["nodes"] == "any"
    assert spec["count"] == 2
    assert spec["duration"] is None


def test_atomic_count_valid_with_implicit_nodes_any() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,count=2")

    CanaryHPCBatchSpec.validate_and_set_defaults(spec)

    assert spec["layout"] == "atomic"
    assert spec["nodes"] == "any"
    assert spec["count"] == 2
    assert spec["duration"] is None


def test_duration_atomic_invalid() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,nodes=any,duration=30m")

    with pytest.raises(ValueError, match="duration-targeted atomic"):
        CanaryHPCBatchSpec.validate_and_set_defaults(spec)


def test_count_zero_invalid() -> None:
    parser = Parser()
    CanaryHPCConductor.setup_parser(parser)

    with pytest.raises(ValueError, match="count <= 0"):
        parser.parse_args(["--batch-spec=count:0"])
