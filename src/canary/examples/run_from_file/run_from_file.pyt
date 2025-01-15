import json

import _canary.util.filesystem as fs


def test_run_from_file(tmpdir):
    from _canary.main import CanaryCommand

    with fs.working_dir(tmpdir.strpath, create=True):
        fs.touchp("tests/regression/2D/test_1.pyt")
        fs.touchp("tests/regression/2D/test_2.pyt")
        fs.touchp("tests/verification/2D/test_1.pyt")
        fs.touchp("tests/verification/2D/test_2.pyt")
        fs.touchp("tests/verification/3D/test_1.pyt")
        fs.touchp("tests/verification/3D/test_2.pyt")
        fs.touchp("tests/prototype/a/test_1.pyt")
        fs.touchp("tests/prototype/a/test_2.pyt")
        fs.touchp("tests/prototype/b/test_1.pyt")
        fs.touchp("tests/prototype/b/test_2.pyt")
        data = {
            "root": "tests",
            "paths": [
                "regression/2D/test_1.pyt",
                "verification/3D/test_2.pyt",
                "prototype/b/test_1.pyt",
            ],
        }
        with open("file.json", "w") as fh:
            json.dump({"testpaths": [data]}, fh, indent=2)
        command = CanaryCommand("run")
        command("file.json")
