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
        spec.resolve_dependencies(drafts)
        assert drafts[0].resolved_dependencies == []
        assert drafts[1].resolved_dependencies == [drafts[0]]


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
        spec.resolve_dependencies(drafts)
        assert drafts[0].resolved_dependencies == []
        assert drafts[1].resolved_dependencies == [drafts[0]]
        assert drafts[2].resolved_dependencies == [drafts[0]]


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
        spec.resolve_dependencies(drafts)
        assert drafts[0].resolved_dependencies == []
        assert drafts[1].resolved_dependencies == []
        assert drafts[2].resolved_dependencies == []
        assert drafts[3].resolved_dependencies == [drafts[1]]


def test_depends_on_many_to_one(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3, 4):
            b = spec.DraftSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        f2 = Path("f2.pyt")
        f2.touch()
        b = spec.DraftSpec(
            file_root=root, file_path=f1, dependencies=["f1.a=1", "f1.a=3", "f1.a=4"]
        )
        drafts.append(b)
        spec.resolve_dependencies(drafts)
        assert drafts[0].resolved_dependencies == []
        assert drafts[1].resolved_dependencies == []
        assert drafts[2].resolved_dependencies == []
        assert drafts[4].resolved_dependencies == [drafts[0], drafts[2], drafts[3]]


def test_depends_on_glob(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.DraftSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        spec.resolve_dependencies(drafts)
        assert drafts[0].resolved_dependencies == []
        assert drafts[1].resolved_dependencies == []
        assert drafts[2].resolved_dependencies == []
        assert drafts[3].resolved_dependencies == [drafts[0], drafts[1], drafts[2]]


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
        b = spec.DraftSpec(
            file_root=root,
            file_path=f1,
            family="abc_run",
            dependencies=["abc_run.my_var=${my_var}"],
            parameters={"my_var": 0.1},
        )
        drafts.append(b)
        spec.resolve_dependencies(drafts)
        assert drafts[1].resolved_dependencies == [drafts[0]]


def test_depends_on_missing(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        Path("f1.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f1.pyt"), dependencies=["f2"])
        with pytest.raises(spec.DependencyResolutionFailed):
            spec.resolve_dependencies([b])


def test_generate_specs(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f1 = Path("f1.pyt")
        f1.touch()
        drafts = []
        for a in (1, 2, 3):
            b = spec.DraftSpec(
                file_root=root, file_path=f1, dependencies=[], parameters={"a": a}
            )
            drafts.append(b)
        Path("f2.pyt").touch()
        b = spec.DraftSpec(file_root=root, file_path=Path("f2.pyt"), dependencies=["f1.a=*"])
        drafts.append(b)
        spec.resolve_dependencies(draft_specs=drafts)
        specs = spec.finalize(drafts)
        assert len(specs) == 4
        assert len(specs[-1].dependencies) == 3


def test_roundtrip(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        root = Path(".")
        f0 = Path("f1.pyt")
        f0.touch()
        s0 = spec.TestSpec(
            id="s0",
            file_root=root,
            file_path=f0,
            family="f0",
            dependencies=[],
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
            id="s1",
            file_root=root,
            file_path=f1,
            family="f1",
            dependencies=[s0],
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
            s = spec.TestSpec.load(fh)
        assert s1 == s
