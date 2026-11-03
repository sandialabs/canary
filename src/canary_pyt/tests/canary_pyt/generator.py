# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys
from pathlib import Path

import pytest

from _canary.core.error import diff_exit_status
from _canary.core.jobspec import BaselineCopyAction
from _canary.core.jobspec_ir import DependencySelector
from canary_pyt.paramset import ParameterSet
from canary_pyt.pyt import PYTAdapter
from canary_pyt.pyt import PYTLoader
from canary_pyt.pyt import PYTLockEmitter
from canary_pyt.pyt import PYTModel
from canary_pyt.pyt import parse_dependencies
from canary_pyt.pyt import parse_dependency


def make_test_file(tmp_path: Path, rel: str, text: str = "# test\n") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def make_model(tmp_path: Path, rel: str) -> PYTModel:
    make_test_file(tmp_path, rel)
    return PYTModel(str(tmp_path), rel)


def lock_model(model: PYTModel, *, on_options: list[str] | None = None):
    return PYTLockEmitter().lock(model, on_options=on_options or [])


def test_lock_no_directives_produces_one_case(tmp_path: Path) -> None:
    m = make_model(tmp_path, "foo.pyt")
    specs = lock_model(m, on_options=[])
    assert len(specs) == 1
    s = specs[0]
    assert s.family == "foo"
    assert s.parameters == {}
    assert s.command == [sys.executable, "foo.pyt"]


def test_lock_multiple_families(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_family("a")
    m.add_family("b")
    specs = lock_model(m)
    fams = sorted([s.family for s in specs if not s.attributes.get("multicase")])
    assert fams == ["a", "b"]


def test_keywords_filters_and_flatten_unique(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_keywords("fast", "regression")
    m.add_keywords("regression", "nightly")
    m.add_keywords("only_a", when={"testname": "a"})
    m.add_keywords("p2", when={"parameters": "p=2"})
    m.add_keywords("opt", when={"options": "opt"})
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    specs = lock_model(m, on_options=["opt"])
    job = [s for s in specs if s.family == "a" and s.parameters.get("p") == 2][0]
    assert job.keywords == ["fast", "regression", "nightly", "only_a", "p2", "opt"]

    job2 = [s for s in specs if s.family == "a" and s.parameters.get("p") == 1][0]
    assert job2.keywords == ["fast", "regression", "nightly", "only_a", "opt"]


def test_timeout_last_wins(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_timeout("1s")
    m.add_timeout("2s")
    specs = lock_model(m)
    assert specs[0].timeout == 2.0


def test_exclusive_or_semantics(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_exclusive(when={"options": "opt"})
    specs1 = lock_model(m, on_options=["opt"])
    specs2 = lock_model(m, on_options=["other"])
    assert specs1[0].exclusive is True
    assert specs2[0].exclusive is False


def test_enable_true_and_false_masking_semantics(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    # enable(False) should mask unconditionally
    m.set_enable(False)
    specs = lock_model(m)
    assert specs[0].mask is not None

    # enable(True, when=...) means "require condition", else mask with reason
    m2 = make_model(tmp_path, "y.pyt")
    m2.set_enable(True, when={"options": "opt"})
    specs2 = lock_model(m2, on_options=["other"])
    assert specs2[0].mask is not None


def test_skipif_masks(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_skipif(True, reason="nope")
    specs = lock_model(m)
    assert specs[0].mask is not None


def test_modules_modulepath_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    m = make_model(tmp_path, "x.pyt")
    monkeypatch.setenv("MODULEPATH", "/a:/b")
    m.add_module("gcc", use="/x")
    specs = lock_model(m)
    mp: str = specs[0].environment.get("MODULEPATH") or ""
    assert mp.startswith("/x:")


def test_sources_and_baseline_substitution(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [2]))
    m.add_source(action="copy", src="in_${P}.txt", dst="out_{p}.txt")
    m.add_baseline(src="a_{p}.exo", dst="b_{P}.exo")
    specs = lock_model(m)
    s = [x for x in specs if x.family == "a" and x.parameters.get("p") == 2][0]
    assert s.assets[0].src.name == "in_2.txt"
    assert s.assets[0].dst == "out_2.txt"
    b = s.baseline[0]
    assert isinstance(b, BaselineCopyAction)
    assert b.src.name == "a_2.exo"
    assert b.dst == "b_2.exo"


def test_dependencies_substitution(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [2]))
    d = DependencySelector(pattern="dep_${P}", expects=1, when="on_success")
    m.add_dependency(d)
    specs = lock_model(m)
    s = [x for x in specs if x.family == "a" and x.parameters.get("p") == 2][0]
    assert len(s.dependencies) == 1
    assert s.dependencies[0].pattern == "dep_2"  # type: ignore


def test_analyze_creates_parent_case_and_dependencies(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))
    m.set_aggregate(flag="--analyze", requires="success")
    specs = lock_model(m)

    parent = [s for s in specs if s.family == "a" and s.attributes.get("multicase") is True][0]
    assert parent.command[-1] == "--analyze"
    assert len(parent.dependencies) == 2
    assert all(d.expects == 1 for d in parent.dependencies)


def test_analyze_parent_inherits_family_mask_reason(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))
    m.set_skipif(True, reason="skip family")
    m.set_aggregate(flag="--analyze", requires="success")

    specs = lock_model(m)

    children = [s for s in specs if not s.attributes.get("multicase")]
    parent = [s for s in specs if s.attributes.get("multicase") is True][0]

    assert len(children) == 2
    assert all(s.mask is not None and s.mask.reason == "skip family" for s in children)
    assert parent.mask is not None
    assert parent.mask.reason == "skip family"


def test_xdiff_uses_canary_diff_exit_status(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_xdiff()
    specs = lock_model(m)
    assert specs[0].xstatus == diff_exit_status


def test_xfail_sets_code(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_xfail(code=7)
    specs = lock_model(m)
    assert specs[0].xstatus == 7


# ------------------------- New coverage for current architecture -------------------------


def test_pyt_loader_records_directives(tmp_path: Path) -> None:
    text = """
import canary_pyt
canary_pyt.directives.keywords("fast", "nightly")
canary_pyt.directives.timeout("3s")
"""
    f = make_test_file(tmp_path, "t.pyt", text=text)
    calls = PYTLoader(file=f).parse()
    assert [c.name for c in calls] == ["keywords", "timeout"]
    assert calls[0].args == ("fast", "nightly")
    assert calls[1].args == ("3s",)
    assert calls[0].file is not None
    assert calls[0].line is not None


def test_adapter_apply_populates_model_from_calls(tmp_path: Path) -> None:
    text = """
import canary_pyt
canary_pyt.directives.testname("a")
canary_pyt.directives.parameterize("p", [1,2])
canary_pyt.directives.keywords("k1")
"""
    f = make_test_file(tmp_path, "t.pyt", text=text)
    m = PYTModel(str(tmp_path), "t.pyt")
    calls = PYTLoader(file=f).parse()
    PYTAdapter(m).apply(calls)

    specs = lock_model(m)
    fams = sorted({s.family for s in specs if not s.attributes.get("multicase")})
    assert fams == ["a"]
    params = sorted([s.parameters["p"] for s in specs if s.family == "a"])
    assert params == [1, 2]


def test_artifact_upon_mapping_success_failure(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    a = PYTAdapter(m)
    a.f_artifact("baz.txt", save_on="success")
    a.f_artifact("spam.txt", save_on="failure")
    specs = lock_model(m)
    w = {a.when for a in specs[0].artifacts if a.pattern in ("baz.txt", "spam.txt")}
    assert w == {"on_success", "on_failure"}


def test_artifact_invalid_upon_raises(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    a = PYTAdapter(m)
    with pytest.raises(ValueError):
        a.f_artifact("out.txt", save_on="nope")


def test_dependency_parsing_legacy_string(tmp_path: Path) -> None:
    # Ensure f_depends_on() string form works through adapter path
    m = make_model(tmp_path, "x.pyt")
    a = PYTAdapter(m)
    a.f_depends_on("foo*", when=None)  # type: ignore[arg-type]
    specs = lock_model(m)
    assert specs[0].dependencies[0].pattern == "foo*"


def test_parse_dependency_string_defaults() -> None:
    dep = parse_dependency("producer", 0)
    assert dep.pattern == "producer"
    assert dep.expects == "+"
    assert dep.when == "on_success"


def test_parse_dependency_rejects_blank_string() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        parse_dependency("   ", 0)


def test_parse_dependency_dict_defaults() -> None:
    dep = parse_dependency({"job": "producer"}, 0)
    assert dep.pattern == "producer"
    assert dep.expects == "+"
    assert dep.when == "on_success"


def test_parse_dependency_dict_normalizes_wildcard_when() -> None:
    dep = parse_dependency({"job": "producer", "when": "*", "expects": 1}, 0)
    assert dep.pattern == "producer"
    assert dep.expects == 1
    assert dep.when == "always"


def test_parse_dependency_accepts_outcome_name_for_when() -> None:
    dep = parse_dependency({"job": "producer", "when": "DIFFED"}, 0)
    assert dep.when == "DIFFED"


def test_parse_dependency_rejects_extra_keys() -> None:
    with pytest.raises(TypeError, match="invalid keys"):
        parse_dependency({"job": "producer", "bogus": True}, 0)


def test_parse_dependency_rejects_invalid_when() -> None:
    with pytest.raises(TypeError, match="invalid choice"):
        parse_dependency({"job": "producer", "when": "later"}, 0)


def test_parse_dependency_requires_job_key() -> None:
    with pytest.raises(TypeError, match="missing required keyword 'job'"):
        parse_dependency({"when": "always"}, 0)


def test_parse_dependency_rejects_invalid_expects_string() -> None:
    with pytest.raises(TypeError, match="invalid choice"):
        parse_dependency({"job": "producer", "expects": "2"}, 0)


def test_parse_dependency_rejects_nonpositive_integer_expects() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        parse_dependency({"job": "producer", "expects": 0}, 0)


def test_parse_dependency_rejects_invalid_expects_type() -> None:
    with pytest.raises(TypeError, match="invalid type"):
        parse_dependency({"job": "producer", "expects": []}, 0)


def test_parse_dependencies_string_with_legacy_kwargs() -> None:
    deps = parse_dependencies("producer", expect=2, result="success")
    assert len(deps) == 1
    assert deps[0].pattern == "producer"
    assert deps[0].expects == 2
    assert deps[0].when == "success"


def test_parse_dependencies_rejects_legacy_kwargs_for_non_string_arg() -> None:
    with pytest.raises(TypeError, match="only supported when 'arg' is a single string"):
        parse_dependencies({"job": "producer"}, expect=1)


def test_parse_dependencies_list_preserves_order() -> None:
    deps = parse_dependencies(["a", {"job": "b", "when": "always", "expects": "?"}])
    assert [dep.pattern for dep in deps] == ["a", "b"]
    assert deps[1].when == "always"
    assert deps[1].expects == "?"


def test_parse_dependencies_reports_index_for_bad_list_entry() -> None:
    with pytest.raises(TypeError, match=r"depends_on\[1\]\['expects'\]: invalid choice"):
        parse_dependencies(["a", {"job": "b", "expects": "bad"}])


def test_parse_dependencies_passes_through_dependency_selector() -> None:
    original = DependencySelector(pattern="producer", expects=1, when="always")
    deps = parse_dependencies(original)
    assert deps == [original]


def test_sources_relative_path_is_rooted_at_test_file(tmp_path: Path) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src="data.txt")
    specs = lock_model(m)
    assert specs[0].assets[0].src == (tmp_path / "sub" / "data.txt")


def test_analyze_script_adds_asset_link_if_missing(tmp_path: Path) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    make_test_file(tmp_path, "sub/analyze.sh", text="#!/bin/sh\necho hi\n")
    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_family("a")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))
    m.set_aggregate(script="analyze.sh")

    specs = lock_model(m)
    parent = [s for s in specs if s.attributes.get("multicase") is True][0]

    # parent should execute the script path (posix string)
    assert parent.command == [(tmp_path / "sub" / "analyze.sh").as_posix()]
    # and link it as an asset (dst should be basename)
    assert any(a.src.name == "analyze.sh" and a.action == "link" for a in parent.assets)


def test_sources_glob_expands_into_multiple_assets(tmp_path: Path) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    make_test_file(tmp_path, "sub/pattern1.txt")
    make_test_file(tmp_path, "sub/pattern2.txt")

    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src="pattern*.txt")
    specs = lock_model(m)

    srcs = sorted(a.src for a in specs[0].assets)
    assert srcs == [tmp_path / "sub" / "pattern1.txt", tmp_path / "sub" / "pattern2.txt"]


def test_sources_glob_no_matches_warns_and_skips(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    make_test_file(tmp_path, "sub/x.pyt")

    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src="does_not_exist_*.txt")

    caplog.clear()
    caplog.set_level("WARNING")

    specs = lock_model(m)

    assert specs[0].assets == []
    assert any("source glob matched nothing" in r.message for r in caplog.records)


def test_sources_glob_multiple_matches_with_dst_warns_and_ignores_dst(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    make_test_file(tmp_path, "sub/pattern1.txt")
    make_test_file(tmp_path, "sub/pattern2.txt")

    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src="pattern*.txt", dst="out.txt")

    caplog.clear()
    caplog.set_level("WARNING")

    specs = lock_model(m)
    assets = specs[0].assets

    assert sorted(a.src for a in assets) == [
        tmp_path / "sub" / "pattern1.txt",
        tmp_path / "sub" / "pattern2.txt",
    ]
    assert all(a.dst is None for a in assets)
    assert any("matched" in r.message and "dst=" in r.message for r in caplog.records)


def test_sources_absolute_glob_expands_into_multiple_assets(tmp_path: Path) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    make_test_file(tmp_path, "sub/pattern1.txt")
    make_test_file(tmp_path, "sub/pattern2.txt")

    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src=str(tmp_path / "sub" / "pattern*.txt"))
    specs = lock_model(m)

    srcs = sorted(a.src for a in specs[0].assets)
    assert srcs == [tmp_path / "sub" / "pattern1.txt", tmp_path / "sub" / "pattern2.txt"]


def test_sources_non_glob_substitutes_src_and_dst(tmp_path: Path) -> None:
    make_test_file(tmp_path, "sub/x.pyt")
    m = PYTModel(str(tmp_path), "sub/x.pyt")
    m.add_source(action="copy", src="in_${P}.txt", dst="out_{p}.txt")

    assets = m.get_sources(family=None, parameters=None, on_options=[], subs={"p": "2", "P": "2"})

    assert len(assets) == 1
    assert assets[0].src == tmp_path / "sub" / "in_2.txt"
    assert assets[0].dst == "out_2.txt"


def test_set_id_sets_explicit_jobspec_id(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef")

    specs = lock_model(m)

    assert len(specs) == 1
    assert specs[0].id == "deadbeef"


def test_set_id_normalizes_uppercase_to_lowercase(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("DEADBEEF")

    specs = lock_model(m)

    assert specs[0].id == "deadbeef"


def test_set_id_rejects_empty_template(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")

    with pytest.raises(ValueError):
        m.set_id("")


@pytest.mark.parametrize(
    "bad_id",
    [
        "abc1234",  # too short
        "dead-beef",  # punctuation
        "dead beef",  # whitespace
        "x" * 65,  # too long
    ],
)
def test_set_id_rejects_invalid_expanded_ids(tmp_path: Path, bad_id: str) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id(bad_id)

    with pytest.raises(ValueError):
        lock_model(m)


def test_set_id_when_condition(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef", when={"options": "stable"})

    specs_without = lock_model(m, on_options=[])
    specs_with = lock_model(m, on_options=["stable"])

    assert specs_without[0].id != "deadbeef"
    assert specs_with[0].id == "deadbeef"


def test_set_id_template_expands_parameters(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef{p}")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    specs = lock_model(m)

    assert sorted(s.id for s in specs) == ["deadbeef1", "deadbeef2"]


def test_set_id_template_expands_uppercase_parameter_alias(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef${P}")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    specs = lock_model(m)

    assert sorted(s.id for s in specs) == ["deadbeef1", "deadbeef2"]


def test_set_id_template_expands_meta_parameters(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef{cpus}")
    m.set_resource_parameter("cpus", 4)

    specs = lock_model(m)

    assert specs[0].id == "deadbeef4"


def test_set_id_template_rejects_invalid_expanded_id(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("dead-beef{p}")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", ["nothex"]))

    with pytest.raises(ValueError, match="expanded to an invalid ID"):
        lock_model(m)


def test_set_id_template_rejects_duplicate_expanded_ids(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    with pytest.raises(ValueError, match="duplicate ID"):
        lock_model(m)


def test_adapter_apply_set_id_from_loader(tmp_path: Path) -> None:
    text = """
import canary_pyt
canary_pyt.directives.set_id("deadbeef")
"""
    f = make_test_file(tmp_path, "t.pyt", text=text)
    m = PYTModel(str(tmp_path), "t.pyt")
    calls = PYTLoader(file=f).parse()

    PYTAdapter(m).apply(calls)
    specs = lock_model(m)

    assert specs[0].id == "deadbeef"


def test_set_id_allows_underscores(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("dead_beef")

    specs = lock_model(m)

    assert specs[0].id == "dead_beef"


def test_set_id_template_expands_parameters_with_underscores(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("dead_beef_{p}")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    specs = lock_model(m)

    assert sorted(s.id for s in specs) == ["dead_beef_1", "dead_beef_2"]


def test_set_id_template_expands_parent_analyze_with_blank_parameters(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    m.set_id("deadbeef{p}")
    m.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))
    m.set_aggregate(flag="--analyze")

    specs = lock_model(m)

    children = [s for s in specs if not s.attributes.get("multicase")]
    parent = [s for s in specs if s.attributes.get("multicase") is True][0]

    assert sorted(s.id for s in children) == ["deadbeef1", "deadbeef2"]
    assert parent.id == "deadbeef"
