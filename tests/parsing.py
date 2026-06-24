# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os

import pytest

from _canary.config import Config
from _canary.config.argparsing import HelpFormatter
from _canary.config.argparsing import Parser
from _canary.config.argparsing import make_argument_parser
from _canary.config.argparsing import safe_loads

ci_env = os.getenv("CI") is not None


def test_config_args():
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


def test_parser_preparse_plugins_debug_and_C():
    parser = make_argument_parser()

    # -p / --debug / -C should be detected; unknown things ignored; stop on known command
    ns = parser.preparse(["-p", "foo", "-d", "-C", "/tmp", "run", "--other"])
    assert ns.plugins == ["foo"]
    assert ns.debug is True
    assert ns.C == "/tmp"

    # compact forms
    ns2 = parser.preparse(["-pfoo", "-C/tmp", "run"])
    assert ns2.plugins == ["foo"]
    assert ns2.C == "/tmp"


def test_parser_addopts_from_environment(monkeypatch: pytest.MonkeyPatch):
    from _canary.config.argparsing import make_argument_parser

    parser = make_argument_parser()

    monkeypatch.setenv("CANARY_ADDOPTS", "-d -p plugA")
    argv = ["collect", "--x"]
    parser.add_opts_from_environment(argv)
    assert argv[:3] == ["-d", "-p", "plugA"]

    # Clear global addopts so only command-specific addopts apply
    monkeypatch.delenv("CANARY_ADDOPTS", raising=False)

    monkeypatch.setenv("CANARY_RUN_ADDOPTS", "--echo")
    argv2 = ["run", "--y"]
    parser.add_opts_from_environment(argv2)
    assert argv2 == ["run", "--echo", "--y"]


def test_convert_arg_line_to_args_strips_comments_and_splits():
    parser = make_argument_parser()
    assert parser.convert_arg_line_to_args("-c debug:true  # comment") == ["-c", "debug:true"]
    assert parser.convert_arg_line_to_args("   ") == []


def test_configmods_nested_and_safe_loads_types():
    parser = make_argument_parser()
    args = parser.parse_args(
        [
            "-c",
            "a:b:1",  # nested keys, value should become int
            "-c",
            "x:y:true",  # bool
            "-c",
            's:t:"hi"',  # string via json
        ]
    )

    mods = args.config_mods
    assert mods["a"]["b"] == 1
    assert mods["x"]["y"] is True
    assert mods["s"]["t"] == "hi"


def test_configmods_merges_multiple_updates_to_same_tree():
    parser = make_argument_parser()
    args = parser.parse_args(["-c", "a:b:1", "-c", "a:c:2", "-c", "a:b:3"])
    mods = args.config_mods
    assert mods["a"]["b"] == 3
    assert mods["a"]["c"] == 2


def test_environment_modification_action_sets_os_environ():
    parser = make_argument_parser()
    args = parser.parse_args(["-e", "HELLO=WORLD"])
    cfg = Config()
    cfg.set_main_options(args)

    assert cfg.get("environment")["set"]["HELLO"] == "WORLD"
    assert os.environ["HELLO"] == "WORLD"
    os.environ.pop("HELLO")


def test_environment_modification_invalid_raises():
    import argparse

    from _canary.config.argparsing import make_argument_parser

    parser = make_argument_parser()
    with pytest.raises(argparse.ArgumentTypeError):
        parser.parse_args(["-e", "NOVAL"])


def test_register_plugin_action_records_plugins():
    parser = make_argument_parser()
    args = parser.parse_args(["-p", "my.plugin", "-p", "other.plugin"])
    assert args.config_mods["plugins"] == ["my.plugin", "other.plugin"]


def test_parser_read_args_from_file_updates_parser_argv(tmp_path):
    f = tmp_path / "args.txt"
    f.write_text("-c debug:true\n", encoding="utf-8")
    parser = make_argument_parser()

    ns = parser.parse_args([f"@{f.as_posix()}"])
    assert ns.config_mods["debug"] is True
    # Parser stores the expanded argv after reading file
    assert any("debug:true" in a for a in parser.argv)


def test_helpformatter_split_lines_pad_and_wrapping(monkeypatch: pytest.MonkeyPatch):
    # Basic sanity: [pad] lines should be indented and wrapping should not crash
    from _canary.config import argparsing as ap

    # Force a deterministic terminal size so wrapping behavior is stable-ish
    monkeypatch.setattr(ap, "terminal_size", lambda: (24, 60))

    fmt = HelpFormatter(prog="x")
    lines = fmt._split_lines("[pad]this is a long line that should wrap", width=20)
    assert lines[0].startswith("  ")
    assert any("wrap" in l for l in lines)


@pytest.mark.skipif(ci_env, reason="Skip in CI")
def test_helpformatter_usage_renders():
    parser = make_argument_parser()
    # ensure our formatter class is actually in use
    assert isinstance(parser._get_formatter(), HelpFormatter)

    usage = parser.format_usage()
    assert usage.startswith("usage: canary")
    # sanity: includes known short flags
    assert "[-v]" in usage
    assert "[-q]" in usage


def test_parser_remove_argument_by_optstring_and_dest():
    parser = make_argument_parser()
    # remove by opt string
    parser.remove_argument("--banner")
    txt = parser.format_help()
    assert "--banner" not in txt

    # remove by dest
    parser.remove_argument("debug")
    txt2 = parser.format_help()
    assert "--debug" not in txt2


def test_parser_get_group_returns_existing_or_creates():
    parser = make_argument_parser()
    g1 = parser.get_group("runtime configuration")
    g2 = parser.get_group("runtime configuration")
    assert g1 is g2

    g3 = parser.get_group("new group")
    assert g3.title == "new group"


def test_safe_loads_falls_back_to_string_on_non_json():
    assert safe_loads("true") is True
    assert safe_loads("1") == 1
    assert safe_loads("not-json") == "not-json"


def _make_parser_tree() -> Parser:
    """
    Build a small nested subparser tree: report -> cdash -> create.

    Uses argparse.ArgumentParser as a stand-in for canary.Parser; the function under
    test only requires `. _actions` and argparse subparser actions.
    """
    parser = make_argument_parser()
    sp1 = parser.add_subparsers(dest="cmd")

    report = sp1.add_parser("report", prog="root report")
    parser._Parser__subcommand_parsers["report"] = report
    sp2 = report.add_subparsers(dest="report_cmd")

    cdash = sp2.add_parser("cdash", prog="root report cdash")
    sp3 = cdash.add_subparsers(dest="cdash_cmd")

    sp3.add_parser("create", prog="root report cdash create")
    return parser


def test_get_nested_subparser_returns_leaf_parser():
    parser = _make_parser_tree()
    leaf = parser.get_subparser("report::cdash::create")
    assert isinstance(leaf, argparse.ArgumentParser)
    assert leaf.prog.endswith("create")


def test_get_nested_subparser_raises_if_no_subparsers_under_current():
    parser = make_argument_parser()
    with pytest.raises(KeyError, match=r"No subparsers found under parser"):
        parser.get_subparser("report")


def test_get_nested_subparser_raises_on_unknown_subcommand():
    parser = _make_parser_tree()
    with pytest.raises(KeyError, match=r"Unknown subcommand nope\. Available:"):
        parser.get_subparser("report::nope")
