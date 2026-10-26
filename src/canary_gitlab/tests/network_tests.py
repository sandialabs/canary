# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from urllib.request import Request

import canary_gitlab.gitlab as gitlab_mod


def test_merge_request_target_data_uses_project_data_when_target_matches_project():
    auth = "placeholder"
    mr = gitlab_mod.merge_request("https://api", 1, 2, auth)
    mr._project_data = {"web_url": "https://example/project"}
    mr._mr_data = {"target_project_id": 1}

    assert mr.target_data == mr.project_data
    assert mr.target_url == "https://example/project"


def test_move_issue_uses_urllib_not_curl(monkeypatch):
    auth = "placeholder"
    repo = gitlab_mod.repo(
        url="https://example/repo", api_url="https://api", access_token=auth, project_id=1
    )
    captured: dict[str, object] = {}

    class DummyOpener:
        def open(self, request: Request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout

            class _Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return _Resp()

    monkeypatch.setattr(gitlab_mod, "build_opener", lambda *args: DummyOpener())

    repo.move_issue(7, to_project_id=9)

    req = captured["request"]
    assert isinstance(req, Request)
    assert req.full_url.endswith("/projects/1/issues/7/move")
    assert captured["timeout"] == gitlab_mod.NETWORK_TIMEOUT_SECONDS


def test_upload_sets_timeout_and_closes_file(monkeypatch, tmp_path):
    f = tmp_path / "payload.txt"
    f.write_text("data")
    auth = "placeholder"

    repo = gitlab_mod.repo(
        url="https://example/repo", api_url="https://api", access_token=auth, project_id=1
    )
    seen: dict[str, object] = {}

    class DummyResponse:
        def json(self):
            return {"ok": True}

    class DummyRequests:
        @staticmethod
        def post(url, headers=None, files=None, timeout=None):
            seen["timeout"] = timeout
            assert files is not None
            fh = files["file"]
            seen["closed_during_call"] = fh.closed
            seen["file_obj"] = fh
            return DummyResponse()

    import sys

    monkeypatch.setitem(sys.modules, "requests", DummyRequests)

    result = repo.upload(file=str(f))

    assert result == {"ok": True}
    assert seen["timeout"] == gitlab_mod.NETWORK_TIMEOUT_SECONDS
    assert seen["closed_during_call"] is False
    assert getattr(seen["file_obj"], "closed") is True
