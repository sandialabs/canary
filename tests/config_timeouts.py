# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import canary
from _canary.config import timeout_multiplier
from _canary.config.schemas import environment_variable_schema
from _canary.core.rules import SessionTimeoutRule
from _canary.session.workspace import Workspace


def test_timeout_environment_variables_map_into_run_timeout() -> None:
    validated = environment_variable_schema.validate(
        {"CANARY_TIMEOUT_FAST": "7", "CANARY_TIMEOUT_DEFAULT": "11"}
    )

    assert validated == {"timeout": {"fast": 7.0, "default": 11.0}}


def test_timeout_multiplier_falls_back_to_config_when_cli_timeouts_exist_without_multiplier() -> (
    None
):
    with canary.config.override() as cfg:
        cfg.options = argparse.Namespace(timeout={"fast": 10.0})
        cfg.data = {"run": {"timeout": {"multiplier": 3.0}}}

        assert timeout_multiplier() == 3.0


def test_timeout_multiplier_prefers_cli_multiplier_over_config() -> None:
    with canary.config.override() as cfg:
        cfg.options = argparse.Namespace(timeout={"fast": 10.0, "multiplier": 4.0})
        cfg.data = {"run": {"timeout": {"multiplier": 3.0}}}

        assert timeout_multiplier() == 4.0


def test_workspace_run_uses_session_timeout_from_config_when_cli_timeout_missing(tmp_path) -> None:
    proj = tmp_path / "project"
    proj.mkdir()

    with canary.config.override() as cfg:
        cfg.options = argparse.Namespace(timeout=None, config_mods=None)
        cfg.data = {"run": {"timeout": {"session": 13.0}}}

        ws = Workspace.create(proj)
        captured: list[object] = []

        class DummySelector:
            def __init__(self, jobs, workspace=None):
                self.jobs = jobs

            def add_rule(self, rule):
                captured.append(rule)

            def run(self):
                return None

        jobs: list[object] = []

        ws.construct_jobs = lambda specs, session_dir: jobs  # type: ignore[method-assign]

        import _canary.session.workspace as workspace_mod

        original_selector = workspace_mod.select.RuntimeSelector
        workspace_mod.select.RuntimeSelector = DummySelector  # type: ignore[assignment]
        try:
            try:
                ws.run(specs=[], view_t=None)
            except Exception:
                # The rest of the run path is not under test here.
                pass
        finally:
            workspace_mod.select.RuntimeSelector = original_selector  # type: ignore[assignment]

    session_rules = [rule for rule in captured if isinstance(rule, SessionTimeoutRule)]
    assert len(session_rules) == 1
    assert session_rules[0].timeout == 13.0
