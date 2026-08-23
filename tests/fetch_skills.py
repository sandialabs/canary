# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path

import pytest

from _canary.plugins.subcommands.fetch import Fetch
from _canary.plugins.subcommands.fetch import UnknownSkillError
from _canary.plugins.subcommands.fetch import fetch_all_skills
from _canary.plugins.subcommands.fetch import fetch_skill
from _canary.plugins.subcommands.fetch import get_skill_resource
from _canary.plugins.subcommands.fetch import list_bundled_skills

EXPECTED_SKILLS = {
    "canary-orientation",
    "canary-test-authoring",
    "canary-run-debug",
    "canary-workflows-results",
    "canary-extension-development",
}


def namespace(**kwargs):
    defaults = {"what": "skills", "name": None, "list_skills": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_list_bundled_skills_contains_expected_skills():
    skills = set(list_bundled_skills())
    assert EXPECTED_SKILLS <= skills


def test_each_bundled_skill_has_skill_md():
    for name in EXPECTED_SKILLS:
        resource = get_skill_resource(name)
        assert resource.is_dir()
        assert resource.joinpath("SKILL.md").is_file()
        text = resource.joinpath("SKILL.md").read_text(encoding="utf-8")
        assert "canary query -c" in text


def test_fetch_specific_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    target = fetch_skill("canary-test-authoring")

    assert target == Path("canary-test-authoring")
    assert (tmp_path / "canary-test-authoring" / "SKILL.md").is_file()
    text = (tmp_path / "canary-test-authoring" / "SKILL.md").read_text()
    assert "Authoring Canary tests" in text
    assert "canary query -c tests" in text


def test_fetch_all_skills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    target = fetch_all_skills()

    assert target == Path("skills")
    for name in EXPECTED_SKILLS:
        assert (tmp_path / "skills" / name / "SKILL.md").is_file()


def test_fetch_command_lists_skills(capsys):
    rc = Fetch().execute(namespace(list_skills=True))

    assert rc == 0
    output = capsys.readouterr().out
    for name in EXPECTED_SKILLS:
        assert name in output


def test_fetch_command_fetches_specific_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rc = Fetch().execute(namespace(name="canary-run-debug"))

    assert rc == 0
    assert (tmp_path / "canary-run-debug" / "SKILL.md").is_file()


def test_fetch_command_fetches_all_skills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rc = Fetch().execute(namespace())

    assert rc == 0
    assert (tmp_path / "skills").is_dir()
    for name in EXPECTED_SKILLS:
        assert (tmp_path / "skills" / name / "SKILL.md").is_file()


def test_fetch_unknown_skill_raises_clear_error():
    with pytest.raises(UnknownSkillError) as exc:
        fetch_skill("does-not-exist")

    message = str(exc.value)
    assert "does-not-exist" in message
    assert "Available skills" in message
    assert "canary-orientation" in message


def test_fetch_specific_skill_refuses_existing_destination(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "canary-test-authoring").mkdir()

    with pytest.raises(ValueError) as exc:
        fetch_skill("canary-test-authoring")

    assert "already exists" in str(exc.value)


def test_fetch_all_skills_refuses_existing_destination(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "skills").mkdir()

    with pytest.raises(ValueError) as exc:
        fetch_all_skills()

    assert "already exists" in str(exc.value)


def test_existing_fetch_examples_rejects_skill_name():
    with pytest.raises(ValueError):
        Fetch().execute(namespace(what="examples", name="canary-orientation"))


def test_existing_fetch_canary_cmake_rejects_skill_name():
    with pytest.raises(ValueError):
        Fetch().execute(namespace(what="canary.cmake", name="canary-orientation"))
