# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

import _canary.config as config
from _canary import select
from _canary.core import rules
from _canary.generation import collect
from _canary.generation.generate import Generator as CanaryGenerator
from _canary.util.filesystem import working_dir
from canary_vvtest.vvt import VVTestAdapter
from canary_vvtest.vvt import VVTestLoader
from canary_vvtest.vvt import VVTestModel
from canary_vvtest.vvt import VVTParseError
from canary_vvtest.vvt import find_vvt_lines
from canary_vvtest.vvt import make_table
from canary_vvtest.vvt import p_PARAMETERIZE
from canary_vvtest.vvt import p_VVT

# ----------------------------- helpers -----------------------------


def generate_specs(generators, on_options=None):
    gen = CanaryGenerator(generators=generators, workspace=Path.cwd(), on_options=on_options or [])
    return gen.run()


def select_specs(
    specs,
    *,
    keyword_exprs=None,
    parameter_expr=None,
    owners=None,
    regex=None,
    ids=None,
    prefixes=None,
):
    selector = select.Selector(specs, workspace=Path.cwd())
    if keyword_exprs:
        selector.add_rule(rules.KeywordRule(keyword_exprs))
    if parameter_expr:
        selector.add_rule(rules.ParameterRule(parameter_expr))
    if owners:
        selector.add_rule(rules.OwnersRule(owners))
    if regex:
        selector.add_rule(rules.RegexRule(regex))
    if ids:
        selector.add_rule(rules.IDsRule(ids))
    if prefixes:
        selector.add_rule(rules.PrefixRule(prefixes))
    selector.run()
    return [spec for spec in selector.specs if not spec.mask]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_vvt_model(tmp_path: Path, rel: str, text: str) -> VVTestModel:
    f = tmp_path / rel
    write(f, text)
    m = VVTestModel(root=str(tmp_path), path=rel)
    directives = VVTestLoader(file=f).parse()
    VVTestAdapter(m).apply(directives)
    return m


# ----------------------------- generator integration -----------------------------


def test_vvt_generator_integration_smoke(tmp_path: Path) -> None:
    with working_dir(tmp_path.as_posix(), create=True):
        write(
            tmp_path / "test.vvt",
            """
# VVT: name: baz
# VVT: analyze : --analyze
# VVT: keywords: test unit
# VVT: parameterize (options=baz) : np=1 2
# VVT: parameterize : a,b,c=1,11,111 2,22,222 3,33,333
""",
        )

        with config.override():
            generators = collect.find_generators_in_path(".")
            specs = generate_specs(generators, on_options=["baz"])
            final = select_specs(specs, keyword_exprs=["test and unit"])

            # np expands (2) * a,b,c expands (3) => 6 + analyze parent => 7
            assert len(specs) == 7
            assert specs[-1].attributes.get("multicase") is True
            assert len(final) == 7

            # Without "baz", np paramset does not activate => only a,b,c (3) + analyze => 4
            specs2 = generate_specs(generators)
            assert specs2[-1].attributes.get("multicase") is True
            assert len(specs2) == 4
            final2 = select_specs(specs2, keyword_exprs=["test and unit"])
            assert len(final2) == 4

            # Parameter rule on np
            specs3 = generate_specs(generators, on_options=["baz"])
            final3 = select_specs(specs3, keyword_exprs=["test and unit"], parameter_expr="np < 2")
            assert len(specs3) == 7
            assert (
                len(final3) == 3
            )  # (a,b,c=3) at np=1 plus analyze parent? depends on rule; match prior behavior

            # Parameter rule on cpus (vvtest plugin maps np->cpus in canary_generate_modifyitems)
            specs4 = generate_specs(generators, on_options=["baz"])
            final4 = select_specs(
                specs4, keyword_exprs=["test and unit"], parameter_expr="cpus < 2"
            )
            assert len(specs4) == 7
            assert len(final4) == 3


# ----------------------------- parsing (loader) -----------------------------


def test_find_vvt_lines_and_continuations() -> None:
    s = """\
#!/usr/bin/env python3
# VVT: parameterize (autotype) : np,n = 1,2 3,4 5,6
# VVT: : 7,8
print("stop scanning here")
# VVT: keywords: should_not_be_seen
"""
    lines, _ = find_vvt_lines(s)
    assert len(lines) == 1
    # continuation should have been appended
    assert "7,8" in lines[0]
    assert lines[0].lstrip().startswith("parameterize")


def test_p_vvt_yields_directives_with_when_options() -> None:
    s = """\
#!/usr/bin/env python3
# VVT: keywords (testname="a", option="opt") : fast nightly
"""
    directives = list(p_VVT(s))
    assert len(directives) == 1
    d = directives[0]
    assert d.name == "keywords"
    # filter opts become `when` expressions
    assert d.when == {"testname": "a", "options": "opt"}
    # non-filter options stay in options list
    assert d.options == []
    assert d.argument == "fast nightly"


# ----------------------------- adapter->model behavior -----------------------------


def test_adapter_keywords_timeout_enable_skipif(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: keywords : fast regression
# VVT: timeout : 2m
# VVT: enable : false
# VVT: skipif (reason="nope") : true
""",
    )
    specs = m  # model
    irs = m  # just to avoid confusion

    # lock and check effects
    from canary_vvtest.vvt import VVTestLockEmitter

    locked = VVTestLockEmitter().lock(m, on_options=[])
    assert len(locked) == 1
    s = locked[0]
    assert "fast" in s.keywords and "regression" in s.keywords
    assert s.timeout == pytest.approx(120.0)
    assert s.mask is not None  # enable(false) and/or skipif(true)


def test_adapter_sources_copy_link_rename(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: copy (rename) : in.txt,out.txt  a.dat, b.dat
# VVT: link : foo bar
# VVT: sources : baz
""",
    )
    from canary_vvtest.vvt import VVTestLockEmitter

    locked = VVTestLockEmitter().lock(m, on_options=[])
    assets = locked[0].assets

    # copy rename yields dst not None
    c1 = [a for a in assets if a.action == "copy"]
    assert len(c1) == 2
    assert c1[0].dst is not None and c1[1].dst is not None

    # link yields dst None and src resolves relative to file dir
    l1 = [a for a in assets if a.action == "link"]
    assert sorted([a.src.name for a in l1]) == ["bar", "foo"]

    n1 = [a for a in assets if a.action == "none"]
    assert [a.src.name for a in n1] == ["baz"]


def test_adapter_baseline_flag_and_copy(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: baseline : a.exo,b.exo
# VVT: baseline : --rebaseline
""",
    )
    from canary_vvtest.vvt import VVTestLockEmitter

    locked = VVTestLockEmitter().lock(m, on_options=[])
    b = locked[0].baseline
    assert len(b) == 2
    assert isinstance(b[0], type(b[0]))  # sanity: baseline actions exist
    # One should be BaselineCopyAction
    from _canary.core.jobspec import BaselineCopyAction
    from _canary.core.jobspec import BaselineScriptAction

    assert any(isinstance(x, BaselineCopyAction) for x in b)
    assert any(isinstance(x, BaselineScriptAction) for x in b)


def test_adapter_parameterize_generates_cases(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : a
# VVT: parameterize : np,n = 1,2 3,4 5,6
""",
    )
    from canary_vvtest.vvt import VVTestLockEmitter

    locked = VVTestLockEmitter().lock(m, on_options=[])
    # 3 cases from parameterize
    assert len([s for s in locked if s.family == "a"]) == 3
    params = sorted([s.parameters for s in locked if s.family == "a"], key=lambda d: d["np"])
    assert params == [{"np": 1, "n": "2"}, {"np": 3, "n": "4"}, {"np": 5, "n": "6"}]


def test_adapter_parameterize_when_options_gate_expansion(tmp_path: Path) -> None:
    text = """
# VVT: name : a
# VVT: parameterize (options=opt) : np = 1 2
"""
    f = tmp_path / "x.vvt"
    write(f, text)
    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()
    VVTestAdapter(m).apply(directives)

    from canary_vvtest.vvt import VVTestLockEmitter

    locked_no = VVTestLockEmitter().lock(m, on_options=[])
    locked_yes = VVTestLockEmitter().lock(m, on_options=["opt"])

    assert len([s for s in locked_no if s.family == "a"]) == 1  # no params expanded => default {}
    assert len([s for s in locked_yes if s.family == "a"]) == 2  # expanded np=1,2


# ----------------------------- include behavior -----------------------------


def test_include_recursion(tmp_path: Path) -> None:
    with working_dir(tmp_path.as_posix(), create=True):
        write(tmp_path / "file1.txt", "# VVT: include : ./file2.txt\n")
        write(tmp_path / "file2.txt", "# VVT: include : ./file3.txt\n")
        write(tmp_path / "file3.txt", "# VVT: parameterize (int, int) : np,n = 1,2 3,4 5,6 7,8\n")

        s = "# VVT: include : ./file1.txt"
        directives = list(p_VVT(s))
        assert directives[0].name == "parameterize"
        names, values, kwds, _ = p_PARAMETERIZE(directives[0])
        assert names == ["np", "n"]
        assert values == [[1, 2], [3, 4], [5, 6], [7, 8]]
        assert kwds["type"] is not None


# ----------------------------- table parsing -----------------------------


def test_make_table_quotes_and_commas() -> None:
    table = make_table("a.0,'b,0',c, 1-0   e ,2.0  ,    6.5,       a.b-foo-baz")
    assert table == [["a.0", "'b,0'", "c", "1-0"], ["e", "2.0", "6.5", "a.b-foo-baz"]]
    assert make_table("1,2 3,4 5,6 7,8") == [["1", "2"], ["3", "4"], ["5", "6"], ["7", "8"]]


# ----------------------------- error paths -----------------------------


def test_unknown_directive_raises(tmp_path: Path) -> None:
    f = tmp_path / "x.vvt"
    write(f, "# VVT: does_not_exist : foo\n")
    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()
    with pytest.raises(VVTParseError):
        VVTestAdapter(m).apply(directives)


def test_include_cycle_raises_vvtparseerror(tmp_path: Path) -> None:
    from canary_vvtest.vvt import p_VVT

    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    write(a, "# VVT: include : ./b.txt\n")
    write(b, "# VVT: include : ./a.txt\n")

    with pytest.raises(VVTParseError, match="include cycle detected"):
        list(p_VVT(a))


def test_safe_eval_does_not_expose_os_or_sys(tmp_path: Path) -> None:
    from canary_vvtest.vvt import evaluate_boolean_expression

    assert evaluate_boolean_expression("__import__('os').getpid()") is None
    assert evaluate_boolean_expression("os.getcwd()") is None


def test_malformed_directive_is_wrapped_in_vvtparseerror(tmp_path: Path) -> None:
    from canary_vvtest.vvt import ParseError
    from canary_vvtest.vvt import p_VVT

    f = tmp_path / "bad.vvt"
    write(f, "# VVT: parameterize (int : np = 1 2\n")

    with pytest.raises(ParseError, match="failed to parse directive"):
        list(p_VVT(f))


def lock_vvt_model(m: VVTestModel, on_options=None):
    from canary_vvtest.vvt import VVTestLockEmitter

    return VVTestLockEmitter().lock(m, on_options=on_options or [])


def test_adapter_metadata_resource_environment_and_artifact_directives(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: description : this directive is accepted but currently has no model effect
# VVT: name : main
# VVT: set_id : abcdef12
# VVT: owner : alice
# VVT: owners : bob carol
# VVT: cpus : 4
# VVT: gpus : 1
# VVT: nodes : 2
# VVT: set_attribute (queue=debug, priority=high)
# VVT: set_attribute : account=proj123 qos=normal
# VVT: load_module (use="/opt/modules") : gcc
# VVT: load_module : cmake
# VVT: source : env.sh extra-env.sh
# VVT: artifact : results/*.txt
# VVT: artifact (save_on=failure) : debug.log
# VVT: artifact (save_on=success) : summary.log
# VVT: execution_path : runs/{name}
# VVT: exclusive
""",
    )

    locked = lock_vvt_model(m)
    assert len(locked) == 1

    s = locked[0]

    assert s.family == "main"
    assert s.id == "abcdef12"

    assert s.owners == ["alice", "bob", "carol"]

    assert s.meta_parameters["cpus"] == 4
    assert s.meta_parameters["gpus"] == 1
    assert s.meta_parameters["nodes"] == 2

    assert s.attributes["queue"] == "debug"
    assert s.attributes["priority"] == "high"
    assert s.attributes["account"] == "proj123"
    assert s.attributes["qos"] == "normal"

    assert s.modules == ["gcc", "cmake"]
    assert s.environment["MODULEPATH"].split(":")[0] == "/opt/modules"

    assert s.rcfiles == ["env.sh", "extra-env.sh"]

    artifacts = {a.pattern: a.when for a in s.artifacts}
    assert artifacts["results/*.txt"] == "always"
    assert artifacts["debug.log"] == "on_failure"
    assert artifacts["summary.log"] == "on_success"

    assert s.exec_path == "runs/main"
    assert s.exclusive is True


def test_adapter_xfail_default_code(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: xfail
""",
    )

    locked = lock_vvt_model(m)

    assert len(locked) == 1
    assert locked[0].xstatus == -1


def test_adapter_xfail_code_from_option(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: xfail (code=17)
""",
    )

    locked = lock_vvt_model(m)

    assert len(locked) == 1
    assert locked[0].xstatus == 17


def test_adapter_xfail_code_from_argument(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: xfail : 23
""",
    )

    locked = lock_vvt_model(m)

    assert len(locked) == 1
    assert locked[0].xstatus == 23


def test_adapter_xdiff(tmp_path: Path) -> None:
    from _canary.core.error import diff_exit_status

    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: xdiff
""",
    )

    locked = lock_vvt_model(m)

    assert len(locked) == 1
    assert locked[0].xstatus == diff_exit_status


def test_adapter_xstatus_when_options_are_honored(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : a
# VVT: name : b
# VVT: xfail (testname=a, code=11)
# VVT: xdiff (testname=b)
""",
    )

    locked = sorted(lock_vvt_model(m), key=lambda s: s.family)

    from _canary.core.error import diff_exit_status

    assert len(locked) == 2
    assert locked[0].family == "a"
    assert locked[0].xstatus == 11
    assert locked[1].family == "b"
    assert locked[1].xstatus == diff_exit_status


def test_adapter_aggregate_flag_creates_multicase_parent(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: aggregate (flag=--pack, requires=always)
""",
    )

    locked = lock_vvt_model(m)

    cases = [s for s in locked if not s.attributes.get("multicase")]
    parents = [s for s in locked if s.attributes.get("multicase") is True]

    assert len(cases) == 2
    assert len(parents) == 1

    parent = parents[0]
    assert parent.family == "agg"
    assert parent.command[-1] == "--pack"
    assert parent.attributes["paramsets"] == [{"keys": ["np"], "values": [[1], [2]]}]


def test_adapter_aggregate_argument_flag_creates_multicase_parent(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: aggregate : --analyze
""",
    )

    locked = lock_vvt_model(m)
    parent = next(s for s in locked if s.attributes.get("multicase") is True)

    assert parent.command[-1] == "--analyze"


def test_adapter_aggregate_argument_script_creates_multicase_parent(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: aggregate : analyze.py
""",
    )

    locked = lock_vvt_model(m)
    parent = next(s for s in locked if s.attributes.get("multicase") is True)

    assert parent.command == [(tmp_path / "analyze.py").as_posix()]
    assert any(a.action == "link" and a.src.name == "analyze.py" for a in parent.assets)


def test_adapter_generate_composite_base_case_script_creates_multicase_parent(
    tmp_path: Path,
) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: generate_composite_base_case (script=make_base.py, requires=always)
""",
    )

    locked = lock_vvt_model(m)
    parent = next(s for s in locked if s.attributes.get("multicase") is True)

    assert parent.command == [(tmp_path / "make_base.py").as_posix()]
    assert any(a.action == "link" and a.src.name == "make_base.py" for a in parent.assets)


def test_adapter_generate_composite_base_case_argument_script_creates_multicase_parent(
    tmp_path: Path,
) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: generate_composite_base_case : make_base.py
""",
    )

    locked = lock_vvt_model(m)
    parent = next(s for s in locked if s.attributes.get("multicase") is True)

    assert parent.command == [(tmp_path / "make_base.py").as_posix()]
    assert any(a.action == "link" and a.src.name == "make_base.py" for a in parent.assets)


def test_adapter_analyze_without_arguments_defaults_to_analyze_flag(tmp_path: Path) -> None:
    m = load_vvt_model(
        tmp_path,
        "x.vvt",
        """
# VVT: name : agg
# VVT: parameterize : np = 1 2
# VVT: analyze
""",
    )

    locked = lock_vvt_model(m)
    parent = next(s for s in locked if s.attributes.get("multicase") is True)

    assert parent.command[-1] == "--analyze"


def test_adapter_invalid_xfail_code_raises_parse_error(tmp_path: Path) -> None:
    f = tmp_path / "x.vvt"
    write(
        f,
        """
# VVT: xfail : not-an-int
""",
    )

    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()

    with pytest.raises(VVTParseError, match="xfail"):
        VVTestAdapter(m).apply(directives)


def test_adapter_invalid_artifact_save_on_raises_parse_error(tmp_path: Path) -> None:
    f = tmp_path / "x.vvt"
    write(
        f,
        """
# VVT: artifact (save_on=sometimes) : debug.log
""",
    )

    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()

    with pytest.raises(VVTParseError, match="artifact"):
        VVTestAdapter(m).apply(directives)


def test_adapter_invalid_set_attribute_argument_raises_parse_error(tmp_path: Path) -> None:
    f = tmp_path / "x.vvt"
    write(
        f,
        """
# VVT: set_attribute : not-key-value
""",
    )

    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()

    with pytest.raises(VVTParseError, match="set_attribute"):
        VVTestAdapter(m).apply(directives)


def test_adapter_invalid_resource_count_raises(tmp_path: Path) -> None:
    f = tmp_path / "x.vvt"
    write(
        f,
        """
# VVT: cpus : 0
""",
    )

    m = VVTestModel(root=str(tmp_path), path="x.vvt")
    directives = VVTestLoader(file=f).parse()

    with pytest.raises(ValueError, match="cpus"):
        VVTestAdapter(m).apply(directives)
