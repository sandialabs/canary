from pathlib import Path

import pytest

import _canary.jobspec as js
from _canary import generate
from _canary import ir
from _canary.util.filesystem import working_dir


def _dep_ids(r: "js.JobSpec") -> list[str]:
    return [d.spec.id for d in r.dependencies]


def test_depends_on_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        Path("f1.pyt").touch()
        Path("f2.pyt").touch()
        dep = ir.DependencySpec(pattern="f1")
        drafts = [
            ir.JobSpecIR(file_root=Path("."), file_path=Path("f1.pyt"), dependencies=[]),
            ir.JobSpecIR(file_root=Path("."), file_path=Path("f2.pyt"), dependencies=[dep]),
        ]
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert _dep_ids(resolved[1]) == [resolved[0].id]
        assert [d.when for d in resolved[1].dependencies] == ["on_success"]


def test_depends_on_one_to_many(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b1 = ir.JobSpecIR(file_root=root, file_path=Path("f1.pyt"), dependencies=[])
        Path("f2.pyt").touch()

        dep = ir.DependencySpec(pattern="f1")
        b2 = ir.JobSpecIR(file_root=root, file_path=Path("f2.pyt"), dependencies=[dep])

        Path("f3.pyt").touch()
        dep = ir.DependencySpec(pattern="f1")
        b3 = ir.JobSpecIR(file_root=root, file_path=Path("f3.pyt"), dependencies=[dep])
        drafts = [b1, b2, b3]
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert _dep_ids(resolved[1]) == [resolved[0].id]
        assert _dep_ids(resolved[2]) == [resolved[0].id]
        assert [d.when for d in resolved[1].dependencies] == ["on_success"]
        assert [d.when for d in resolved[2].dependencies] == ["on_success"]


def test_depends_on_param(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        drafts = []
        for a in (1, 2, 3):
            b = ir.JobSpecIR(
                file_root=root, file_path=Path("f1.pyt"), dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        dep = ir.DependencySpec(pattern="f1.a=2")
        b = ir.JobSpecIR(file_root=root, file_path=Path("f2.pyt"), dependencies=[dep])
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert _dep_ids(resolved[3]) == [resolved[1].id]
        assert [d.when for d in resolved[3].dependencies] == ["on_success"]


def test_depends_on_many_to_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3, 4):
            b = ir.JobSpecIR(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        deps = [
            ir.DependencySpec(pattern="f1.a=1"),
            ir.DependencySpec(pattern="f1.a=3"),
            ir.DependencySpec(pattern="f1.a=4"),
        ]
        b = ir.JobSpecIR(file_root=root, file_path=f1, dependencies=deps)
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert _dep_ids(resolved[4]) == [resolved[0].id, resolved[2].id, resolved[3].id]
        assert [d.when for d in resolved[4].dependencies] == [
            "on_success",
            "on_success",
            "on_success",
        ]


def test_depends_on_glob(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = ir.JobSpecIR(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        Path("f2.pyt").touch()
        dep = ir.DependencySpec(pattern="f1.a=*")
        b = ir.JobSpecIR(file_root=root, file_path=Path("f2.pyt"), dependencies=[dep])
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert _dep_ids(resolved[3]) == [resolved[0].id, resolved[1].id, resolved[2].id]
        assert [d.when for d in resolved[3].dependencies] == [
            "on_success",
            "on_success",
            "on_success",
        ]


def test_depends_on_param_subs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        b = ir.JobSpecIR(
            file_root=root,
            file_path=f1,
            family="abc_run",
            dependencies=[],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        dep = ir.DependencySpec(pattern="abc_run.my_var=${my_var}")
        b = ir.JobSpecIR(
            file_root=root,
            file_path=f2,
            family="foobar",
            dependencies=[dep],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert _dep_ids(resolved[1]) == [resolved[0].id]
        assert [d.when for d in resolved[1].dependencies] == ["on_success"]


def test_depends_on_missing(tmpdir):
    from _canary.resolve_dependency import UnresolvedDependenciesErrors

    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        dep = ir.DependencySpec(pattern="f2")
        b = ir.JobSpecIR(file_root=root, file_path=Path("f1.pyt"), dependencies=[dep])
        with pytest.raises(UnresolvedDependenciesErrors):
            generate.resolve([b])


def test_generate_specs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = ir.JobSpecIR(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        Path("f2.pyt").touch()
        dep = ir.DependencySpec(pattern="f1.a=*")
        b = ir.JobSpecIR(file_root=root, file_path=Path("f2.pyt"), dependencies=[dep])
        drafts.append(b)
        resolved = generate.resolve(specs=drafts)
        assert len(resolved) == 4
        assert len(resolved[-1].dependencies) == 3
        assert [d.when for d in resolved[-1].dependencies] == [
            "on_success",
            "on_success",
            "on_success",
        ]
