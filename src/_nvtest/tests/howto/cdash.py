"""
How to integrate with CDash
===========================

After completing a test session

.. code-block:: console

    $ cd TestResults
    $ nvtest report cdash create -p <PROJECT_NAME> -b <BUILD_NAME>
    $ nvtest report cdash post URL
"""

import os

import _nvtest.util.filesystem as fs


def test_howto_cdash(tmpdir):
    import _nvtest.main

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write("import sys\ndef test():\n    return 0\ntest()")
        run = _nvtest.main.NVTestCommand("run")
        run("-w", ".")
        with fs.working_dir("TestResults"):
            report = _nvtest.main.NVTestCommand("report")
            report(
                "cdash", "create", "--project=nvtest", "--build=SPAM", "--track=Nightly"
            )
        assert os.path.exists("TestResults/_reports/cdash/Test.xml")
        assert os.path.exists("TestResults/_reports/cdash/Notes.xml")
