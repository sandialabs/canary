# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json

import pytest
import yaml

from _canary.subcommands.query import Query
from _canary.subcommands.query import query_skills
from _canary.subcommands.query import skill_to_markdown
from _canary.subcommands.query import write_skill_markdown

EXPECTED_SKILLS = {
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
        "skill": "all",
        "query": ".",
        "terse": False,
        "markdown": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_query_all_skills_contains_expected_skills():
    skills = query_skills("all")

    assert isinstance(skills, dict)
    assert EXPECTED_SKILLS <= set(skills)


def test_each_bundled_skill_has_expected_shape():
    for name in EXPECTED_SKILLS:
        skill = query_skills(name)

        assert isinstance(skill, dict)
        assert skill["name"] == name
        assert isinstance(skill["description"], str)
        assert skill["description"]
        assert isinstance(skill["body"], str)
        assert "canary query -c" in skill["body"]


def test_query_specific_skill():
    skill = query_skills("canary-test-authoring")

    assert skill["name"] == "canary-test-authoring"
    assert "Authoring Canary tests" in skill["body"]
    assert "canary query -c tests" in skill["body"]


def test_query_specific_skill_field_with_dot_query():
    description = query_skills("canary-run-debug", ".description")

    assert description == (
        "Use this skill when running Canary tests or workflows, inspecting failures, "
        "querying job/session state, reproducing a job, or debugging resource and "
        "dependency problems."
    )


def test_query_specific_skill_field_without_dot_query():
    body = query_skills("canary-run-debug", "body")

    assert "# Running and debugging Canary jobs" in body
    assert "canary query -c execution.local" in body


def test_query_all_skills_field_query():
    description = query_skills("all", "canary-orientation.description")

    assert description == (
        "Use this skill when you need to understand what Canary is, when to use it, "
        "and how to discover detailed Canary capabilities without loading the full "
        "documentation."
    )


def test_query_unknown_skill_raises_clear_error():
    with pytest.raises(KeyError) as exc:
        query_skills("does-not-exist")

    message = str(exc.value)
    assert "does-not-exist" in message
    assert "Available keys" in message
    assert "canary-orientation" in message


def test_query_command_prints_all_skills(capsys):
    rc = Query().execute(namespace(skill="all"))

    assert rc == 0

    output = capsys.readouterr().out
    data = json.loads(output)

    assert EXPECTED_SKILLS <= set(data)


def test_query_command_prints_specific_skill(capsys):
    rc = Query().execute(namespace(skill="canary-run-debug"))

    assert rc == 0

    output = capsys.readouterr().out
    data = json.loads(output)

    assert data["name"] == "canary-run-debug"
    assert "# Running and debugging Canary jobs" in data["body"]


def test_query_command_prints_specific_skill_field(capsys):
    rc = Query().execute(namespace(skill="canary-test-authoring", query="body"))

    assert rc == 0

    output = capsys.readouterr().out
    data = json.loads(output)

    assert "# Authoring Canary tests" in data
    assert "canary query -c tests" in data


def test_query_command_terse_prints_compact_json(capsys):
    rc = Query().execute(namespace(skill="canary-run-debug", query="name", terse=True))

    assert rc == 0

    output = capsys.readouterr().out
    assert output == '"canary-run-debug"\n'


def test_skill_to_markdown_emits_frontmatter_and_body():
    skill = query_skills("canary-workflows-results")
    markdown = skill_to_markdown(skill)

    assert markdown.startswith("---\n")
    assert "\n---\n\n# Canary workflows and result analysis" in markdown
    assert "canary query -c workflows" in markdown
    assert markdown.endswith("\n")

    frontmatter_text = markdown.split("---", 2)[1]
    frontmatter = yaml.safe_load(frontmatter_text)

    assert frontmatter["name"] == "canary-workflows-results"
    assert frontmatter["description"] == skill["description"]


def test_write_specific_skill_markdown_to_file(tmp_path):
    skill = query_skills("canary-test-authoring")
    output = tmp_path / "SKILL.md"

    write_skill_markdown("canary-test-authoring", skill, output)

    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: canary-test-authoring" in text
    assert "# Authoring Canary tests" in text
    assert "canary query -c tests" in text


def test_write_specific_skill_markdown_to_existing_directory(tmp_path):
    skill = query_skills("canary-test-authoring")

    write_skill_markdown("canary-test-authoring", skill, tmp_path)

    output = tmp_path / "canary-test-authoring.md"
    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert "# Authoring Canary tests" in text


def test_write_all_skills_markdown_to_directory(tmp_path):
    skills = query_skills("all")
    output = tmp_path / "skills"

    write_skill_markdown("all", skills, output)

    assert output.is_dir()

    for name in EXPECTED_SKILLS:
        path = output / f"{name}.md"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "canary query -c" in text


def test_query_command_writes_specific_skill_markdown(tmp_path):
    output = tmp_path / "canary-run-debug.md"

    rc = Query().execute(namespace(skill="canary-run-debug", markdown=str(output)))

    assert rc == 0
    assert output.is_file()

    text = output.read_text(encoding="utf-8")
    assert "# Running and debugging Canary jobs" in text
    assert "canary query -c execution.local" in text


def test_query_command_writes_all_skills_markdown(tmp_path):
    output = tmp_path / "skills"

    rc = Query().execute(namespace(skill="all", markdown=str(output)))

    assert rc == 0
    assert output.is_dir()

    for name in EXPECTED_SKILLS:
        assert (output / f"{name}.md").is_file()


def test_write_specific_skill_markdown_rejects_field_query(tmp_path):
    body = query_skills("canary-test-authoring", "body")

    with pytest.raises(TypeError) as exc:
        write_skill_markdown("canary-test-authoring", body, tmp_path / "SKILL.md")

    assert "--markdown requires the selected skill object" in str(exc.value)


def test_query_command_rejects_markdown_with_capability():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(capability="overview", skill=None, markdown="overview.md"))

    assert "--markdown is only valid with --skill" in str(exc.value)


def test_query_command_rejects_markdown_with_job_query():
    with pytest.raises(ValueError) as exc:
        Query().execute(namespace(jobid="abc123", skill=None, markdown="job.md"))

    assert "--markdown is only valid with --skill" in str(exc.value)
