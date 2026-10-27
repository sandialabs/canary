# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The ``app.classify_pathspec`` application operation.

Classifying ``canary run`` pathspec items -- deciding whether each is a scan
path, a view path, a selection tag, or a spec id -- requires the current
workspace and used to happen inside the ``PathSpec`` argparse action.  It now
lives behind the app facade.  These tests pin the classification and, in
particular, the error reporting the CLI turns into a usage error.
"""

import canary
from _canary import app
from _canary.app.pathspec import RequestBuilder

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


def test_directory_and_file_items_become_scanpaths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suite").mkdir()
    (tmp_path / "suite" / "a.pyt").write_text(PYT_BODY)
    (tmp_path / "b.pyt").write_text(PYT_BODY)

    with canary.config.override():
        builder = app.classify_pathspec([str(tmp_path / "suite"), str(tmp_path / "b.pyt")])

    assert builder.kind == "scanpaths"
    assert not builder.errors
    assert builder.scanpaths[str(tmp_path / "suite")] == []
    assert builder.scanpaths[str(tmp_path)] == ["b.pyt"]


def test_unresolvable_item_without_workspace_is_reported(tmp_path, monkeypatch):
    """With no workspace, an item that is neither a path nor a known id errors.

    Spec ids can only be resolved against a workspace, so a bare token in a
    workspace-less directory is a usage error rather than a silent scanpath.
    """
    monkeypatch.chdir(tmp_path)

    with canary.config.override():
        builder = app.classify_pathspec(["deadbeef"])

    assert builder.kind is None
    assert builder.errors == ["Spec IDs require an active workspace"]


def test_unknown_spec_id_in_workspace_is_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)

    with canary.config.override():
        app.run(_scanpaths_request(tmp_path))
        builder = app.classify_pathspec(["deadbeef"])

    assert any("not a valid test identifier" in e for e in builder.errors)


def test_existing_tag_classifies_as_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)

    with canary.config.override():
        app.run(_scanpaths_request(tmp_path))
        app.select("mytag")
        builder = app.classify_pathspec(["mytag"])

    assert builder.kind == "tag"
    assert builder.tag == "mytag"
    assert not builder.errors


def test_mixing_scanpaths_and_tag_reports_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)

    with canary.config.override():
        app.run(_scanpaths_request(tmp_path))
        app.select("mytag")
        builder = app.classify_pathspec(["mytag", str(tmp_path)])

    assert any("Cannot mix" in e for e in builder.errors)


def test_classification_extends_a_provided_builder(tmp_path, monkeypatch):
    """A caller may accumulate items from more than one source into one builder."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suite").mkdir()

    builder = RequestBuilder()
    with canary.config.override():
        returned = app.classify_pathspec([str(tmp_path / "suite")], builder=builder)

    assert returned is builder
    assert builder.kind == "scanpaths"


def test_globbed_directory_item_uses_literal_prefix_as_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "some" / "baz" / "foo").mkdir(parents=True)
    (tmp_path / "some" / "spam" / "foo").mkdir(parents=True)

    with canary.config.override():
        builder = app.classify_pathspec([str(tmp_path / "some" / "**" / "foo")])

    assert builder.kind == "scanpaths"
    assert not builder.errors
    assert builder.scanpaths[str(tmp_path / "some")] == ["baz/foo", "spam/foo"]


def test_globbed_file_item_uses_shared_literal_prefix_as_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "some" / "baz" / "foo").mkdir(parents=True)
    (tmp_path / "some" / "spam" / "foo").mkdir(parents=True)
    (tmp_path / "some" / "baz" / "foo" / "test.pyt").write_text(PYT_BODY)
    (tmp_path / "some" / "spam" / "foo" / "test.pyt").write_text(PYT_BODY)

    with canary.config.override():
        builder = app.classify_pathspec([str(tmp_path / "some" / "**" / "foo" / "*.pyt")])

    assert builder.kind == "scanpaths"
    assert not builder.errors
    assert builder.scanpaths[str(tmp_path / "some")] == ["baz/foo/test.pyt", "spam/foo/test.pyt"]


def test_globbed_item_without_matches_reports_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with canary.config.override():
        builder = app.classify_pathspec([str(tmp_path / "some" / "**" / "foo")])

    assert builder.errors == [f"{tmp_path / 'some' / '**' / 'foo'}: no paths matched pattern"]


def test_explicit_root_with_glob_keeps_root_authoritative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "some" / "dir" / "foo" / "a" / "spam").mkdir(parents=True)
    (tmp_path / "some" / "dir" / "foo" / "b" / "spam").mkdir(parents=True)

    with canary.config.override():
        builder = app.classify_pathspec([f"{tmp_path / 'some' / 'dir'}:foo/**/spam"])

    assert builder.kind == "scanpaths"
    assert not builder.errors
    assert builder.scanpaths[str(tmp_path / "some" / "dir")] == ["foo/a/spam", "foo/b/spam"]


def test_colon_after_first_globbed_component_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "some" / "dir" / "a" / "spam").mkdir(parents=True)

    with canary.config.override():
        builder = app.classify_pathspec([f"{tmp_path / 'some' / 'dir'}/**/spam:baz"])

    assert builder.errors == [
        f"{tmp_path / 'some' / 'dir'}/**/spam:baz: ':' is only allowed before the first globbed component"
    ]


class _Request:
    kind = "scanpaths"

    def __init__(self, value):
        self.value = value


def _scanpaths_request(tmp_path):
    return _Request({str(tmp_path): []})
