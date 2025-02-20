import argparse
import os


def test_batch_args_backward():
    import _canary.plugins.subcommands.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(
        [
            "-l",
            "batch:option=--account=XYZ123",
            "-l",
            "batch:option=--licenses=pscratch",
            "-l",
            "batch:option=--foo=bar,--baz=spam",
            "-l",
            "batch:option=--a=b,-c d",
        ]
    )
    assert args.batch["options"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c d",
    ]


def test_batch_options():
    import _canary.plugins.subcommands.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
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
        ]
    )
    assert args.batch["options"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c d",
    ]


def test_parsing_backward():
    import _canary.plugins.subcommands.common as common

    parser = argparse.ArgumentParser()
    common.add_resource_arguments(parser)
    args = parser.parse_args(["-l", "test:timeoutx=2.0"])
    assert args.timeout_multiplier == 2.0


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
    config = Config.factory()
    config.set_main_options(args)
    assert config.debug is True
    assert config.resource_pool.pinfo("cpus_per_node") == 8
    assert config.resource_pool.pinfo("gpus_per_node") == 4
    assert config.environment.mods["set"]["SPAM"] == "EGGS"
    assert os.environ["SPAM"] == "EGGS"
    os.environ.pop("SPAM")
