from pathlib import Path

import pytest

import _canary.testspec as spec
from _canary import generate
from _canary.util.filesystem import working_dir


def test_depends_on_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        Path("f1.pyt").touch()
        Path("f2.pyt").touch()
        drafts = [
            spec.UnresolvedSpec(file_root=Path("."), file_path=Path("f1.pyt"), dependencies=[]),
            spec.UnresolvedSpec(file_root=Path("."), file_path=Path("f2.pyt"), dependencies=["f1"]),
        ]
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == [resolved[0]]


def test_depends_on_one_to_many(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b1 = spec.UnresolvedSpec(file_root=root, file_path=Path("f1.pyt"), dependencies=[])
        Path("f2.pyt").touch()
        b2 = spec.UnresolvedSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1"])
        Path("f3.pyt").touch()
        b3 = spec.UnresolvedSpec(file_root=root, file_path=Path("f3.pyt"), dependencies=["f1"])
        drafts = [b1, b2, b3]
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == [resolved[0]]
        assert resolved[2].dependencies == [resolved[0]]


def test_depends_on_param(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.UnresolvedSpec(
                file_root=root, file_path=Path("f1.pyt"), dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.UnresolvedSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=2"])
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert resolved[3].dependencies == [resolved[1]]


def test_depends_on_many_to_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3, 4):
            b = spec.UnresolvedSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        b = spec.UnresolvedSpec(
            file_root=root, file_path=f1, dependencies=["f1.a=1", "f1.a=3", "f1.a=4"]
        )
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert resolved[4].dependencies == [resolved[0], resolved[2], resolved[3]]


def test_depends_on_glob(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.UnresolvedSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.UnresolvedSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == []
        assert resolved[2].dependencies == []
        assert resolved[3].dependencies == [resolved[0], resolved[1], resolved[2]]


def test_depends_on_param_subs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        b = spec.UnresolvedSpec(
            file_root=root,
            file_path=f1,
            family="abc_run",
            dependencies=[],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        b = spec.UnresolvedSpec(
            file_root=root,
            file_path=f2,
            family="foobar",
            dependencies=["abc_run.my_var=${my_var}"],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        resolved = generate.resolve(drafts)
        assert resolved[1].dependencies == [resolved[0]]


def test_depends_on_missing(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b = spec.UnresolvedSpec(file_root=root, file_path=Path("f1.pyt"), dependencies=["f2"])
        with pytest.raises(spec.UnresolvedDependenciesErrors):
            generate.resolve([b])


def test_generate_specs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.UnresolvedSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.UnresolvedSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        resolved = generate.resolve(specs=drafts)
        assert len(resolved) == 4
        assert len(resolved[-1].dependencies) == 3
