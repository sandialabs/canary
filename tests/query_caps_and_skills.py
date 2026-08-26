# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from types import SimpleNamespace

import pytest
import yaml

from _canary.subcommands import query as query_mod
from _canary.subcommands.query import CAPABILITY_HELP_QUERY
from _canary.subcommands.query import SKILL_HELP_QUERY
from _canary.subcommands.query import Query
from _canary.subcommands.query import build_capabilities_tree
from _canary.subcommands.query import build_skills_tree
from _canary.subcommands.query import list_capability_paths
from _canary.subcommands.query import list_skill_paths
from _canary.subcommands.query import query_json
from _canary.subcommands.query import skill_to_markdown
from _canary.subcommands.query import write_skill_markdown

EXPECTED_CORE_SKILLS = {
    "canary-orientation",
    "canary-test-authoring",
    "canary-run-debug",
    "canary-workflows-results",
    "canary-extension-development",
}


def namespace(**kwargs):
    defaults = {
        "jobid": None,
        "session": None,
        "capability": None,
        "skill": None,
        "query": ".",
        "terse": False,
        "markdown": None,
        "list_keys": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


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


def fake_capabilities_payload(extension: str = "fake"):
    return {
        "schema_version": "2.0.0",
        "extension": extension,
        "capabilities": {
            "overview": {
                "summary": f"{extension} extension overview",
                "details": {"kind": extension, "enabled": True},
            },
            "commands": {"run": {"purpose": f"run {extension} jobs"}},
        },
    }


def fake_skills_payload(extension: str = "fake"):
    return {
        "schema_version": "2.0.0",
        "extension": extension,
        "skills": {
            f"canary-{extension}-authoring": {
                "name": f"canary-{extension}-authoring",
                "description": f"Author {extension} jobs.",
                "body": f"# Authoring {extension} jobs\n\nUse this skill for {extension} jobs.\n",
            },
            f"canary-{extension}-debug": {
                "name": f"canary-{extension}-debug",
                "description": f"Debug {extension} jobs.",
                "body": f"# Debugging {extension} jobs\n\nUse this skill to debug {extension} jobs.\n",
            },
        },
    }


def install_fake_query_plugin(monkeypatch, *, capabilities=None, skills=None):
    fake_config = SimpleNamespace(
        pluginmanager=FakePluginManager(capabilities=capabilities, skills=skills)
    )
    monkeypatch.setattr(query_mod, "config", fake_config)


# -------------------------------------------------------------------------
# Core capabilities
# -------------------------------------------------------------------------


def test_build_capabilities_tree_contains_core_keys():
    data = build_capabilities_tree()

    assert isinstance(data, dict)
    assert "overview" in data
    assert "hooks" in data
    assert "query" in data
    assert "ext" in data
    assert isinstance(data["ext"], dict)


def test_query_capability_root_command(capsys):
    rc = Query().execute(namespace(capability="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "overview" in out
    assert "hooks" in out
    assert "query" in out
    assert "ext" in out


def test_query_capability_overview_command(capsys):
    rc = Query().execute(namespace(capability="overview"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "what_is_canary" in out
    assert "major_concepts" in out


def test_query_capability_nested_command(capsys):
    rc = Query().execute(namespace(capability="hooks.post"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "canary_runtest_finish" in out


def test_query_capability_rejects_extra_positional_query():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(capability="hooks", query=".post"))

    assert "Capability queries must be supplied directly" in str(exc.value)


def test_query_capability_missing_key_reports_available_keys():
    data = build_capabilities_tree()

    with pytest.raises(KeyError) as exc:
        query_json(data, "does_not_exist")

    message = str(exc.value)
    assert "does_not_exist" in message
    assert "Available keys" in message
    assert "overview" in message


def test_query_capability_list_root(capsys):
    rc = Query().execute(namespace(capability=".", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "overview" in out
    assert "hooks" in out
    assert "query" in out
    assert "ext" in out


def test_query_capability_list_ext_is_valid_even_without_extensions(capsys):
    rc = Query().execute(namespace(capability="ext", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert isinstance(out, list)


def test_query_capability_no_query_prints_help(capsys):
    rc = Query().execute(namespace(capability=CAPABILITY_HELP_QUERY))

    assert rc == 0
    out = capsys.readouterr().out

    assert "Canary capability queries" in out
    assert "canary query -c QUERY" in out
    assert "Top-level capability keys" in out
    assert "overview" in out


def test_query_capability_no_query_with_list_lists_root(capsys):
    rc = Query().execute(namespace(capability=CAPABILITY_HELP_QUERY, list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "overview" in out
    assert "hooks" in out


# -------------------------------------------------------------------------
# Extension capability aggregation
# -------------------------------------------------------------------------


def test_plugin_capabilities_are_aggregated_under_ext(monkeypatch):
    install_fake_query_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    data = build_capabilities_tree()

    assert "ext" in data
    assert "fake" in data["ext"]
    assert data["ext"]["fake"]["overview"]["summary"] == "fake extension overview"


def test_query_plugin_capability_command(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = Query().execute(namespace(capability="ext.fake.overview"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["summary"] == "fake extension overview"
    assert out["details"]["kind"] == "fake"


def test_query_plugin_capability_nested_field(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = Query().execute(namespace(capability="ext.fake.overview.details.kind"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out == "fake"


def test_query_plugin_capability_list_ext(monkeypatch, capsys):
    install_fake_query_plugin(
        monkeypatch,
        capabilities=[fake_capabilities_payload("alpha"), fake_capabilities_payload("beta")],
    )

    rc = Query().execute(namespace(capability="ext", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "ext.alpha" in out
    assert "ext.beta" in out


def test_query_plugin_capability_list_extension(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    rc = Query().execute(namespace(capability="ext.fake", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "ext.fake.overview" in out
    assert "ext.fake.commands" in out


def test_duplicate_plugin_capability_namespace_raises(monkeypatch):
    install_fake_query_plugin(
        monkeypatch,
        capabilities=[fake_capabilities_payload("fake"), fake_capabilities_payload("fake")],
    )

    with pytest.raises(ValueError) as exc:
        build_capabilities_tree()

    assert "Duplicate Canary capabilities extension namespace: fake" in str(exc.value)


# -------------------------------------------------------------------------
# Core skills
# -------------------------------------------------------------------------


def test_build_skills_tree_contains_core_skills():
    data = build_skills_tree()

    assert isinstance(data, dict)
    assert EXPECTED_CORE_SKILLS <= set(data)
    assert "ext" in data
    assert isinstance(data["ext"], dict)


def test_each_core_skill_has_expected_shape():
    data = build_skills_tree()

    for name in EXPECTED_CORE_SKILLS:
        skill = query_json(data, name)

        assert isinstance(skill, dict)
        assert skill["name"] == name
        assert isinstance(skill["description"], str)
        assert skill["description"]
        assert isinstance(skill["body"], str)
        assert "canary query -c" in skill["body"]


def test_query_specific_skill_command(capsys):
    rc = Query().execute(namespace(skill="canary-run-debug"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["name"] == "canary-run-debug"
    assert "# Running and debugging Canary jobs" in out["body"]


def test_query_specific_skill_field_with_full_skill_query(capsys):
    rc = Query().execute(namespace(skill="canary-run-debug.description"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert "running Canary jobs" in out
    assert "debug" in out.lower()


def test_query_skill_rejects_extra_positional_query():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(skill="canary-run-debug", query="body"))

    assert "Skill queries must be supplied directly" in str(exc.value)


def test_query_unknown_skill_raises_clear_error():
    data = build_skills_tree()

    with pytest.raises(KeyError) as exc:
        query_json(data, "does-not-exist")

    message = str(exc.value)
    assert "does-not-exist" in message
    assert "Available keys" in message
    assert "canary-orientation" in message


def test_query_skill_root_command(capsys):
    rc = Query().execute(namespace(skill="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert EXPECTED_CORE_SKILLS <= set(out)


def test_query_skill_list_root(capsys):
    rc = Query().execute(namespace(skill=".", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert EXPECTED_CORE_SKILLS <= set(out)


def test_query_skill_no_query_prints_help(capsys):
    rc = Query().execute(namespace(skill=SKILL_HELP_QUERY))

    assert rc == 0
    out = capsys.readouterr().out

    assert "Canary skill queries" in out
    assert "canary query -k QUERY" in out
    assert "Available skills" in out
    assert "canary-orientation" in out


def test_query_skill_no_query_with_list_lists_root(capsys):
    rc = Query().execute(namespace(skill=SKILL_HELP_QUERY, list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert EXPECTED_CORE_SKILLS <= set(out)


def test_query_skill_terse_prints_compact_json(capsys):
    rc = Query().execute(namespace(skill="canary-run-debug.name", terse=True))

    assert rc == 0

    output = capsys.readouterr().out
    assert output == '"canary-run-debug"\n'


# -------------------------------------------------------------------------
# Extension skill aggregation
# -------------------------------------------------------------------------


def test_plugin_skills_are_aggregated_under_ext(monkeypatch):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()

    assert "ext" in data
    assert "fake" in data["ext"]
    assert "canary-fake-authoring" in data["ext"]["fake"]


def test_query_plugin_skill_command(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = Query().execute(namespace(skill="ext.fake.canary-fake-authoring"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out["name"] == "canary-fake-authoring"
    assert "# Authoring fake jobs" in out["body"]


def test_query_plugin_skill_field(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = Query().execute(namespace(skill="ext.fake.canary-fake-debug.description"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)

    assert out == "Debug fake jobs."


def test_query_plugin_skill_list_extension(monkeypatch, capsys):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    rc = Query().execute(namespace(skill="ext.fake", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "ext.fake.canary-fake-authoring" in out
    assert "ext.fake.canary-fake-debug" in out


def test_duplicate_plugin_skill_namespace_raises(monkeypatch):
    install_fake_query_plugin(
        monkeypatch, skills=[fake_skills_payload("fake"), fake_skills_payload("fake")]
    )

    with pytest.raises(ValueError) as exc:
        build_skills_tree()

    assert "Duplicate Canary skills extension namespace: fake" in str(exc.value)


# -------------------------------------------------------------------------
# Markdown export
# -------------------------------------------------------------------------


def test_skill_to_markdown_emits_frontmatter_and_body():
    data = build_skills_tree()
    skill = query_json(data, "canary-workflows-results")

    markdown = skill_to_markdown(skill)

    assert markdown.startswith("---\n")
    assert "\n---\n\n# Canary workflows and result analysis" in markdown
    assert "canary query -c" in markdown
    assert markdown.endswith("\n")

    frontmatter_text = markdown.split("---", 2)[1]
    frontmatter = yaml.safe_load(frontmatter_text)

    assert frontmatter["name"] == "canary-workflows-results"
    assert frontmatter["description"] == skill["description"]


def test_write_specific_skill_markdown_to_file(tmp_path):
    data = build_skills_tree()
    skill = query_json(data, "canary-test-authoring")
    output = tmp_path / "SKILL.md"

    write_skill_markdown("canary-test-authoring", skill, output)

    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: canary-test-authoring" in text
    assert "# Authoring Canary tests" in text
    assert "canary query -c" in text


def test_write_specific_skill_markdown_to_existing_directory(tmp_path):
    data = build_skills_tree()
    skill = query_json(data, "canary-test-authoring")

    write_skill_markdown("canary-test-authoring", skill, tmp_path)

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
        path = output / f"{name}.md"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "canary query -c" in text


def test_write_extension_skill_subtree_markdown_to_directory(tmp_path, monkeypatch):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()
    subtree = query_json(data, "ext.fake")
    output = tmp_path / "skills"

    write_skill_markdown("ext.fake", subtree, output)

    assert (output / "ext" / "fake" / "canary-fake-authoring.md").is_file()
    assert (output / "ext" / "fake" / "canary-fake-debug.md").is_file()


def test_query_command_writes_specific_skill_markdown(tmp_path):
    output = tmp_path / "canary-run-debug.md"

    rc = Query().execute(namespace(skill="canary-run-debug", markdown=str(output)))

    assert rc == 0
    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert "# Running and debugging Canary jobs" in text
    assert "canary query -c" in text


def test_query_command_writes_all_skills_markdown(tmp_path):
    output = tmp_path / "skills"

    rc = Query().execute(namespace(skill=".", markdown=str(output)))

    assert rc == 0
    assert output.is_dir()

    for name in EXPECTED_CORE_SKILLS:
        assert (output / f"{name}.md").is_file()


def test_write_skill_markdown_rejects_scalar_field_query(tmp_path):
    data = build_skills_tree()
    body = query_json(data, "canary-test-authoring.body")

    with pytest.raises(ValueError) as exc:
        write_skill_markdown("canary-test-authoring.body", body, tmp_path / "SKILL.md")

    assert "does not contain any skill objects" in str(exc.value)


def test_query_command_rejects_markdown_with_capability():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(capability="overview", markdown="overview.md"))

    assert "--markdown is only valid with --skill" in str(exc.value)


def test_query_command_rejects_markdown_with_job_query():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(jobid="abc123", markdown="job.md"))

    assert "--markdown is only valid with --skill" in str(exc.value)


# -------------------------------------------------------------------------
# Generic query path behavior
# -------------------------------------------------------------------------


def test_query_json_existing_dot_semantics_are_preserved():
    data = {"measurements": {"data": {"max_stress": 12.5}}, "items": [{"name": "a"}]}

    assert query_json(data, ".") == data
    assert query_json(data, "measurements") == {"data": {"max_stress": 12.5}}
    assert query_json(data, ".measurements.data.max_stress") == 12.5
    assert query_json(data, ".items[0].name") == "a"


def test_query_json_supports_quoted_keys():
    data = {"a.b": {"key with spaces": [{"x": 1}]}}

    assert query_json(data, '["a.b"]["key with spaces"][0].x') == 1


def test_list_capability_paths_lists_only_child_objects(monkeypatch):
    install_fake_query_plugin(monkeypatch, capabilities=[fake_capabilities_payload("fake")])

    data = build_capabilities_tree()
    paths = list_capability_paths(data, "ext.fake.overview")

    assert "ext.fake.overview.details" in paths
    assert "ext.fake.overview.summary" not in paths


def test_list_skill_paths_lists_terminal_skills(monkeypatch):
    install_fake_query_plugin(monkeypatch, skills=[fake_skills_payload("fake")])

    data = build_skills_tree()
    paths = list_skill_paths(data, "ext.fake")

    assert paths == ["ext.fake.canary-fake-authoring", "ext.fake.canary-fake-debug"]


# -------------------------------------------------------------------------
# Job/session lock query behavior
# -------------------------------------------------------------------------


def test_query_job_behavior_is_preserved(tmp_path, monkeypatch, capsys):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    lockfile = job_dir / "testcase.lock"
    lockfile.write_text(
        json.dumps(
            {
                "id": "abc123",
                "measurements": {"data": {"answer": 42}},
                "status": {"outcome": "SUCCESS"},
            }
        )
    )

    class FakeWorkspace:
        @staticmethod
        def load():
            return FakeWorkspace()

        def find_job(self, jobid):
            assert jobid == "abc123"
            return SimpleNamespace(lockfile=lockfile)

    monkeypatch.setattr(query_mod, "Workspace", FakeWorkspace)

    rc = Query().execute(namespace(jobid="abc123", query="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "abc123"

    rc = Query().execute(namespace(jobid="abc123", query=".measurements"))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"data": {"answer": 42}}


def test_query_job_list_keys(tmp_path, monkeypatch, capsys):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    lockfile = job_dir / "testcase.lock"
    lockfile.write_text(
        json.dumps(
            {
                "id": "abc123",
                "measurements": {"data": {"answer": 42}},
                "status": {"outcome": "SUCCESS"},
            }
        )
    )

    class FakeWorkspace:
        @staticmethod
        def load():
            return FakeWorkspace()

        def find_job(self, jobid):
            assert jobid == "abc123"
            return SimpleNamespace(lockfile=lockfile)

    monkeypatch.setattr(query_mod, "Workspace", FakeWorkspace)

    rc = Query().execute(namespace(jobid="abc123", query=".", list_keys=True))

    assert rc == 0
    out = capsys.readouterr().out.splitlines()

    assert "measurements" in out
    assert "status" in out
    assert "id" not in out


def test_query_session_behavior_is_preserved(tmp_path, monkeypatch, capsys):
    refs_dir = tmp_path / "refs"
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "session-001"
    refs_dir.mkdir()
    session_dir.mkdir(parents=True)

    (session_dir / "session.lock").write_text(
        json.dumps(
            {
                "name": "session-001",
                "job_ids": ["abc123"],
                "measurements": {"campaign": "agentic-demo"},
            }
        )
    )

    (refs_dir / "latest").write_text("../sessions/session-001")

    class FakeWorkspace:
        def __init__(self):
            self.refs_dir = refs_dir
            self.sessions_dir = sessions_dir

        @staticmethod
        def load():
            return FakeWorkspace()

    monkeypatch.setattr(query_mod, "Workspace", FakeWorkspace)

    rc = Query().execute(namespace(session="session-001", query="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["name"] == "session-001"

    rc = Query().execute(namespace(session="latest", query=".measurements.campaign"))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == "agentic-demo"
