import json
from pathlib import Path

import pytest

import _canary.testspec as spec
from _canary.util.filesystem import working_dir


def test_depends_on_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        Path("f1.pyt").touch()
        Path("f2.pyt").touch()
        drafts = [
            spec.DraftSpec(file_root=Path("."), file_path=Path("f1.pyt"), dependencies=[]),
            spec.DraftSpec(file_root=Path("."), file_path=Path("f2.pyt"), dependencies=["f1"]),
        ]
        resolved = spec.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == [resolved[0]]


def test_depends_on_one_to_many(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b1 = spec.DraftSpec(file_root=root, file_path=Path("f1.pyt"), dependencies=[])
        Path("f2.pyt").touch()
        b2 = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1"])
        Path("f3.pyt").touch()
        b3 = spec.DraftSpec(file_root=root, file_path=Path("f3.pyt"), dependencies=["f1"])
        drafts = [b1, b2, b3]
        resolved = spec.resolve(drafts)
        assert resolved[0].dependencies == []
        assert resolved[1].dependencies == [resolved[0]]
        assert resolved[2].dependencies == [resolved[0]]


def test_depends_on_param(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.DraftSpec(
                file_root=root, file_path=Path("f1.pyt"), dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=2"])
        drafts.append(b)
        resolved = spec.resolve(drafts)
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
            b = spec.DraftSpec(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        b = spec.DraftSpec(
            file_root=root, file_path=f1, dependencies=["f1.a=1", "f1.a=3", "f1.a=4"]
        )
        drafts.append(b)
        resolved = spec.resolve(drafts)
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
            b = spec.DraftSpec(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        resolved = spec.resolve(drafts)
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
        b = spec.DraftSpec(
            file_root=root,
            file_path=f1,
            family="abc_run",
            dependencies=[],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        b = spec.DraftSpec(
            file_root=root,
            file_path=f2,
            family="foobar",
            dependencies=["abc_run.my_var=${my_var}"],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        resolved = spec.resolve(drafts)
        assert resolved[1].dependencies == [resolved[0]]


def test_depends_on_missing(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f1.pyt"), dependencies=["f2"])
        with pytest.raises(spec.DependencyResolutionFailed):
            spec.resolve([b])


def test_generate_specs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.DraftSpec(file_root=root, file_path=f1, dependencies=[], parameters={"a": a})
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        resolved = spec.resolve(specs=drafts)
        specs = spec.finalize(resolved)
        assert len(specs) == 4
        assert len(specs[-1].dependencies) == 3


def test_roundtrip(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f0 = Path("f1.pyt")
        f0.touch()
        s0 = spec.TestSpec(
            id="F0",
            file_root=root,
            file_path=f0,
            family="f0",
            dependencies=[],
            dep_done_criteria=[],
            keywords=[],
            parameters={},
            rparameters={},
            assets=[],
            baseline=[],
            artifacts=[],
            timeout=1.0,
            xstatus=0,
            exclusive=False,
            preload=None,
            modules=None,
            rcfiles=None,
            owners=None,
            mask="",
        )

        f1 = Path("f1.pyt")
        f1.touch()

        s1 = spec.TestSpec(
            id="F1",
            file_root=root,
            file_path=f1,
            family="f1",
            dependencies=[s0],
            dep_done_criteria=["success"],
            keywords=[],
            parameters={},
            rparameters={},
            assets=[spec.Asset(src=Path("a.txt"), dst="a.txt", action="copy")],
            baseline=[],
            artifacts=[],
            timeout=1.0,
            xstatus=0,
            exclusive=False,
            preload=None,
            modules=None,
            rcfiles=None,
            owners=None,
            mask="",
        )
        with open("spec.lock", "w") as fh:
            s1.dump(fh)
        with open("spec.lock", "r") as fh:
            d = json.load(fh)
            print(d)
        s = spec.TestSpec.from_dict(d, {"F0": s0})
        assert s1 == s
