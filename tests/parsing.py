import argparse
import os


def test_batch_args():
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
    assert args.rh["batch:scheduler_args"] == [
        "--account=XYZ123",
        "--licenses=pscratch",
        "--foo=bar",
        "--baz=spam",
        "--a=b",
        "-c",
        "d",
    ]
    assert args.rh["batch:batched"] is True
    assert args.batched_invocation is True


def test_config_args():
    from _nvtest.config import Config
    from _nvtest.config.argparsing import make_argument_parser

    parser = make_argument_parser()
    args = parser.parse_args(
        [
            "-c",
            "config:debug:true",
            "-c",
            "machine:cpu_count:8",
            "-c",
            "machine:gpu_count:4",
            "-e",
            "SPAM=EGGS",
        ]
    )
    try:
        config = Config()
        config.set_main_options(args)
        print(config.scopes["command_line"])
        cls = config.scopes["command_line"]
        assert cls["config"]["debug"] is True
        assert cls["machine"]["cpu_count"] == 8
        assert cls["machine"]["gpu_count"] == 4
        assert cls["variables"]["SPAM"] == "EGGS"
        assert os.environ["SPAM"] == "EGGS"
    finally:
        os.environ.pop("SPAM")
