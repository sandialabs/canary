# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


def test_batch_options():
    import argparse

    from canary_hpc import partitioning
    from canary_hpc.batchopts import BatchResourceSetter

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b",
        action=BatchResourceSetter,
        metavar="resource",
        dest="batch",
        help=BatchResourceSetter.help_page("-b"),
    )
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
    assert args.batch["options"] == [
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
    assert args.batch["spec"]["count"] == 1
    args = parser.parse_args(["-b", "spec=duration:1"])
    assert args.batch["spec"]["duration"] == 1.0
    args = parser.parse_args(["-b", "spec=layout:atomic"])
    assert args.batch["spec"]["layout"] == "atomic"
    args = parser.parse_args(["-b", "spec=layout:flat"])
    assert args.batch["spec"]["layout"] == "flat"
    args = parser.parse_args(["-b", "spec=count:auto"])
    assert args.batch["spec"]["count"] == partitioning.AUTO
    args = parser.parse_args(["-b", "spec=count:max"])
    assert args.batch["spec"]["count"] == partitioning.ONE_PER_BATCH

    args = parser.parse_args(["-b", "scheduler=shell"])
    BatchResourceSetter.validate_and_set_defaults(args.batch)
    assert args.batch["spec"]["layout"] == "flat"
    assert args.batch["spec"]["duration"] == 60 * 30
    assert args.batch["spec"]["nodes"] == "any"

    args = parser.parse_args(["-b", "exec=backend:slurm,batch:abcdefg"])
    assert args.batch["exec"]["backend"] == "slurm"
    assert args.batch["exec"]["batch"] == "abcdefg"

    args = parser.parse_args(["-b", "exec=backend:slurm,batch:abcdefg,case:12345"])
    assert args.batch["exec"]["backend"] == "slurm"
    assert args.batch["exec"]["batch"] == "abcdefg"
    assert args.batch["exec"]["case"] == "12345"
