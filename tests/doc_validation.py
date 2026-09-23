# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Validate that skills.json and capabilities.json agree with hookspec.py.

These tests guard against documentation drift — specifically the class of bug
where a hook's firstresult setting or signature is described incorrectly in the
machine-readable knowledge databases that agents and users query via
``canary learn``.
"""

import importlib.resources
import json
import re

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_skills() -> dict:
    data = importlib.resources.files("canary").joinpath("data/skills.json").read_text()
    return json.loads(data)


def _load_capabilities() -> dict:
    data = importlib.resources.files("canary").joinpath("data/capabilities.json").read_text()
    return json.loads(data)


def _hookspec_firstresult() -> dict[str, bool]:
    """Return {hook_name: firstresult} for every @hookspec in hookspec.py."""
    import pluggy

    from _canary import hookspec as hs_module

    pm = pluggy.PluginManager("canary")
    pm.add_hookspecs(hs_module)
    result = {}
    for name, hook in vars(pm.hook).items():
        if name.startswith("canary_"):
            spec = hook.spec
            if spec is not None:
                result[name] = bool(spec.opts.get("firstresult", False))
    return result


# ---------------------------------------------------------------------------
# skills.json correctness
# ---------------------------------------------------------------------------


class TestSkillsJson:
    def setup_method(self):
        self.skills = _load_skills()
        self.hookspecs = _hookspec_firstresult()

    def _extension_dev_body(self) -> str:
        return self.skills["skills"]["canary-extension-development"]["body"]

    def test_extension_dev_skill_runtest_finish_not_firstresult_true(self):
        """The canary-extension-development skill must not claim
        canary_runtest_finish is firstresult=True."""
        body = self._extension_dev_body()
        # The sentence "canary_runtest_finish` is `firstresult=True`" must be gone
        assert (
            "`firstresult=True`" not in body
            or "canary_runtest_finish" not in body.split("`firstresult=True`")[0][-200:]
        ), (
            "skills.json canary-extension-development incorrectly describes "
            "canary_runtest_finish as firstresult=True"
        )

    def test_extension_dev_skill_runtest_finish_reference_firstresult_false(self):
        """The ## canary_runtest_finish reference block must say firstresult: False."""
        body = self._extension_dev_body()
        # The section heading uses backtick-quoted name
        for heading in (
            "## `canary_runtest_finish` reference",
            "## canary_runtest_finish reference",
        ):
            ref_idx = body.find(heading)
            if ref_idx != -1:
                break
        assert ref_idx != -1, "canary_runtest_finish reference section not found in skill body"
        section = body[ref_idx : ref_idx + 400]
        assert "False" in section, (
            "canary_runtest_finish reference block does not mention False firstresult"
        )
        assert "True" not in section.split("False")[0], (
            "canary_runtest_finish reference block lists firstresult as True before False"
        )

    def test_extension_dev_skill_runtest_finish_return_none(self):
        """Signature in skill must be -> None, not -> bool."""
        body = self._extension_dev_body()
        for heading in (
            "## `canary_runtest_finish` reference",
            "## canary_runtest_finish reference",
        ):
            ref_idx = body.find(heading)
            if ref_idx != -1:
                break
        if ref_idx == -1:
            pytest.skip("reference section not found")
        section = body[ref_idx : ref_idx + 400]
        assert "-> None" in section, (
            "canary_runtest_finish reference block shows wrong return type (should be -> None)"
        )

    def test_no_phantom_hook_canary_runtest_setup(self):
        """skills.json must not reference the non-existent canary_runtest_setup hook."""
        raw = json.dumps(self.skills)
        assert "canary_runtest_setup" not in raw, (
            "skills.json references phantom hook 'canary_runtest_setup'; "
            "the real hook is 'canary_runteststart'"
        )

    def test_no_phantom_hook_canary_execute_modifyitems(self):
        """skills.json must not reference the non-existent canary_execute_modifyitems hook."""
        raw = json.dumps(self.skills)
        assert "canary_execute_modifyitems" not in raw, (
            "skills.json references phantom hook 'canary_execute_modifyitems'"
        )


# ---------------------------------------------------------------------------
# capabilities.json correctness
# ---------------------------------------------------------------------------


class TestCapabilitiesJson:
    def setup_method(self):
        self.caps = _load_capabilities()
        self.hookspecs = _hookspec_firstresult()

    def _find_firstresult_claims(self) -> list[tuple[str, bool]]:
        """Walk capabilities JSON and extract every (hook_name, firstresult) claim."""
        raw = json.dumps(self.caps)
        # Look for patterns like "firstresult": true/false near hook names
        claims = []
        for hook_name in self.hookspecs:
            pattern = rf'"{hook_name}".*?"firstresult"\s*:\s*(true|false)'
            for m in re.finditer(pattern, raw, re.DOTALL):
                claimed = m.group(1) == "true"
                claims.append((hook_name, claimed))
        return claims

    def test_runtest_finish_firstresult_false_in_capabilities(self):
        """capabilities.json must describe canary_runtest_finish as firstresult=False."""
        raw = json.dumps(self.caps)
        # Find every "firstresult" value near canary_runtest_finish
        chunks = re.split(r'"canary_runtest_finish"', raw)
        for chunk in chunks[1:]:  # skip before first occurrence
            m = re.search(r'"firstresult"\s*:\s*(true|false)', chunk[:500])
            if m:
                assert m.group(1) == "false", (
                    "capabilities.json claims canary_runtest_finish firstresult=true"
                )

    def test_no_phantom_hook_canary_runtest_setup(self):
        """capabilities.json must not reference the non-existent canary_runtest_setup hook."""
        raw = json.dumps(self.caps)
        assert "canary_runtest_setup" not in raw, (
            "capabilities.json references phantom hook 'canary_runtest_setup'"
        )


# ---------------------------------------------------------------------------
# Cross-check: named hooks in docs exist in hookspec
# ---------------------------------------------------------------------------

KNOWN_PHANTOM_FREE_HOOKS = [
    # Hooks explicitly mentioned in skills/capabilities that must exist in hookspec
    "canary_runtest_finish",
    "canary_runteststart",
    "canary_runtest",
    "canary_sessionstart",
    "canary_sessionfinish",
    "canary_addconfig",
    "canary_configure",
    "canary_addoption",
    "canary_addcommand",
    "canary_testcase_generator",
    "canary_generate_modifyitems",
    "canary_select_modifyitems",
    "canary_runtests",
    "canary_reporter",
]


@pytest.mark.parametrize("hook_name", KNOWN_PHANTOM_FREE_HOOKS)
def test_documented_hook_exists_in_hookspec(hook_name):
    """Every hook referenced in docs/skills/capabilities must exist in hookspec.py."""
    import pluggy

    from _canary import hookspec as hs_module

    pm = pluggy.PluginManager("canary")
    pm.add_hookspecs(hs_module)
    hook_names = {name for name in vars(pm.hook) if name.startswith("canary_")}
    assert hook_name in hook_names, (
        f"Hook '{hook_name}' is referenced in docs/skills/capabilities "
        f"but has no @hookspec in hookspec.py"
    )
