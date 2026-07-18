# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
from pathlib import Path

import pytest

import canary
from _canary.error import StopExecution
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def data_dir() -> Path:
    here = Path(__file__).parent
    candidates = [here / "data", here.parent / "data"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not find tests data dir from {here}")


def find_job_by_name(workspace: Workspace, name: str):
    for job in workspace.load_jobs():
        if job.name == name:
            return job
    names = sorted(job.name for job in workspace.load_jobs())
    raise AssertionError(f"No job named {name!r}. Available: {names}")


def txtfiles(path: Path) -> list[str]:
    return sorted(p.name for p in Path(path).glob("*.txt") if not p.name.startswith("canary-"))


def dump_outputs(root: Path) -> None:
    for file in glob.glob(str(root / "TestResults/**/canary-out.txt"), recursive=True):
        print(f"\n--- {file} ---")
        print(Path(file).read_text())


def create_workspace_and_collect(
    root: Path,
    scanpaths: dict[str, list[str]] | None = None,
    *,
    on_options: list[str] | None = None,
) -> tuple[Workspace, list]:
    workspace = Workspace.create(root)
    specs = workspace.collect(scanpaths or {str(root): []}, on_options=on_options)
    return workspace, specs


def run_specs(
    root: Path,
    scanpaths: dict[str, list[str]] | None = None,
    *,
    on_options: list[str] | None = None,
    only: str = "all",
    expected_returncode: int = 0,
):
    with working_dir(root), canary.config.override():
        workspace, specs = create_workspace_and_collect(root, scanpaths, on_options=on_options)
        session = workspace.run(specs, only=only)
        if session.returncode != expected_returncode:
            dump_outputs(root)
        assert session.returncode == expected_returncode
        return workspace, session


def test_core_pyt_directives(tmp_path):
    root = tmp_path / "core"
    root.mkdir()

    write(
        root / "kw_basic.pyt",
        """\
import sys
import canary

canary.directives.keywords('a', 'b', 'c')

def test():
    self = canary.get_instance()
    assert self.keywords == ['a', 'b', 'c']

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "kw_testname.pyt",
        """\
import sys
import canary

canary.directives.testname('kw_name_a')
canary.directives.testname('kw_name_b')
canary.directives.keywords('kw_a', when={'testname': 'kw_name_a'})
canary.directives.keywords('kw_b', when='testname="kw_name_b"')

def test():
    self = canary.get_instance()
    if self.name == 'kw_name_a':
        assert self.keywords == ['kw_a']
    elif self.name == 'kw_name_b':
        assert self.keywords == ['kw_b']
    else:
        raise AssertionError(self.name)

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "kw_parameters.pyt",
        """\
import sys
import canary

canary.directives.parameterize('a', (2, 4, 6, 8, 10))
canary.directives.keywords('kw_2', when='parameters="a=2"')
canary.directives.keywords('kw_4', when='parameters="a=4"')
canary.directives.keywords('kw_6', when='parameters="a>4 and a<8"')
canary.directives.keywords('kw_8', when='parameters="a>=7"')
canary.directives.keywords('kw_9', 'kw_10', when='parameters="a>8"')

def test():
    self = canary.get_instance()
    if self.parameters.a == 2:
        assert self.keywords == ['kw_2']
    elif self.parameters.a == 4:
        assert self.keywords == ['kw_4']
    elif self.parameters.a == 6:
        assert self.keywords == ['kw_6']
    elif self.parameters.a == 8:
        assert self.keywords == ['kw_8']
    elif self.parameters.a == 10:
        assert set(self.keywords) == {'kw_8', 'kw_9', 'kw_10'}
    else:
        raise AssertionError(self.parameters.a)

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "parameterize_basic.pyt",
        """\
import sys
import canary

canary.directives.parameterize('a,b,c', [(1, 2, 3), (4, 5, 6)])

def test():
    self = canary.get_instance()
    a = self.parameters.a
    assert self.parameters[('a', 'b', 'c')] == (a, a + 1, a + 2)

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "parameterize_product.pyt",
        """\
import sys
import canary

canary.directives.analyze()
canary.directives.parameterize('a,b', [('a1', 'b1'), ('a2', 'b2')])
canary.directives.parameterize('c,d', [('c1', 'd1'), ('c2', 'd2')])

def test():
    self = canary.get_instance()
    abcd = self.parameters[('a', 'b', 'c', 'd')]
    assert abcd in [
        ('a1', 'b1', 'c1', 'd1'),
        ('a1', 'b1', 'c2', 'd2'),
        ('a2', 'b2', 'c1', 'd1'),
        ('a2', 'b2', 'c2', 'd2'),
    ]

def analyze():
    self = canary.get_instance()
    assert self.parameters.a == ('a1', 'a1', 'a2', 'a2')
    assert self.parameters.b == ('b1', 'b1', 'b2', 'b2')
    assert self.parameters.c == ('c1', 'c2', 'c1', 'c2')
    assert self.parameters.d == ('d1', 'd2', 'd1', 'd2')
    assert self.parameters[('a', 'b', 'c', 'd')] == (
        ('a1', 'b1', 'c1', 'd1'),
        ('a1', 'b1', 'c2', 'd2'),
        ('a2', 'b2', 'c1', 'd1'),
        ('a2', 'b2', 'c2', 'd2'),
    )
    assert self.parameters[('b', 'c', 'd', 'a')] == (
        ('b1', 'c1', 'd1', 'a1'),
        ('b1', 'c2', 'd2', 'a1'),
        ('b2', 'c1', 'd1', 'a2'),
        ('b2', 'c2', 'd2', 'a2'),
    )

if __name__ == '__main__':
    if '--analyze' in sys.argv[1:]:
        rc = analyze()
    else:
        rc = test()
    sys.exit(rc)
""",
    )

    write(
        root / "dep_source.pyt",
        """\
import sys
import canary

def test():
    canary.filesystem.touchp("baz.txt")

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_one.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on('dep_source')

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].working_directory, "baz.txt"))

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_many_a.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on('dep_source')

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].working_directory, "baz.txt"))

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_many_b.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on('dep_source')

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    assert os.path.exists(os.path.join(self.dependencies[0].working_directory, "baz.txt"))

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_glob_source.pyt",
        """\
import sys
import canary

canary.directives.parameterize('a', (1, 2, 3))

def test():
    self = canary.get_instance()
    canary.filesystem.touchp(f"baz-{self.parameters.a}.txt")

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_glob_consumer.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on('dep_glob_source.a=2')

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    dep = self.dependencies[0]
    assert dep.parameters.a == 2
    assert os.path.exists(os.path.join(dep.working_directory, "baz-2.txt"))

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_list_source.pyt",
        """\
import sys
import canary

canary.directives.parameterize('a', (1, 2, 3, 4))

def test():
    self = canary.get_instance()
    canary.filesystem.touchp(f"baz-{self.parameters.a}.txt")

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "dep_list_consumer.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on(['dep_list_source.a=1', 'dep_list_source.a=3', 'dep_list_source.a=4'])

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 3
    values = sorted(dep.parameters.a for dep in self.dependencies)
    assert values == [1, 3, 4]
    for dep in self.dependencies:
        assert os.path.exists(os.path.join(dep.working_directory, f"baz-{dep.parameters.a}.txt"))

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "copy_src.txt", "copy source")
    write(root / "link_src.txt", "link source")
    write(
        root / "copy_link.pyt",
        """\
import os
import sys
import canary

canary.directives.copy(src='copy_src.txt', dst='copied.txt')
canary.directives.link(src='link_src.txt', dst='linked.txt')

def test():
    assert os.path.exists('copied.txt')
    assert not os.path.islink('copied.txt')
    assert os.path.islink('linked.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "xfail_case.pyt",
        """\
import sys
import canary

canary.directives.xfail()

def test():
    raise canary.TestFailed()

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(
        root / "xdiff_case.pyt",
        """\
import sys
import canary

canary.directives.xdiff()

def test():
    raise canary.TestDiffed()

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    workspace, session = run_specs(root, expected_returncode=0)
    assert (root / "TestResults" / ".canary-view.json").exists()
    assert session.returncode == 0
    assert workspace.db.get_results()


def test_analyze_generators(tmp_path):
    root = tmp_path / "analyze"
    root.mkdir()

    generator_dir = (Path(__file__).parent / "data/generators").resolve()
    scanpaths = {str(generator_dir): ["analyze.pyt", "analyze_alt_flag.pyt", "analyze_script.pyt"]}

    run_specs(root, scanpaths=scanpaths, expected_returncode=0)


def test_baseline_directives(tmp_path):
    root = tmp_path / "baseline"
    root.mkdir()

    write(root / "a.txt", "null")
    write(
        root / "baseline_copy.pyt",
        """\
import sys
import canary

canary.directives.parameterize('a', (1, 2))
canary.directives.baseline(src='a-out.txt', dst='a.txt', when='parameters="a=1"')

def test():
    self = canary.get_instance()
    with open('a-out.txt', 'w') as fh:
        fh.write(f'a={self.parameters.a}')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "b.txt", "null")
    write(
        root / "baseline_flag.pyt",
        """\
import os
import sys
import canary

canary.directives.parameterize('a', (1, 2))
canary.directives.baseline(flag='--baseline', when='parameters="a=1"')

def test():
    self = canary.get_instance()
    with open('b-out.txt', 'w') as fh:
        fh.write(f'b={self.parameters.a}')

def baseline():
    self = canary.get_instance()
    assert self.parameters.a == 1
    dst = os.path.join(os.path.dirname(self.file), 'b.txt')
    with open(dst, 'w') as fh:
        fh.write(open('b-out.txt').read())

if __name__ == '__main__':
    if '--baseline' in sys.argv:
        rc = baseline()
    else:
        rc = test()
    sys.exit(rc)
""",
    )

    workspace, _ = run_specs(root, expected_returncode=0)

    for job in workspace.load_jobs():
        job.do_baseline()

    assert (root / "a.txt").read_text() == "a=1"
    assert (root / "b.txt").read_text() == "b=1"


def test_enable_directive(tmp_path):
    root = tmp_path / "enable"
    root.mkdir()

    write(
        root / "f1.pyt",
        """\
import sys
import canary

canary.directives.enable(when='options=baz')

def test():
    pass

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace, specs = create_workspace_and_collect(root)
        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="all")
        assert exc.value.exit_code == 7

    root_enabled = tmp_path / "enable_on"
    root_enabled.mkdir()
    write((root_enabled / "f1.pyt"), (root / "f1.pyt").read_text())

    workspace, session = run_specs(root_enabled, on_options=["baz"], expected_returncode=0)
    assert session.returncode == 0
    assert set(os.listdir(root_enabled / "TestResults")) == {".canary-view.json", "f1"}
    assert workspace.db.get_results()


def test_skipif_directive(tmp_path, monkeypatch):
    root = tmp_path / "skipif"
    root.mkdir()

    write(
        root / "f1.pyt",
        """\
import os
import sys
import canary

canary.directives.skipif(os.getenv('CANARY_BAZ') is not None, reason='just because')

def test():
    pass

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    run_specs(root, expected_returncode=0)
    assert set(os.listdir(root / "TestResults")) == {".canary-view.json", "f1"}

    root_skipped = tmp_path / "skipif_masked"
    root_skipped.mkdir()
    write(root_skipped / "f1.pyt", (root / "f1.pyt").read_text())

    monkeypatch.setenv("CANARY_BAZ", "1")
    with working_dir(root_skipped), canary.config.override():
        workspace, specs = create_workspace_and_collect(root_skipped, on_options=["baz"])
        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="all")
        assert exc.value.exit_code == 7


def test_timeout_directive(tmp_path):
    root = tmp_path / "timeout"
    root.mkdir()

    write(
        root / "f1.pyt",
        """\
import sys
import time
import canary

canary.directives.timeout('1us')

def test():
    time.sleep(10)

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    run_specs(root, expected_returncode=4)


def test_copy_and_link_directives(tmp_path):
    root = tmp_path / "copy-link"
    root.mkdir()

    write(root / "foo" / "foo.txt", "foo")
    write(root / "foo" / "baz.txt", "baz")
    write(
        root / "foo" / "copy_basic.pyt",
        """\
import os
import sys
import canary

canary.directives.copy('foo.txt', 'baz.txt')

def test():
    assert os.path.exists('./foo.txt')
    assert os.path.exists('./baz.txt')
    assert not os.path.islink('./foo.txt')
    assert not os.path.islink('./baz.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "rename" / "foo.txt", "foo")
    write(root / "rename" / "baz.txt", "baz")
    write(
        root / "rename" / "copy_rename.pyt",
        """\
import os
import sys
import canary

canary.directives.copy(src='foo.txt', dst='foo_copy.txt')
canary.directives.copy(src='baz.txt', dst='baz_copy.txt')

def test():
    assert os.path.exists('./foo_copy.txt')
    assert os.path.exists('./baz_copy.txt')
    assert not os.path.islink('./foo_copy.txt')
    assert not os.path.islink('./baz_copy.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "link" / "foo.txt", "foo")
    write(root / "link" / "baz.txt", "baz")
    write(
        root / "link" / "link_basic.pyt",
        """\
import os
import sys
import canary

canary.directives.link('foo.txt', 'baz.txt')

def test():
    assert os.path.islink('./foo.txt')
    assert os.path.islink('./baz.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "link_rename" / "foo.txt", "foo")
    write(root / "link_rename" / "baz.txt", "baz")
    write(
        root / "link_rename" / "link_rename.pyt",
        """\
import os
import sys
import canary

canary.directives.link(src='foo.txt', dst='foo_link.txt')
canary.directives.link(src='baz.txt', dst='baz_link.txt')

def test():
    assert os.path.islink('./foo_link.txt')
    assert os.path.islink('./baz_link.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    write(root / "shared" / "foo.txt", "foo")
    write(root / "shared" / "baz.txt", "baz")
    write(
        root / "rel" / "link_relative.pyt",
        """\
import os
import sys
import canary

canary.directives.link(src='../shared/foo.txt', dst='foo_link.txt')
canary.directives.link(src='../shared/baz.txt', dst='baz_link.txt')

def test():
    assert os.path.islink('./foo_link.txt')
    assert os.path.islink('./baz_link.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    run_specs(root, expected_returncode=0)


def test_vvt_link_rename_directive(tmp_path):
    root = tmp_path / "vvt-link"
    root.mkdir()

    write(root / "shared" / "foo.txt", "foo")
    write(root / "shared" / "baz.txt", "baz")
    write(
        root / "rel" / "a.vvt",
        """\
# VVT: link (rename) : ../shared/foo.txt,foo_link.txt
# VVT: link (rename) : ../shared/baz.txt,baz_link.txt
import os
import sys

def test():
    assert os.path.islink('./foo_link.txt')
    assert os.path.islink('./baz_link.txt')

if __name__ == '__main__':
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        try:
            canary.config.pluginmanager.ensure_loaded("canary_vvtest")
        except Exception as e:
            pytest.skip(f"canary_vvtest not available: {e}")

        workspace, specs = create_workspace_and_collect(root)
        session = workspace.run(specs, only="all")
        if session.returncode != 0:
            dump_outputs(root)
        assert session.returncode == 0


def test_link_when_directive(tmp_path):
    root = tmp_path / "link-when"
    root.mkdir()

    generator = data_dir() / "generators" / "link_when.pyt"
    assert generator.exists(), generator

    workspace, session = run_specs(
        root, scanpaths={str(generator.parent): [generator.name]}, expected_returncode=0
    )

    cases = {
        "link_when.a=link_when_1.b=1": ["link_when_1.txt"],
        "link_when.a=link_when_1.b=2": ["link_when_1-b2.txt"],
        "link_when.a=link_when_2.b=1": ["link_when_2.txt"],
        "link_when.a=link_when_2.b=2": ["link_when_2-b2.txt"],
    }

    for name, expected in cases.items():
        job = find_job_by_name(workspace, name)
        assert txtfiles(job.workspace.dir) == expected

def test_generation_only_directives(tmp_path):
    """Cover directives whose primary effects are on generated specs."""
    root = tmp_path / "generation-only"
    root.mkdir()

    write(root / "input.dat", "input")
    write(root / "preload.sh", "echo preload")
    write(
        root / "meta.pyt",
        """\
import sys
import canary

canary.directives.owners("alice", "bob")
canary.directives.owner("carol")
canary.directives.exclusive()
canary.directives.cpus(2)
canary.directives.gpus(0)
canary.directives.nodes(1)
canary.directives.timeout("2s")
canary.directives.set_attribute(priority="high", answer=42)
canary.directives.artifact("success.txt", save_on="success")
canary.directives.artifact("failure.txt", save_on="failure")
canary.directives.sources("input.dat")
canary.directives.preload("preload.sh")
canary.directives.load_module("fake-module", use="/tmp/canary-modulefiles")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace, specs = create_workspace_and_collect(root)

    assert len(specs) == 1
    spec = specs[0]

    assert spec.owners == ["alice", "bob", "carol"]
    assert spec.exclusive is True
    assert spec.meta_parameters["cpus"] == 2
    assert spec.meta_parameters["gpus"] == 0
    assert spec.meta_parameters["nodes"] == 1
    assert spec.timeout == 2.0
    assert spec.attributes["priority"] == "high"
    assert spec.attributes["answer"] == 42
    assert spec.preload == "preload.sh"
    assert spec.modules == ["fake-module"]
    assert spec.environment["MODULEPATH"].split(":")[0] == "/tmp/canary-modulefiles"

    artifacts = {(a.pattern, a.when) for a in spec.artifacts}
    assert ("success.txt", "on_success") in artifacts
    assert ("failure.txt", "on_failure") in artifacts

    source_assets = [(a.action, a.src.name, a.dst) for a in spec.assets]
    assert ("none", "input.dat", None) in source_assets


def test_parameterize_modes_centered_and_random(tmp_path):
    """Cover non-default parameterize modes."""
    root = tmp_path / "parameterize-modes"
    root.mkdir()

    write(
        root / "centered.pyt",
        """\
import sys
import canary
from _canary import enums

canary.directives.parameterize(
    "x,y",
    [(0, 1, 1), (10, 2, 1)],
    type=enums.centered_parameter_space,
)

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "randomized.pyt",
        """\
import sys
import canary
from _canary import enums

canary.directives.parameterize(
    "r,s",
    [(0.0, 1.0), (10.0, 20.0)],
    type=enums.random_parameter_space,
    samples=3,
    random_seed=99,
)

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        _, specs = create_workspace_and_collect(root)

    centered = [s for s in specs if s.family == "centered"]
    randomized = [s for s in specs if s.family == "randomized"]

    assert len(centered) == 5
    assert {tuple(s.parameters[k] for k in ("x", "y")) for s in centered} == {
        (0, 10),
        (-1, 10),
        (1, 10),
        (0, 8),
        (0, 12),
    }

    assert len(randomized) == 3
    for spec in randomized:
        assert 0.0 <= spec.parameters["r"] <= 1.0
        assert 10.0 <= spec.parameters["s"] <= 20.0


def test_runtime_source_attribute_and_artifact_directives(tmp_path):
    """Cover source(), set_attribute(), and artifact() during execution."""
    root = tmp_path / "runtime-metadata"
    root.mkdir()

    env_file = root / "env.sh"
    write(
        env_file,
        """\
export CANARY_DIRECTIVE_SOURCE_VALUE=from_rcfile
""",
    )

    write(
        root / "runtime_meta.pyt",
        f"""\
import os
import sys
import canary

canary.directives.source({str(env_file)!r})
canary.directives.set_attribute(kind="runtime-meta", enabled=True)
canary.directives.artifact("kept.txt", save_on="success")

def test():
    self = canary.get_instance()
    assert os.environ["CANARY_DIRECTIVE_SOURCE_VALUE"] == "from_rcfile"
    assert self.attributes["kind"] == "runtime-meta"
    assert self.attributes["enabled"] is True
    with open("kept.txt", "w") as fh:
        fh.write("artifact")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, session = run_specs(root, expected_returncode=0)
    assert session.returncode == 0

    job = next(job for job in workspace.load_jobs() if job.name == "runtime_meta")
    assert "kept.txt" in job.get_artifacts()


def test_conditional_copy_link_and_sources_directives(tmp_path):
    """Expand asset coverage: conditional copy/link plus sources(action=none)."""
    root = tmp_path / "conditional-assets"
    root.mkdir()

    write(root / "spam.txt", "spam")
    write(root / "eggs.txt", "eggs")
    write(root / "shared.txt", "shared")
    write(root / "declared-source.txt", "declared")

    write(
        root / "assets.pyt",
        """\
import os
import sys
import canary

canary.directives.parameterize("breakfast", ("spam", "eggs"))
canary.directives.copy("spam.txt", when={"parameters": "breakfast=spam"})
canary.directives.copy("eggs.txt", when={"parameters": "breakfast=eggs"})
canary.directives.link(src="shared.txt", dst="shared-link.txt")
canary.directives.sources("declared-source.txt")

def test():
    self = canary.get_instance()

    if self.parameters.breakfast == "spam":
        assert os.path.exists("spam.txt")
        assert not os.path.exists("eggs.txt")
    elif self.parameters.breakfast == "eggs":
        assert os.path.exists("eggs.txt")
        assert not os.path.exists("spam.txt")
    else:
        raise AssertionError(self.parameters.breakfast)

    assert os.path.islink("shared-link.txt")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, session = run_specs(root, expected_returncode=0)
    assert session.returncode == 0

    specs = workspace.db.load_specs()
    spec = next(s for s in specs if s.family == "assets" and s.parameters["breakfast"] == "spam")
    none_assets = [a for a in spec.assets if a.action == "none"]
    assert len(none_assets) == 1
    assert none_assets[0].src.name == "declared-source.txt"


def test_depends_on_dict_forms_and_expected_dependency_results(tmp_path):
    """Expand depends_on coverage for dict form, expects, and result gating."""
    root = tmp_path / "depends-dict"
    root.mkdir()

    write(
        root / "provider.pyt",
        """\
import sys
import canary

def test():
    with open("provided.txt", "w") as fh:
        fh.write("ok")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "consumer_always.pyt",
        """\
import os
import sys
import canary

canary.directives.depends_on({"job": "provider", "when": "always", "expects": 1})

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    dep = self.dependencies[0]
    assert os.path.exists(os.path.join(dep.working_directory, "provided.txt"))

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "expected_diff.pyt",
        """\
import sys
import canary

def test():
    raise canary.TestDiffed()

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "consumer_diff.pyt",
        """\
import sys
import canary

canary.directives.depends_on({"job": "expected_diff", "when": "DIFFED", "expects": 1})

def test():
    self = canary.get_instance()
    assert len(self.dependencies) == 1
    assert self.dependencies[0].status.outcome.name == "DIFFED"

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, session = run_specs(root, expected_returncode=2)

    jobs = {job.name: job for job in workspace.load_jobs()}
    assert jobs["consumer_always"].status.is_success()
    assert jobs["consumer_diff"].status.is_success()


def test_enable_false_masks_spec(tmp_path):
    root = tmp_path / "enable-false"
    root.mkdir()

    write(
        root / "disabled.pyt",
        """\
import sys
import canary

canary.directives.enable(False)

def test():
    raise AssertionError("should never run")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        _, specs = create_workspace_and_collect(root)

    assert len(specs) == 1
    assert specs[0].mask
    assert "enable=False" in (specs[0].mask.reason or "")


def test_resource_directives_with_conditions(tmp_path):
    """Cover conditional resource directives without requiring actual GPUs."""
    root = tmp_path / "conditional-resources"
    root.mkdir()

    write(
        root / "resources.pyt",
        """\
import sys
import canary

canary.directives.parameterize("mode", ("small", "large"))
canary.directives.cpus(1, when={"parameters": "mode=small"})
canary.directives.cpus(3, when={"parameters": "mode=large"})
canary.directives.nodes(1)
canary.directives.gpus(0)

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        _, specs = create_workspace_and_collect(root)

    by_mode = {spec.parameters["mode"]: spec for spec in specs}
    assert by_mode["small"].meta_parameters["cpus"] == 1
    assert by_mode["large"].meta_parameters["cpus"] == 3
    assert by_mode["small"].meta_parameters["nodes"] == 1
    assert by_mode["large"].meta_parameters["nodes"] == 1
    assert by_mode["small"].meta_parameters["gpus"] == 0
    assert by_mode["large"].meta_parameters["gpus"] == 0


def test_xfail_specific_code(tmp_path):
    root = tmp_path / "xfail-code"
    root.mkdir()

    write(
        root / "xfail_code.pyt",
        """\
import sys
import canary

canary.directives.xfail(code=7)

def test():
    return 7

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, session = run_specs(root, expected_returncode=0)
    assert session.returncode == 0

    job = next(job for job in workspace.load_jobs() if job.name == "xfail_code")
    assert job.status.outcome.name == "XFAIL"
