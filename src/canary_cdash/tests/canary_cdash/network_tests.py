# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


import canary_cdash.interface as interface_mod


def test_cdash_get_passes_timeout(monkeypatch):
    seen = {}

    class DummyResponse:
        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr(interface_mod, "urlopen", fake_urlopen)

    payload = interface_mod.server.get("https://example.invalid/api")

    assert payload == {"ok": True}
    assert seen["timeout"] == interface_mod.NETWORK_TIMEOUT_SECONDS


def test_cdash_buildid_does_not_use_insecure_k(monkeypatch):
    captured = {}

    class DummyCurl:
        def __call__(self, *args, **kwargs):
            captured["args"] = args

            class DummyResult:
                def get_output(self):
                    return "<buildid>123</buildid>"

            return DummyResult()

    monkeypatch.setattr(interface_mod, "Executable", lambda name: DummyCurl())

    cdash = interface_mod.server(baseurl="https://example.invalid", project="proj")
    buildid = cdash.buildid(sitename="site", buildstamp="stamp", buildname="name")

    assert buildid == 123
    assert "-k" not in captured["args"]
