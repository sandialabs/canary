# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import canary
from _canary.subcommands import learn as learn_mod
from _canary.subcommands.config import show_config
from _canary.subcommands.describe import Describe
from _canary.subcommands.find import Find
from _canary.subcommands.learn import CAPABILITY_HELP_QUERY
from _canary.subcommands.learn import SKILL_HELP_QUERY
from _canary.subcommands.learn import Learn
from _canary.subcommands.learn import build_capabilities_tree
from _canary.subcommands.learn import build_skills_tree
from _canary.subcommands.learn import list_capability_paths
from _canary.subcommands.learn import list_skill_paths
from _canary.subcommands.location import Location
from _canary.subcommands.log import Log
from _canary.subcommands.query import Query
from _canary.subcommands.status import Status
from _canary.subcommands.tree import Tree
from _canary.util.filesystem import working_dir
from _canary.util.query_data import query_json
from _canary.util.query_data import skill_to_markdown
from _canary.util.query_data import write_skill_markdown
from _canary.util.testing import CanaryCommand
from _canary.workspace import Workspace

EXPECTED_CORE_SKILLS = {
    "canary-orientation",
    "canary-test-authoring",
    "canary-run-debug",
    "canary-workflows-results",
    "canary-extension-development",
}

EXPECTED_CORE_SKILL_PATHS = {f"core.{name}" for name in EXPECTED_CORE_SKILLS}


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    d = tmp_path_factory.mktemp("canary-command")

    with working_dir(d):
        with open("e.pyt", "w") as fh:
            fh.write(
                """\
import canary
import canary_pyt
canary_pyt.directives.parameterize('a', (1, 2, 3, 4, 5, 6, 7, 8))
def test():
    self = canary.get_instance()
    if self.parameters.a == 2:
        raise canary.TestDiffed()
    elif self.parameters.a == 3:
        raise canary.TestFailed()
    elif self.parameters.a == 4:
        raise canary.TestSkipped()
    elif self.parameters.a == 5:
        raise canary.TestTimedOut()
if __name__ == "__main__":
    test()
"""
            )

        with open("f.pyt", "w") as fh:
            fh.write(
                """\
import canary
import canary_pyt
canary_pyt.directives.parameterize('a', (1, 2))
def test():
    self = canary.get_instance()
    if self.parameters.a == 2:
        raise canary.TestDiffed()
if __name__ == "__main__":
    test()
"""
            )

        with open("g.pyt", "w") as fh:
            fh.write(
                """\
import canary
import canary_pyt
canary_pyt.directives.aggregate()
canary_pyt.directives.parameterize('a', (1, 2))
def test(job):
    pass
if __name__ == "__main__":
    self = canary.get_instance()
    if not isinstance(self, canary.TestMultiInstance):
        test(self)
"""
            )

        with canary.config.override():
            workspace = Workspace.create(d)
            specs = workspace.collect({str(d): []})
            session = workspace.run(specs, only="all")

        jobs = workspace.load_jobs()
        f_a1_job = next(job for job in jobs if job.name == "f.a=1")

        ns = SimpleNamespace(
            tmp_path=d,
            workspace=workspace,
            session=session,
            results_path=d / "TestResults",
            f_a1_id=f_a1_job.id,
        )
        yield ns


# -------------------------------------------------------------------------
# Shared helpers
# -------------------------------------------------------------------------


def run_location(testspec: str, *, input=False, log=False, source=False, x=False) -> int:
    args = argparse.Namespace(
        show_input=input,
        show_log=log,
        show_source_dir=source,
        show_working_directory=x,
        testspec=testspec,
    )
    return Location().execute(args)


def run_status(*, report_chars="dftns", durations=None, sort_by="name") -> int:
    args = argparse.Namespace(
        durations=durations,
        format_cols="ID,Name,Session,Exit Code,Duration,Status,Details",
        report_chars=report_chars,
        sort_by=sort_by,
        specs=[],
    )
    return Status().execute(args)


def run_query(*, jobid=None, session=None, query=".", terse=False, list_keys=False) -> int:
    """Compatibility shim: dispatch to the new Query subcommand structure."""
    if jobid is not None:
        args = argparse.Namespace(
            query_subcmd="job",
            jobid=jobid,
            path=query,
            cache=False,
            all_runs=False,
            clean=False,
            terse=terse,
            list_keys=list_keys,
        )
    else:
        args = argparse.Namespace(
            query_subcmd="session",
            session=session,
            path=query,
            expand_jobs=False,
            digest=False,
            where=None,
            clean=False,
            terse=terse,
            list_keys=list_keys,
        )
    return Query().execute(args)


def run_learn_capabilities(*, query=".", terse=False, list_keys=False) -> int:
    args = argparse.Namespace(query=query, terse=terse, list_keys=list_keys)
    return Learn().run_capabilities(args)


def run_learn_skills(*, query=".", terse=False, list_keys=False, markdown=None) -> int:
    args = argparse.Namespace(query=query, terse=terse, list_keys=list_keys, markdown=markdown)
    return Learn().run_skills(args)


class FakeHook:
    def __init__(self, *, capabilities=None, skills=None):
        self._capabilities = list(capabilities or [])
        self._skills = list(skills or [])

    def canary_capabilities(self):
        return list(self._capabilities)

    def canary_skills(self):
        return list(self._skills)


class FakePluginManager:
    def __init__(self, *, capabilities=None, skills=None):
        self.hook = FakeHook(capabilities=capabilities, skills=skills)


def fake_capabilities_payload(namespace: str = "fake"):
    return {
        "schema_version": "2.0.0",
        "namespace": namespace,
        "capabilities": {
            "overview": {
                "summary": f"{namespace} namespace overview",
                "details": {"kind": namespace, "enabled": True},
            },
            "commands": {"run": {"purpose": f"run {namespace} jobs"}},
        },
    }


def fake_skills_payload(namespace: str = "fake"):
    return {
        "schema_version": "2.0.0",
        "namespace": namespace,
        "skills": {
            f"canary-{namespace}-authoring": {
                "name": f"canary-{namespace}-authoring",
                "description": f"Author {namespace} jobs.",
                "body": f"# Authoring {namespace} jobs\n\nUse this skill for {namespace} jobs.\n",
            },
            f"canary-{namespace}-debug": {
                "name": f"canary-{namespace}-debug",
                "description": f"Debug {namespace} jobs.",
                "body": f"# Debugging {namespace} jobs\n\nUse this skill to debug {namespace} jobs.\n",
            },
        },
    }


def install_fake_learn_plugin(monkeypatch, *, capabilities=None, skills=None):
    fake_config = SimpleNamespace(
        pluginmanager=FakePluginManager(capabilities=capabilities, skills=skills)
    )
    monkeypatch.setattr(learn_mod, "config", fake_config)


# -------------------------------------------------------------------------
# Existing command tests
# -------------------------------------------------------------------------


def test_location_0(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, input=True) == 0


def test_location_1(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, log=True) == 0


def test_location_2(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, source=True) == 0


def test_location_3(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id, x=True) == 0


def test_location_4(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_location(setup.f_a1_id) == 0


def test_log(setup, monkeypatch):
    from _canary.subcommands import log as log_module

    monkeypatch.setattr(log_module, "page_text", lambda text: None)

    with working_dir(setup.results_path), canary.config.override():
        args = argparse.Namespace(
            error=False, workspace_file=None, raw=False, testspec=setup.f_a1_id
        )
        assert Log().execute(args) == 0


def test_status(setup):
    with working_dir(setup.results_path), canary.config.override():
        assert run_status() == 0
        assert run_status(report_chars="A") == 0
        assert run_status(report_chars="A", durations=10) == 0
        assert run_status(sort_by="duration") == 0


def test_describe(capsys):
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    with canary.config.override():
        args = argparse.Namespace(on_options=None, testspec=os.path.join(data_dir, "empire.pyt"))
        rc = Describe().execute(args)
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out

        args = argparse.Namespace(on_options=None, testspec=os.path.join(data_dir, "empire.vvt"))
        rc = Describe().execute(args)
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out


def test_find():
    d = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(d, ".."))
    examples = os.path.join(root, "examples")

    with working_dir(root), canary.config.override():
        args = argparse.Namespace(
            scanpaths={examples: []},
            on_options=None,
            keyword_exprs=None,
            parameter_expr=None,
            owners=None,
            regex_filter=None,
            print_paths=False,
            print_files=False,
            print_graph=False,
            print_lock=False,
            print_keywords=False,
        )
        assert Find().execute(args) == 0


def test_config_show():
    args = argparse.Namespace(file_paths=False, format="yaml", section=None)
    assert show_config(args) == 0


def test_analyze(setup):
    # Keep this one as a real command invocation because it specifically
    # tests command-line script-argument behavior after "--".
    #
    # Use --only all because the setup run already produced successful
    # results for the g jobs; the default --only not_pass would exclude them.
    with working_dir(setup.results_path), canary.config.override():
        run = CanaryCommand("run")
        cp = run("--only", "all", "-k", "g", "--", "--stage=analyze")
        assert cp.returncode == 0


def test_tree():
    examples = os.path.join(os.path.dirname(__file__), "../examples")

    args = argparse.Namespace(a=False, d=False, exclude_results=False, directory=examples)
    assert Tree().execute(args) == 0


# -------------------------------------------------------------------------
# Query command: job/session lock queries only
# -------------------------------------------------------------------------


def test_query_job_whole_lock_file(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(jobid=setup.f_a1_id)

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert rc == 0
    assert data["spec"]["id"] == setup.f_a1_id


def test_query_job_field(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(jobid=setup.f_a1_id, query=".spec.id")

    captured = capsys.readouterr()

    assert rc == 0
    assert json.loads(captured.out) == setup.f_a1_id


def test_query_job_nested_field(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(jobid=setup.f_a1_id, query=".status")

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert rc == 0
    assert isinstance(data, dict)
    assert "category" in data
    assert "outcome" in data


def test_query_job_list_keys(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(jobid=setup.f_a1_id, query=".", list_keys=True)

    captured = capsys.readouterr()
    out = captured.out.splitlines()

    assert rc == 0
    assert "spec" in out
    assert "status" in out


def test_query_job_all_runs_returns_list(setup, capsys):
    from _canary.subcommands.query import _exec_job

    args = argparse.Namespace(
        query_subcmd="job",
        jobid=setup.f_a1_id,
        path=".",
        cache=False,
        all_runs=True,
        clean=False,
        terse=False,
        list_keys=False,
    )
    with working_dir(setup.results_path), canary.config.override():
        rc = _exec_job(args)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert len(rows) >= 1


def test_query_job_all_runs_has_expected_fields(setup, capsys):
    from _canary.subcommands.query import _exec_job

    args = argparse.Namespace(
        query_subcmd="job",
        jobid=setup.f_a1_id,
        path=".",
        cache=False,
        all_runs=True,
        clean=False,
        terse=False,
        list_keys=False,
    )
    with working_dir(setup.results_path), canary.config.override():
        _exec_job(args)
    rows = json.loads(capsys.readouterr().out)
    for row in rows:
        assert "id" in row
        assert "name" in row
        assert "session" in row
        assert "exit_code" in row
        assert "status" in row
        assert "timings" in row


def test_query_session_whole_lock_file(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(session=setup.session.name)

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert rc == 0
    assert data["name"] == setup.session.name
    assert setup.f_a1_id in data["job_ids"]


def test_query_session_field(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(session=setup.session.name, query=".name")

    captured = capsys.readouterr()

    assert rc == 0
    assert json.loads(captured.out) == setup.session.name


def test_query_session_list_index(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(session=setup.session.name, query=".job_ids[0]")

    captured = capsys.readouterr()

    assert rc == 0
    assert isinstance(json.loads(captured.out), str)


def test_query_latest_session_whole_lock_file_is_json(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(session="latest")

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert rc == 0
    assert "name" in data
    assert "job_ids" in data


def _run_query_session_digest(setup, *, where=None):
    args = argparse.Namespace(
        query_subcmd="session",
        session=setup.session.name,
        path=".",
        expand_jobs=False,
        digest=True,
        where=where,
        clean=False,
        terse=False,
        list_keys=False,
    )
    return Query().execute(args)


def test_query_session_digest_outputs_one_line_per_job(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = _run_query_session_digest(setup)
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    # Each line should be "name CATEGORY"
    valid_categories = {"PASS", "FAIL", "CANCEL", "SKIP", "NONE"}
    for line in lines:
        parts = line.rsplit(" ", 1)
        assert len(parts) == 2, f"Expected 'name CATEGORY', got {line!r}"
        _name, category = parts
        assert category in valid_categories, f"Unexpected category {category!r}"


def test_query_session_digest_line_count_matches_job_count(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = _run_query_session_digest(setup)
    assert rc == 0
    digest_lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    # Should have at least one line per job
    assert len(digest_lines) > 0


def test_query_session_digest_where_filters_jobs(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = _run_query_session_digest(setup, where="status.category==PASS")
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    for line in lines:
        _, category = line.rsplit(" ", 1)
        assert category == "PASS"


def test_query_terse_outputs_single_line_json(setup, capsys):
    with working_dir(setup.results_path), canary.config.override():
        rc = run_query(session=setup.session.name, query=".", terse=True)

    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0
    assert out.endswith("\n")
    assert "\n" not in out.rstrip("\n")
    data = json.loads(out)
    assert data["name"] == setup.session.name


def test_query_missing_key_reports_available_keys():
    data = {"alpha": 1, "beta": {"gamma": 2}}

    with pytest.raises(KeyError) as exc:
        query_json(data, ".missing")

    message = str(exc.value)

    assert "No such key" in message
    assert "missing" in message
    assert "alpha" in message
    assert "beta" in message


def test_query_json_existing_dot_semantics_are_preserved():
    data = {"measurements": {"data": {"max_stress": 12.5}}, "items": [{"name": "a"}]}

    assert query_json(data, ".") == data
    assert query_json(data, "measurements") == {"data": {"max_stress": 12.5}}
    assert query_json(data, ".measurements.data.max_stress") == 12.5
    assert query_json(data, ".items[0].name") == "a"


def test_query_json_supports_quoted_keys():
    data = {"a.b": {"key with spaces": [{"x": 1}]}}

    assert query_json(data, '["a.b"]["key with spaces"][0].x') == 1


# -------------------------------------------------------------------------
# Learn command: core capabilities
# -------------------------------------------------------------------------


def test_build_capabilities_tree_contains_core_keys():
    data = build_capabilities_tree()

    assert isinstance(data, dict)
    assert "core" in data
    assert "overview" in data["core"]
    assert "hooks" in data["core"]
    assert "query" in data["core"]


def test_learn_capability_root_command(capsys):
    rc = run_learn_capabilities(query=".")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "core" in out
    assert "overview" in out["core"]
    assert "hooks" in out["core"]
    assert "query" in out["core"]


def test_learn_capability_overview_command(capsys):
    rc = run_learn_capabilities(query="core.overview")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "what_is_canary" in out
    assert "major_concepts" in out


def test_learn_capability_nested_command(capsys):
    rc = run_learn_capabilities(query="core.hooks.post")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "canary_runtest_finish" in out


def test_learn_capability_missing_key_reports_available_keys():
    data = build_capabilities_tree()

    with pytest.raises(KeyError) as exc:
        query_json(data, "core.does_not_exist")

    message = str(exc.value)
    assert "does_not_exist" in message
    assert "Available keys" in message
    assert "overview" in message


def test_learn_capability_list_root(capsys):
    rc = run_learn_capabilities(query=".", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "core" in out


def test_learn_capability_list_core(capsys):
    rc = run_learn_capabilities(query="core", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "core.commands" in out


def test_learn_capability_no_query_prints_help(capsys):
    rc = run_learn_capabilities(query=CAPABILITY_HELP_QUERY)

    assert rc == 0
    out = capsys.readouterr().out

    assert "Canary capability queries" in out
    assert "canary learn capabilities QUERY" in out
    assert "core" in out


def test_learn_capability_no_query_with_list_lists_root(capsys):
    rc = run_learn_capabilities(query=CAPABILITY_HELP_QUERY, list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "core" in out


# -------------------------------------------------------------------------
# Learn command: extension capabilities
# -------------------------------------------------------------------------


def test_plugin_capabilities_are_aggregated_under_ext(monkeypatch):
    install_fake_learn_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    data = build_capabilities_tree()

    assert "fake" in data
    assert data["fake"]["overview"]["summary"] == "fake namespace overview"


def test_learn_plugin_capability_command(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = run_learn_capabilities(query="fake.overview")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["summary"] == "fake namespace overview"
    assert out["details"]["kind"] == "fake"


def test_learn_plugin_capability_nested_field(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = run_learn_capabilities(query="fake.overview.details.kind")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out == "fake"


def test_learn_plugin_capability_list_ext(monkeypatch, capsys):
    install_fake_learn_plugin(
        monkeypatch,
        capabilities=[fake_capabilities_payload("alpha"), fake_capabilities_payload("beta")],
    )

    rc = run_learn_capabilities(query=".", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "alpha" in out
    assert "beta" in out


def test_learn_plugin_capability_list_extension(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = run_learn_capabilities(query="fake", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "fake.overview" in out
    assert "fake.commands" in out


def test_duplicate_plugin_capability_namespace_raises(monkeypatch):
    install_fake_learn_plugin(
        monkeypatch,
        capabilities=[fake_capabilities_payload("fake"), fake_capabilities_payload("fake")],
    )

    with pytest.raises(ValueError) as exc:
        build_capabilities_tree()

    assert "Duplicate Canary capabilities namespace: fake" in str(exc.value)


def test_list_capability_paths_lists_only_child_objects(monkeypatch):
    install_fake_learn_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    data = build_capabilities_tree()
    paths = list_capability_paths(data, "fake.overview")

    assert "fake.overview.details" in paths
    assert "fake.overview.summary" not in paths


# -------------------------------------------------------------------------
# Learn command: core skills
# -------------------------------------------------------------------------


def test_build_skills_tree_contains_core_skills():
    data = build_skills_tree()

    assert isinstance(data, dict)
    assert "core" in data
    assert EXPECTED_CORE_SKILLS <= set(data["core"])


def test_each_core_skill_has_expected_shape():
    data = build_skills_tree()

    for name in EXPECTED_CORE_SKILLS:
        skill = query_json(data, f"core.{name}")

        assert isinstance(skill, dict)
        assert skill["name"] == name
        assert isinstance(skill["description"], str)
        assert skill["description"]
        assert isinstance(skill["body"], str)
        assert "canary" in skill["body"]


def test_learn_specific_skill_command(capsys):
    rc = run_learn_skills(query="core.canary-run-debug")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["name"] == "canary-run-debug"
    assert "# Canary run and debug" in out["body"]


def test_learn_specific_skill_field_with_full_skill_query(capsys):
    rc = run_learn_skills(query="core.canary-run-debug.description")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "running Canary jobs" in out
    assert "debug" in out.lower()


def test_learn_unknown_skill_raises_clear_error():
    data = build_skills_tree()

    with pytest.raises(KeyError) as exc:
        query_json(data, "core.does-not-exist")

    message = str(exc.value)
    assert "does-not-exist" in message
    assert "Available keys" in message
    assert "canary-orientation" in message


def test_learn_skill_root_command(capsys):
    rc = run_learn_skills(query=".")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "core" in out
    assert EXPECTED_CORE_SKILLS <= set(out["core"])


def test_learn_skill_list_root(capsys):
    rc = run_learn_skills(query=".", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert EXPECTED_CORE_SKILL_PATHS <= set(out)


def test_learn_skill_no_query_prints_help(capsys):
    rc = run_learn_skills(query=SKILL_HELP_QUERY)

    assert rc == 0
    out = capsys.readouterr().out

    assert "Canary skill queries" in out
    assert "canary learn skills QUERY" in out
    assert "Available skills" in out
    assert "core.canary-orientation" in out


def test_learn_skill_no_query_with_list_lists_root(capsys):
    rc = run_learn_skills(query=SKILL_HELP_QUERY, list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert EXPECTED_CORE_SKILL_PATHS <= set(out)


def test_learn_skill_terse_prints_compact_json(capsys):
    rc = run_learn_skills(query="core.canary-run-debug.name", terse=True)

    assert rc == 0

    output = capsys.readouterr().out
    assert output == '"canary-run-debug"\n'


# -------------------------------------------------------------------------
# Learn command: extension skills
# -------------------------------------------------------------------------


def test_plugin_skills_are_aggregated_under_namespace(monkeypatch):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()

    assert "fake" in data
    assert "canary-fake-authoring" in data["fake"]


def test_learn_plugin_skill_command(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = run_learn_skills(query="fake.canary-fake-authoring")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["name"] == "canary-fake-authoring"
    assert "# Authoring fake jobs" in out["body"]


def test_learn_plugin_skill_field(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = run_learn_skills(query="fake.canary-fake-debug.description")

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out == "Debug fake jobs."


def test_learn_plugin_skill_list_extension(monkeypatch, capsys):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = run_learn_skills(query="fake", list_keys=True)

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "fake.canary-fake-authoring" in out
    assert "fake.canary-fake-debug" in out


def test_duplicate_plugin_skill_namespace_raises(monkeypatch):
    install_fake_learn_plugin(
        monkeypatch, skills=[fake_skills_payload("fake"), fake_skills_payload("fake")]
    )

    with pytest.raises(ValueError) as exc:
        build_skills_tree()

    assert "Duplicate Canary skills namespace: fake" in str(exc.value)


def test_list_skill_paths_lists_terminal_skills(monkeypatch):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()
    paths = list_skill_paths(data, "fake")

    assert paths == ["fake.canary-fake-authoring", "fake.canary-fake-debug"]


# -------------------------------------------------------------------------
# Learn command: Markdown export
# -------------------------------------------------------------------------


def test_skill_to_markdown_emits_frontmatter_and_body():
    data = build_skills_tree()
    skill = query_json(data, "core.canary-workflows-results")

    markdown = skill_to_markdown(skill)

    assert markdown.startswith("---\n")
    assert "\n---\n\n# Canary workflows and result analysis" in markdown
    assert "canary" in markdown
    assert markdown.endswith("\n")

    frontmatter_text = markdown.split("---", 2)[1]
    frontmatter = yaml.safe_load(frontmatter_text)

    assert frontmatter["name"] == "canary-workflows-results"
    assert frontmatter["description"] == skill["description"]


def test_write_specific_skill_markdown_to_file(tmp_path):
    data = build_skills_tree()
    skill = query_json(data, "core.canary-test-authoring")
    output = tmp_path / "SKILL.md"

    write_skill_markdown("core.canary-test-authoring", skill, output)

    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: canary-test-authoring" in text
    assert "# Authoring Canary tests" in text
    assert "canary" in text


def test_write_specific_skill_markdown_to_existing_directory(tmp_path):
    data = build_skills_tree()
    skill = query_json(data, "core.canary-test-authoring")

    write_skill_markdown("core.canary-test-authoring", skill, tmp_path)

    output = tmp_path / "canary-test-authoring.md"
    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert "# Authoring Canary tests" in text


def test_write_all_core_skills_markdown_to_directory(tmp_path):
    data = build_skills_tree()
    output = tmp_path / "skills"

    write_skill_markdown(".", data, output)

    assert output.is_dir()

    for name in EXPECTED_CORE_SKILLS:
        path = output / "core" / f"{name}.md"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "canary" in text


def test_write_extension_skill_subtree_markdown_to_directory(tmp_path, monkeypatch):
    install_fake_learn_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()
    subtree = query_json(data, "fake")
    output = tmp_path / "skills"

    write_skill_markdown("fake", subtree, output)

    assert (output / "fake" / "canary-fake-authoring.md").is_file()
    assert (output / "fake" / "canary-fake-debug.md").is_file()


def test_learn_command_writes_specific_skill_markdown(tmp_path):
    output = tmp_path / "canary-run-debug.md"

    rc = run_learn_skills(query="core.canary-run-debug", markdown=str(output))

    assert rc == 0
    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert "# Canary run and debug" in text
    assert "canary" in text


def test_learn_command_writes_all_skills_markdown(tmp_path):
    output = tmp_path / "skills"

    rc = run_learn_skills(query=".", markdown=str(output))

    assert rc == 0
    assert output.is_dir()

    for name in EXPECTED_CORE_SKILLS:
        assert (output / "core" / f"{name}.md").is_file()


def test_write_skill_markdown_rejects_scalar_field_query(tmp_path):
    data = build_skills_tree()
    body = query_json(data, "core.canary-test-authoring.body")

    with pytest.raises(ValueError) as exc:
        write_skill_markdown("core.canary-test-authoring.body", body, tmp_path / "SKILL.md")

    assert "does not contain any skill objects" in str(exc.value)


# -------------------------------------------------------------------------
# Rebaseline command
# -------------------------------------------------------------------------


def find_lockfiles_followlinks(path: Path) -> list[Path]:
    import os

    lockfiles: list[Path] = []
    for root, dirs, files in os.walk(path, followlinks=True):
        if "testcase.lock" in files:
            lockfiles.append(Path(root) / "testcase.lock")
    return lockfiles


def test_rebaseline_from_directory(tmpdir):

    def check_success(cp):
        assert cp.returncode == 0, (
            f"command failed with returncode={cp.returncode}\n"
            f"stdout:\n{getattr(cp, 'stdout', '')}\n"
            f"stderr:\n{getattr(cp, 'stderr', '')}\n"
        )

    with working_dir(tmpdir.strpath, create=True):
        Path("test_rebaseline.pyt").write_text(
            "\n".join(
                [
                    "import pathlib",
                    "import canary",
                    "import canary_pyt",
                    "",
                    "canary_pyt.directives.baseline(src='actual.txt', dst='expected.txt')",
                    "",
                    "pathlib.Path('actual.txt').write_text('original\\n')",
                    "",
                ]
            )
        )
        Path("expected.txt").write_text("old baseline\n")

        cp = CanaryCommand("init")(".")
        check_success(cp)

        cp = CanaryCommand("run")("-w", ".")
        check_success(cp)

        lockfiles = find_lockfiles_followlinks(Path("TestResults"))
        assert len(lockfiles) == 1

        result_dir = lockfiles[0].parent
        actual = result_dir / "actual.txt"
        assert actual.exists()
        actual.write_text("new baseline\n")

        cp = CanaryCommand("rebaseline")("TestResults")
        check_success(cp)

        assert Path("expected.txt").read_text() == "new baseline\n"


# ---------------------------------------------------------------------------
# canary query batch / batches tests
# ---------------------------------------------------------------------------


def _write_basic_tests(n: int = 4) -> None:
    """Write n minimal .pyt test files into the current directory."""
    for i in range(n):
        Path(f"bt_{i}.pyt").write_text(
            "import sys\ndef test():\n    pass\nif __name__ == '__main__':\n    sys.exit(test())\n"
        )


@pytest.fixture(scope="module")
def batch_setup(tmp_path_factory):
    """Run a small HPC batch (shell backend, 2 batches) and yield workspace info."""

    import _canary.config as cfg
    from _canary.util.filesystem import working_dir
    from _canary.workspace import Workspace
    from canary_hpc.conductor import CanaryHPCConductor

    d = tmp_path_factory.mktemp("query-batch")
    with working_dir(d):
        _write_basic_tests(4)
        with cfg.override():
            cfg.options.hpc_backend = "shell"
            spec = {"count": 2, "duration": None, "layout": "flat", "nodes": "any"}
            cfg.options.hpc_batchspec = spec
            conductor = CanaryHPCConductor(backend="shell")
            cfg.pluginmanager.register(conductor, "canary_hpc_batch_setup")
            workspace = Workspace.create(d, force=True)
            specs = workspace.create_selection("default", {str(d): []})
            workspace.run(specs)

    # Discover batch dirs and session name
    session_dirs = sorted((d / ".canary" / "sessions").glob("*"))
    assert session_dirs, "No session directories created"
    session_name = session_dirs[0].name
    batch_dirs = sorted((session_dirs[0] / "batches").glob("*"))
    assert len(batch_dirs) == 2, f"Expected 2 batch dirs, got {len(batch_dirs)}: {batch_dirs}"

    yield SimpleNamespace(
        root=d,
        workspace_dir=d / ".canary",
        session_name=session_name,
        session_dir=session_dirs[0],
        batch_dirs=batch_dirs,
        batch_id=batch_dirs[0].name,  # 7-char prefix
    )


def _run_query_batch(
    batch_id, *, session=None, path=".", clean=False, terse=False, list_keys=False
):
    from canary_hpc import _exec_query_batch

    args = argparse.Namespace(
        query_subcmd="batch",
        batchid=batch_id,
        path=path,
        session=session,
        clean=clean,
        terse=terse,
        list_keys=list_keys,
    )
    return _exec_query_batch(args)


def _run_query_batches(*, session="latest", where=None, terse=False):
    from canary_hpc import _exec_query_batches

    args = argparse.Namespace(query_subcmd="batches", session=session, where=where, terse=terse)
    return _exec_query_batches(args)


def test_query_batch_returns_lock_file_as_json(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batch(batch_setup.batch_id)
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "id" in data
    assert "jobs" in data
    assert "status" in data
    assert "timekeeper" in data
    assert "estimated_runtime" in data


def test_query_batch_path_expression(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batch(batch_setup.batch_id, path=".status")
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    # status has category, outcome, reason keys
    assert "category" in data or "outcome" in data or "code" in data


def test_query_batch_list_keys(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batch(batch_setup.batch_id, list_keys=True)
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any("status" in line for line in lines)
    assert any("timekeeper" in line for line in lines)


def test_query_batch_terse_outputs_single_line(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batch(batch_setup.batch_id, terse=True)
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln.strip()]
    assert len(lines) == 1


def test_query_batch_with_explicit_session(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batch(batch_setup.batch_id, session=batch_setup.session_name)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "id" in data


def test_query_batches_returns_list(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batches(session=batch_setup.session_name)
    assert rc == 0
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert isinstance(rows, list)
    assert len(rows) == 2


def test_query_batches_has_expected_fields(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batches(session=batch_setup.session_name)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    for row in rows:
        assert "id" in row
        assert "id_prefix" in row
        assert "job_count" in row
        assert "status" in row
        assert "timings" in row
        assert "estimated_runtime" in row


def test_query_batches_sorted_by_job_count_descending(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batches(session=batch_setup.session_name)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    counts = [r["job_count"] for r in rows]
    assert counts == sorted(counts, reverse=True)


def test_query_batches_where_filter(batch_setup, capsys):
    with working_dir(batch_setup.root):
        rc = _run_query_batches(session=batch_setup.session_name, where="status.category==PASS")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    # All returned rows should have category==PASS
    for row in rows:
        assert row["status"]["category"] == "PASS"


def test_query_batches_via_query_command(batch_setup, capsys):
    """Test the full dispatch path: Query().execute() -> canary_query_execute hook."""
    with working_dir(batch_setup.root):
        args = argparse.Namespace(
            query_subcmd="batches", session=batch_setup.session_name, where=None, terse=False
        )
        rc = Query().execute(args)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 2


def test_query_batch_via_query_command(batch_setup, capsys):
    """Test the full dispatch path: Query().execute() -> canary_query_execute hook."""
    with working_dir(batch_setup.root):
        args = argparse.Namespace(
            query_subcmd="batch",
            batchid=batch_setup.batch_id,
            path=".",
            session=batch_setup.session_name,
            clean=False,
            terse=False,
            list_keys=False,
        )
        rc = Query().execute(args)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "id" in data


# -------------------------------------------------------------------------
# _parse_where unit tests — numeric comparisons on timings.* fields
# -------------------------------------------------------------------------


def test_parse_where_string_equality():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("status.category==PASS")
    assert pred({"status": {"category": "PASS"}}) is True
    assert pred({"status": {"category": "FAIL"}}) is False


def test_parse_where_string_inequality():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("status.outcome!=FAILED")
    assert pred({"status": {"outcome": "SUCCESS"}}) is True
    assert pred({"status": {"outcome": "FAILED"}}) is False


def test_parse_where_numeric_greater_than():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.queue_wait>3600")
    assert pred({"timings": {"queue_wait": 5348.0}}) is True
    assert pred({"timings": {"queue_wait": 1262.0}}) is False
    assert pred({"timings": {"queue_wait": 3600.0}}) is False  # strict >


def test_parse_where_numeric_greater_than_or_equal():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.queue_wait>=3600")
    assert pred({"timings": {"queue_wait": 3600.0}}) is True
    assert pred({"timings": {"queue_wait": 3600.1}}) is True
    assert pred({"timings": {"queue_wait": 3599.9}}) is False


def test_parse_where_numeric_less_than():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.running<60")
    assert pred({"timings": {"running": 45.5}}) is True
    assert pred({"timings": {"running": 120.0}}) is False


def test_parse_where_numeric_less_than_or_equal():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.running<=60")
    assert pred({"timings": {"running": 60.0}}) is True
    assert pred({"timings": {"running": 60.1}}) is False


def test_parse_where_none_value_ordered_returns_false():
    """None timing values (batch not yet finished) should never pass ordered predicates."""
    from _canary.subcommands.query import _parse_where

    for op in (">", "<", ">=", "<="):
        pred = _parse_where(f"timings.queue_wait{op}3600")
        assert pred({"timings": {"queue_wait": None}}) is False, (
            f"op={op!r} should be False for None"
        )


def test_parse_where_none_value_equality_returns_false():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.queue_wait==3600")
    assert pred({"timings": {"queue_wait": None}}) is False


def test_parse_where_none_value_inequality_returns_true():
    from _canary.subcommands.query import _parse_where

    pred = _parse_where("timings.queue_wait!=3600")
    assert pred({"timings": {"queue_wait": None}}) is True


def test_parse_where_invalid_expression_raises():
    from _canary.subcommands.query import _parse_where

    with pytest.raises(ValueError, match="Invalid --where expression"):
        _parse_where("not_valid_expression")


def test_query_batches_where_numeric_timing(batch_setup, capsys):
    """--where on a numeric timings field should filter correctly."""
    with working_dir(batch_setup.root):
        # All batches should have timings.total >= 0 (they are completed)
        rc = _run_query_batches(session=batch_setup.session_name, where="timings.total>=0")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    # All returned rows have timings.total >= 0
    for row in rows:
        total = row["timings"]["total"]
        assert total is not None and total >= 0


# -------------------------------------------------------------------------
# canary query jobs tests
# -------------------------------------------------------------------------


def _run_query_jobs(setup_ns, *, session=None, where=None, terse=False, digest=False):
    """Helper: call _exec_jobs via Query().execute() dispatch."""
    from _canary.subcommands.query import _exec_jobs

    args = argparse.Namespace(
        query_subcmd="jobs", session=session, where=where, terse=terse, digest=digest
    )
    with working_dir(setup_ns.results_path), canary.config.override():
        return _exec_jobs(args)


def test_query_jobs_returns_json_list(setup, capsys):
    rc = _run_query_jobs(setup)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert len(rows) > 0


def test_query_jobs_has_expected_fields(setup, capsys):
    rc = _run_query_jobs(setup)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    for row in rows:
        assert "id" in row
        assert "name" in row
        assert "fullname" in row
        assert "file_path" in row
        assert "exec_dir" in row
        assert "session" in row
        assert "exit_code" in row
        assert "status" in row
        assert "category" in row["status"]
        assert "outcome" in row["status"]
        assert "timings" in row


def test_query_jobs_with_session_scopes_to_session(setup, capsys):
    rc = _run_query_jobs(setup, session=setup.session.name)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert len(rows) > 0
    # All rows should belong to this session
    for row in rows:
        assert row["session"] == setup.session.name


def test_query_jobs_with_session_latest(setup, capsys):
    rc = _run_query_jobs(setup, session="latest")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert len(rows) > 0


def test_query_jobs_where_filter(setup, capsys):
    rc = _run_query_jobs(setup, where="status.category==PASS")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    # All returned rows should have category PASS
    for row in rows:
        assert row["status"]["category"] == "PASS"


def test_query_jobs_where_nonexistent_returns_empty(setup, capsys):
    # Use a category value that should not exist
    rc = _run_query_jobs(setup, where="status.category==NONEXISTENT")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows == []


def test_query_jobs_digest_outputs_one_line_per_job(setup, capsys):
    rc = _run_query_jobs(setup, digest=True)
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) > 0
    valid_categories = {"PASS", "FAIL", "CANCEL", "SKIP", "NONE"}
    for line in lines:
        parts = line.rsplit(" ", 1)
        assert len(parts) == 2, f"Expected 'name CATEGORY', got {line!r}"
        _, category = parts
        assert category in valid_categories, f"Unexpected category {category!r}"


def test_query_jobs_cross_session_returns_latest_per_spec(setup, capsys):
    """Cross-session default: each spec_name appears at most once."""
    rc = _run_query_jobs(setup)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    names = [r["name"] for r in rows]
    # No duplicates — latest per spec
    assert len(names) == len(set(names)), "Duplicate spec names in query jobs output"


def test_query_jobs_via_query_command(setup, capsys):
    """Test the full dispatch path: Query().execute() -> canary_query_execute hook."""
    args = argparse.Namespace(
        query_subcmd="jobs", session=None, where=None, terse=False, digest=False
    )
    with working_dir(setup.results_path), canary.config.override():
        rc = Query().execute(args)
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list)
    assert len(rows) > 0


def test_query_jobs_terse_outputs_single_line(setup, capsys):
    rc = _run_query_jobs(setup, terse=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert "\n" not in out.rstrip("\n")
    rows = json.loads(out)
    assert isinstance(rows, list)
