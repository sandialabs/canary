from _nvtest.finder import Finder
from _nvtest.util.filesystem import working_dir


def test_backward_names(tmpdir):
    workdir = tmpdir.strpath
    with working_dir(workdir):
        with open("a.pyt", "w") as fh:
            fh.write("import nvtest\nnvtest.directives.keywords('a', 'b', 'c', 'd', 'e')")
    finder = Finder()
    finder.add(workdir)
    assert len(finder.roots) == 1
    assert workdir in finder.roots
    finder.prepare()
    files = finder.discover()
    [case] = finder.lock_and_filter(files)
    case.work_tree = tmpdir.strpath
    assert case.exec_path == case.namespace
    assert case.exec_root == case.work_tree
