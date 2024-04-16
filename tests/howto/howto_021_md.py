"""
How to generate markdown output
===============================

After completing a test session

.. code-block:: console

    $ nvtest -C TestResults report markdown create
    markdown report written to TestResults/Results.md

"""

import os

import _nvtest.util.filesystem as fs


def test_howto_html(tmpdir):
    import _nvtest.main

    with fs.working_dir(tmpdir.strpath, create=True):
        with open("test.pyt", "w") as fh:
            fh.write("import sys\ndef test():\n    return 0\ntest()")
        run = _nvtest.main.NVTestCommand("run")
        run("-w", ".")
        with fs.working_dir("TestResults"):
            report = _nvtest.main.NVTestCommand("report")
            report("markdown", "create")
        assert os.path.exists("TestResults/_reports/markdown")
        assert os.path.exists("TestResults/Results.md")
