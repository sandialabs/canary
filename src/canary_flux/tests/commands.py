# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import pytest

import canary_flux
from _canary.config.argparsing import Parser


def test_flux_command_dispatch_run(monkeypatch):
    called = {}

    class FakeFluxRun:
        def execute(self, args):
            called["run"] = args
            return 17

    monkeypatch.setattr(canary_flux, "FluxRun", FakeFluxRun)

    args = argparse.Namespace(flux_command="run")
    rc = canary_flux.Flux().execute(args)

    assert rc == 17
    assert called["run"] is args


def test_flux_command_dispatch_exec(monkeypatch):
    called = {}

    class FakeFluxExec:
        def execute(self, args):
            called["exec"] = args
            return 23

    monkeypatch.setattr(canary_flux, "FluxExec", FakeFluxExec)

    args = argparse.Namespace(flux_command="exec")
    rc = canary_flux.Flux().execute(args)

    assert rc == 23
    assert called["exec"] is args


def test_flux_command_dispatch_unknown():
    args = argparse.Namespace(flux_command="bogus")

    with pytest.raises(ValueError, match="unknown subcommand"):
        canary_flux.Flux().execute(args)


def test_flux_run_parser_defaults_and_time_parsing(monkeypatch):
    """
    Avoid depending on Canary's full Run parser in this unit test by monkeypatching
    the imported Run class used by FluxRun.setup_parser.
    """

    class FakeRun:
        def setup_parser(self, parser):
            parser.add_argument("--timeout", action="append", default=None)
            parser.add_argument("--workers", type=int)
            parser.add_argument("paths", nargs="*")

    import _canary.plugins.subcommands.run as run_mod

    monkeypatch.setattr(run_mod, "Run", FakeRun)

    parser = Parser()
    canary_flux.FluxRun.setup_parser(parser)

    args = parser.parse_args(
        [
            "--timeout=queue=20m",
            "--timeout=allocation=1h",
            "--nodes=3",
            "--workers=7",
            "--submit-arg=--foo",
            "--submit-arg=--bar",
            "some/path",
        ]
    )

    assert args.flux_direct_run is True
    assert set(args.timeout) == {"queue=20m", "allocation=1h"}
    assert args.flux_nodes == 3
    assert args.workers == 7
    assert args.flux_submit_args == ["--foo", "--bar"]
    assert args.paths == ["some/path"]


def test_flux_exec_parser_sets_flux_exec_and_disables_direct_run():
    parser = Parser()
    canary_flux.FluxExec.setup_parser(parser)

    args = parser.parse_args(["--session", "session-1", "abc123"])

    assert args.flux_exec is True
    assert args.flux_direct_run is False
    assert args.session == "session-1"
    assert args.spec == "abc123"
