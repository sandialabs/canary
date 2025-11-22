# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os


def test_config_args():
    from _canary.config import Config
    from _canary.config.argparsing import make_argument_parser

    parser = make_argument_parser()
    args = parser.parse_args(
        [
            "-c",
            "debug:true",
            "-c",
            "resource_pool:cpus:8",
            "-c",
            "resource_pool:gpus:4",
            "-e",
            "SPAM=EGGS",
        ]
    )
    config = Config()
    config.set_main_options(args)
    assert config.get("debug") is True
    assert config.getoption("resource_pool_mods") == {"cpus": 8, "gpus": 4}
    assert config.get("environment")["set"]["SPAM"] == "EGGS"
    assert os.environ["SPAM"] == "EGGS"
    os.environ.pop("SPAM")
