import argparse
import os


def test_batch_args_backward():
    import _nvtest.command.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(
        [
            "-l",
            "batch:args=--account=XYZ123",
            "-l",
            "batch:args=--licenses=pscratch",
            "-l",
            "batch:args=--foo=bar --baz=spam",
            "-l",
            "batch:args='--a=b -c d'",
        ]
    )
    assert args.batch["scheduler_args"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c",
        "d",
    ]


def test_batch_args():
    import _nvtest.command.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(
        [
            "-b",
            "args=--account=XYZ123",
            "-b",
            "args=--licenses=pscratch",
            "-b",
            "args=--foo=bar --baz=spam",
            "-b",
            "args='--a=b -c d'",
        ]
    )
    assert args.batch["scheduler_args"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c",
        "d",
    ]


def test_parsing_backward():
    import _nvtest.command.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(["-l", "test:timeoutx=2.0"])
    assert args.timeout_multiplier == 2.0


def test_config_args():
    from _nvtest.config import Config
    from _nvtest.config.argparsing import make_argument_parser

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
    config = Config.factory()
    config.set_main_options(args)
    assert config.debug is True
    assert config.resource_pool.pinfo("cpus_per_node") == 8
    assert config.resource_pool.pinfo("gpus_per_node") == 4
    assert config.variables["SPAM"] == "EGGS"
    assert os.environ["SPAM"] == "EGGS"
    os.environ.pop("SPAM")
