from pathlib import Path

import pytest

from _canary.jobspec import Artifact
from _canary.jobspec import Asset
from _canary.jobspec import BaselineCopyAction
from _canary.jobspec import BaselineScriptAction
from _canary.jobspec import JobSpec
from _canary.jobspec import Mask
from _canary.jobspec import SpecDependency
from _canary.util import json_helper as json


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "suite").mkdir()
    (root / "suite" / "test_x.py").write_text("# test file")
    return root


def test_mask_invariants():
    with pytest.raises(TypeError):
        Mask(True, None)
    with pytest.raises(TypeError):
        Mask(False, "because")

    assert bool(Mask.masked("r")) is True
    assert bool(Mask.unmasked()) is False


def test_asset_roundtrip_json():
    a = Asset(src=Path("a/b.txt"), dst="b.txt", action="copy")
    s = json.dumps(a)
    out = json.loads(s)
    assert out == a
    assert isinstance(out.src, Path)


def test_baseline_copy_roundtrip_json():
    b = BaselineCopyAction(src=Path("out/new.txt"), dst="gold/new.txt")
    out = json.loads(json.dumps(b))
    assert out == b
    assert out.kind == "copy"
    assert isinstance(out.src, Path)


def test_baseline_script_roundtrip_json():
    b = BaselineScriptAction(script=["python", "do_rebaseline.py", "--x"])
    out = json.loads(json.dumps(b))
    assert out == b
    assert out.kind == "script"


def test_baseline_script_requires_nonempty():
    with pytest.raises(TypeError):
        BaselineScriptAction(script=[])


def test_artifact_active():
    # Use a tiny stub status with a .category like the real one
    class Cat:
        PASS = object()
        FAIL = object()

    class Status:
        def __init__(self, category):
            self.category = category

    # Monkeypatch the imported Category inside Artifact.active by mimicking the module import.
    # Easiest: just assert the always/never cases which don't import Category.
    a_always = Artifact("*.txt", when="always")
    a_never = Artifact("*.txt", when="never")
    assert a_always.active(Status(Cat.PASS)) is True
    assert a_never.active(Status(Cat.FAIL)) is False


def test_jobspec_post_init_sets_family(repo: Path):
    spec = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64)
    assert spec.family == "test_x"


def test_jobspec_file_property(repo: Path):
    spec = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64)
    assert spec.file == repo / "suite" / "test_x.py"


def test_jobspec_name_fullname_with_parameters(repo: Path):
    spec = JobSpec(
        file_root=repo,
        file_path=Path("suite/test_x.py"),
        id="a" * 64,
        family="t",
        parameters={"b": 2, "a": 1},
    )
    assert spec.name == "t.a=1.b=2"
    assert spec.fullname.endswith("suite/t.a=1.b=2")


def test_jobspec_execpath_and_viewpath_defaults(repo: Path):
    spec = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64, family="t")
    assert spec.execpath.endswith("suite/t")
    assert spec.viewpath == spec.execpath


def test_jobspec_execpath_override(repo: Path):
    spec = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="a" * 64, family="t")
    spec.execpath = "custom/exec"
    assert spec.execpath == "custom/exec"


def test_jobspec_serialization_roundtrip_includes_mask_and_baseline(repo: Path):
    spec = JobSpec(
        file_root=repo,
        file_path=Path("suite/test_x.py"),
        id="a" * 64,
        mask=Mask.masked("reason"),
        baseline=[BaselineCopyAction(src=Path("out/a"), dst="gold/a")],
        assets=[Asset(src=Path("in.dat"), dst="in.dat", action="link")],
    )
    out = json.loads(json.dumps(spec))
    assert isinstance(out, JobSpec)
    assert out.id == spec.id
    assert out.file_root == spec.file_root
    assert out.file_path == spec.file_path
    assert out.mask == spec.mask
    assert out.baseline == spec.baseline
    assert out.assets == spec.assets


def test_specdependency_roundtrip_json(repo: Path):
    upstream = JobSpec(file_root=repo, file_path=Path("suite/test_x.py"), id="b" * 64)
    dep = SpecDependency(spec=upstream, when="on_success")
    out = json.loads(json.dumps(dep))
    assert out == dep
    assert isinstance(out.spec, JobSpec)
