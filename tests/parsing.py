# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os


def test_batch_options():
    import argparse

    from _canary.plugins.builtin.partitioning import BatchResourceSetter
    from _canary.plugins.builtin.partitioning import validate_and_set_defaults
    from _canary.util import partitioning

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
    validate_and_set_defaults(args.batch)
    assert args.batch["spec"]["layout"] == "flat"
    assert args.batch["spec"]["duration"] == 60 * 30
    assert args.batch["spec"]["nodes"] == "any"


def test_config_args():
    from _canary.config import Config
    from _canary.config.argparsing import make_argument_parser

    parser = make_argument_parser()
    args = parser.parse_args(
        [
            "-c",
            "config:debug:true",
            "-c",
            "resource_pool:nodes:1",
            "-c",
            "resource_pool:cpus_per_node:8",
            "-c",
            "resource_pool:gpus_per_node:4",
            "-e",
            "SPAM=EGGS",
        ]
    )
    config = Config()
    config.set_main_options(args)
    assert config.get("config:debug") is True
    assert config.resource_pool.pinfo("cpus_per_node") == 8
    assert config.resource_pool.pinfo("gpus_per_node") == 4
    assert config.get("environment")["set"]["SPAM"] == "EGGS"
    assert os.environ["SPAM"] == "EGGS"
    os.environ.pop("SPAM")
