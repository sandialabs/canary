import sys
from pathlib import Path

import pytest

from _canary.error import diff_exit_status
from _canary.ir import DependencySelector
from _canary.jobspec import BaselineCopyAction
from _canary.paramset import ParameterSet
from canary_pyt.pyt import PYTAdapter
from canary_pyt.pyt import PYTLoader
from canary_pyt.pyt import PYTLockEmitter
from canary_pyt.pyt import PYTModel


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
    m.set_analyze(flag="--analyze", requires="success")
    specs = lock_model(m)

    parent = [s for s in specs if s.family == "a" and s.attributes.get("multicase") is True][0]
    assert parent.command[-1] == "--analyze"
    assert len(parent.dependencies) == 2
    assert all(d.expects == 1 for d in parent.dependencies)


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
import canary
canary.directives.keywords("fast", "nightly")
canary.directives.timeout("3s")
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
import canary
canary.directives.testname("a")
canary.directives.parameterize("p", [1,2])
canary.directives.keywords("k1")
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
    a.f_artifact("out.txt", upon="success")
    a.f_artifact("err.txt", upon="failure")
    specs = lock_model(m)
    arts = specs[0].artifacts
    assert [x.when for x in arts] == ["on_success", "on_failure"]


def test_artifact_invalid_upon_raises(tmp_path: Path) -> None:
    m = make_model(tmp_path, "x.pyt")
    a = PYTAdapter(m)
    with pytest.raises(ValueError):
        a.f_artifact("out.txt", upon="nope")


def test_dependency_parsing_legacy_string(tmp_path: Path) -> None:
    # Ensure f_depends_on() string form works through adapter path
    m = make_model(tmp_path, "x.pyt")
    a = PYTAdapter(m)
    a.f_depends_on("foo*", when=None)  # type: ignore[arg-type]
    specs = lock_model(m)
    assert specs[0].dependencies[0].pattern == "foo*"


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
    m.set_analyze(script="analyze.sh")

    specs = lock_model(m)
    parent = [s for s in specs if s.attributes.get("multicase") is True][0]

    # parent should execute the script path (posix string)
    assert parent.command == [(tmp_path / "sub" / "analyze.sh").as_posix()]
    # and link it as an asset (dst should be basename)
    assert any(a.src.name == "analyze.sh" and a.action == "link" for a in parent.assets)
