import sys
from pathlib import Path

import pytest

from _canary.error import diff_exit_status
from _canary.generator import CanaryDSLSpecGenerator
from _canary.paramset import ParameterSet
from _canary.testspec import DependencySpec


def make_test_file(tmp_path: Path, rel: str, text: str = "# test\n") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def make_gen(tmp_path: Path, rel: str) -> CanaryDSLSpecGenerator:
    make_test_file(tmp_path, rel)
    return CanaryDSLSpecGenerator(str(tmp_path), rel)


def test_lock_no_directives_produces_one_case(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "foo.pyt")
    specs = gen.lock(on_options=[])
    assert len(specs) == 1
    s = specs[0]
    assert s.family == "foo"
    assert s.parameters == {}
    assert s.command == [sys.executable, "foo.pyt"]


def test_lock_multiple_families(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_family("a")
    gen.add_family("b")
    specs = gen.lock()
    fams = sorted([s.family for s in specs if not s.attributes.get("multicase")])
    assert fams == ["a", "b"]


def test_keywords_filters_and_flatten_unique(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_keywords("fast", "regression")
    gen.add_keywords("regression", "nightly")
    gen.add_keywords("only_a", when={"testname": "a"})
    gen.add_keywords("p2", when={"parameters": "p=2"})
    gen.add_keywords("opt", when={"options": "opt"})
    gen.add_family("a")
    gen.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))

    specs = gen.lock(on_options=["opt"])
    case = [s for s in specs if s.family == "a" and s.parameters.get("p") == 2][0]
    assert case.keywords == ["fast", "regression", "nightly", "only_a", "p2", "opt"]

    case2 = [s for s in specs if s.family == "a" and s.parameters.get("p") == 1][0]
    assert case2.keywords == ["fast", "regression", "nightly", "only_a", "opt"]


def test_timeout_last_wins(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_timeout("1s")
    gen.add_timeout("2s")
    specs = gen.lock()
    assert specs[0].timeout == 2.0


def test_exclusive_or_semantics(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.set_exclusive(when={"options": "opt"})
    specs1 = gen.lock(on_options=["opt"])
    specs2 = gen.lock(on_options=["other"])
    assert specs1[0].exclusive is True
    assert specs2[0].exclusive is False


def test_enable_masks(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.set_enable(False)
    specs = gen.lock()
    assert specs[0].mask is not None


def test_skipif_masks(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.set_skipif(True, reason="nope")
    specs = gen.lock()
    assert specs[0].mask is not None


def test_modules_modulepath_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    monkeypatch.setenv("MODULEPATH", "/a:/b")
    gen.add_module("gcc", use="/x")
    specs = gen.lock()
    assert specs[0].environment["MODULEPATH"].startswith("/x:")


def test_sources_and_baseline_substitution(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_family("a")
    gen.add_parameter_set(ParameterSet.list_parameter_space("p", [2]))
    gen.add_source("copy", src="in_${P}.txt", dst="out_{p}.txt")
    gen.add_baseline(src="a_{p}.exo", dst="b_{P}.exo")
    specs = gen.lock()
    s = [x for x in specs if x.family == "a" and x.parameters.get("p") == 2][0]
    assert ("in_2.txt", "out_2.txt") in s.file_resources.get("copy", [])  # type: ignore
    assert ("a_2.exo", "b_2.exo") in s.baseline


def test_dependencies_substitution(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_family("a")
    gen.add_parameter_set(ParameterSet.list_parameter_space("p", [2]))
    d = DependencySpec(pattern="dep_${P}", expects=1, when="on_success")
    gen.add_dependency(d)
    specs = gen.lock()
    s = [x for x in specs if x.family == "a" and x.parameters.get("p") == 2][0]
    assert len(s.dependencies) == 1
    assert s.dependencies[0].pattern == "dep_2"  # type: ignore


def test_analyze_creates_parent_case_and_dependencies(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.add_family("a")
    gen.add_parameter_set(ParameterSet.list_parameter_space("p", [1, 2]))
    gen.set_analyze(flag="--analyze", requires="success")
    specs = gen.lock()
    parent = [s for s in specs if s.family == "a" and s.attributes.get("multicase") is True][0]
    assert parent.command[-1] == "--analyze"
    assert len(parent.dependencies) == 2


def test_xdiff_uses_canary_diff_exit_status(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.set_xdiff()
    specs = gen.lock()
    assert specs[0].xstatus == diff_exit_status


def test_xfail_sets_code(tmp_path: Path) -> None:
    gen = make_gen(tmp_path, "x.pyt")
    gen.set_xfail(code=7)
    specs = gen.lock()
    assert specs[0].xstatus == 7
