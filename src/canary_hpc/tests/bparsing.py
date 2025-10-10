# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from _canary.config.argparsing import Parser as CanaryParser
from canary_hpc import partitioning
from canary_hpc import setup_parser
from canary_hpc.argparsing import CanaryHPCBatchSpec


class Parser(CanaryParser):
    def add_argument(self, *args, **kwargs):
        kwargs.pop("group", None)
        kwargs.pop("command", None)
        return super().add_argument(*args, **kwargs)


def test_parsing():
    parser = Parser()
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
    assert args.canary_hpc["scheduler_args"] == [
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
    assert args.canary_hpc["batch_spec"]["count"] == 1
    args = parser.parse_args(["--hpc-batch-spec=duration:1"])
    assert args.canary_hpc["batch_spec"]["duration"] == 1.0
    args = parser.parse_args(["--hpc-batch-spec=layout:atomic"])
    assert args.canary_hpc["batch_spec"]["layout"] == "atomic"
    args = parser.parse_args(["--hpc-batch-spec=layout:flat"])
    assert args.canary_hpc["batch_spec"]["layout"] == "flat"
    args = parser.parse_args(["--hpc-batch-spec=count:auto"])
    assert args.canary_hpc["batch_spec"]["count"] == partitioning.AUTO
    args = parser.parse_args(["--hpc-batch-spec=count:max"])
    assert args.canary_hpc["batch_spec"]["count"] == partitioning.ONE_PER_BATCH

    args = parser.parse_args(["--hpc-scheduler=shell"])
    CanaryHPCBatchSpec.validate_and_set_defaults(args.canary_hpc)
    assert args.canary_hpc["scheduler"] == "shell"
    assert args.canary_hpc["batch_spec"]["layout"] == "flat"
    assert args.canary_hpc["batch_spec"]["duration"] == 60 * 30
    assert args.canary_hpc["batch_spec"]["nodes"] == "any"


def test_parsing_batch_exec():
    parser = Parser()
    setup_parser(parser)

    args = parser.parse_args(["--hpc-batch-exec=backend:slurm,batch:abcdefg,case:12345"])
    assert args.canary_hpc["batch_exec"]["backend"] == "slurm"
    assert args.canary_hpc["batch_exec"]["batch"] == "abcdefg"
    assert args.canary_hpc["batch_exec"]["case"] == "12345"

    args = parser.parse_args(["--hpc-batch-exec=backend:slurm,batch:abcdefg"])
    assert args.canary_hpc["batch_exec"]["backend"] == "slurm"
    assert args.canary_hpc["batch_exec"]["batch"] == "abcdefg"


def test_parsing_legacy():
    parser = Parser()
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
    assert args.canary_hpc["scheduler_args"] == [
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
    assert args.canary_hpc["batch_spec"]["count"] == 1
    args = parser.parse_args(["-b", "spec=duration:1"])
    assert args.canary_hpc["batch_spec"]["duration"] == 1.0
    args = parser.parse_args(["-b", "spec=layout:atomic"])
    assert args.canary_hpc["batch_spec"]["layout"] == "atomic"
    args = parser.parse_args(["-b", "spec=layout:flat"])
    assert args.canary_hpc["batch_spec"]["layout"] == "flat"
    args = parser.parse_args(["-b", "spec=count:auto"])
    assert args.canary_hpc["batch_spec"]["count"] == partitioning.AUTO
    args = parser.parse_args(["-b", "spec=count:max"])
    assert args.canary_hpc["batch_spec"]["count"] == partitioning.ONE_PER_BATCH

    args = parser.parse_args(["-b", "scheduler=shell"])
    CanaryHPCBatchSpec.validate_and_set_defaults(args.canary_hpc)
    assert args.canary_hpc["scheduler"] == "shell"
    assert args.canary_hpc["batch_spec"]["layout"] == "flat"
    assert args.canary_hpc["batch_spec"]["duration"] == 60 * 30
    assert args.canary_hpc["batch_spec"]["nodes"] == "any"

    args = parser.parse_args(["-b", "backend=shell"])
    CanaryHPCBatchSpec.validate_and_set_defaults(args.canary_hpc)
    assert args.canary_hpc["scheduler"] == "shell"
    assert args.canary_hpc["batch_spec"]["layout"] == "flat"
    assert args.canary_hpc["batch_spec"]["duration"] == 60 * 30
    assert args.canary_hpc["batch_spec"]["nodes"] == "any"


def test_parsing_batch_exec_legacy():
    parser = Parser()
    setup_parser(parser)

    args = parser.parse_args(["-b", "exec=backend:slurm,batch:abcdefg,case:12345"])
    assert args.canary_hpc["batch_exec"]["backend"] == "slurm"
    assert args.canary_hpc["batch_exec"]["batch"] == "abcdefg"
    assert args.canary_hpc["batch_exec"]["case"] == "12345"

    args = parser.parse_args(["-b", "exec=backend:slurm,batch:abcdefg"])
    assert args.canary_hpc["batch_exec"]["backend"] == "slurm"
    assert args.canary_hpc["batch_exec"]["batch"] == "abcdefg"
