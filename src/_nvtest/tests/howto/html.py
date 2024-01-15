"""
How to generate HTML output
===========================

After completing a test session

.. code-block:: console

    $ nvtest -C TestResults report html create
    HTML report written to TestResults/Results.html

The HTML report has the following form:

.. raw:: html

    <style>
    table{font-family:arial,sans-serif;border-collapse:collapse;}
    td, th {border: 1px solid #dddddd; text-align: left; padding: 8px; width=100%}
    tr:nth-child(even) {background-color: #dddddd;}
    </style>
    <div class="box">
    <h3>NVTest Summary</h3>
    <table>
    <tr><th>Site</th><th>Project</th><th>Not Run</th><th>Timeout</th><th>Fail</th><th>Diff</th><th>Pass</th><th>Total</th></tr>
    <tr><td><pre>site</pre></td><td> <pre> project </pre> </td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>N</td></tr>
    </table>
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
            report("html", "create")
        assert os.path.exists("TestResults/_reports/html")
        assert os.path.exists("TestResults/Results.html")
