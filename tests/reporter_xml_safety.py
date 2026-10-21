# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Reporters must produce well-formed XML no matter what tests print."""

import xml.dom.minidom as xdom

import pytest

from _canary.reporters.junit import JunitReporter
from _canary.reporters.junit import JunitReportRequest
from _canary.session.workspace import Workspace
from _canary.util import xmlsafe
from _canary.util.filesystem import working_dir

HOSTILE = "end ]]> of cdata\x00 nul \x07 bell \x1b[31mred\x1b[0m \x0b vt \x1b]8;;http://x\x07link"


def test_xml_safe_strips_invalid_characters():
    out = xmlsafe.xml_safe(HOSTILE)
    assert "\x00" not in out and "\x07" not in out and "\x0b" not in out
    assert "\x1b" not in out  # ANSI removed
    assert "red" in out and "]]>" in out


def test_cdata_nodes_roundtrip_cdata_terminator():
    doc = xdom.Document()
    root = doc.createElement("r")
    doc.appendChild(root)
    for node in xmlsafe.cdata_nodes(doc, "a]]>b]]>]]>c"):
        root.appendChild(node)
    parsed = xdom.parseString(doc.toxml())
    assert parsed.documentElement is not None
    text = "".join(getattr(n, "data", "") for n in parsed.documentElement.childNodes)
    assert text == "a]]>b]]>]]>c"


def test_xml_safe_truncates_large_text():
    out = xmlsafe.xml_safe("x" * 10_000, max_length=1000)
    assert len(out) <= 1000
    assert "characters truncated" in out


@pytest.fixture(scope="module")
def failing_workspace(tmp_path_factory):
    from _canary import config

    root = tmp_path_factory.mktemp("xml-safety")
    with working_dir(root):
        (root / "bad.pyt").write_text(
            "import sys\n"
            "if __name__ == '__main__':\n"
            f"    sys.stdout.write({HOSTILE!r})\n"
            "    sys.exit(1)\n"
        )
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        with config.override():
            setattr(config.options, "report", None)
            workspace.run(specs, only="all")
    return root, workspace


def test_junit_report_with_hostile_output_is_well_formed(failing_workspace):
    root, workspace = failing_workspace
    output = root / "junit.xml"
    JunitReporter().write(
        JunitReportRequest(workspace=workspace, jobs=workspace.load_jobs(), output=output)
    )
    doc = xdom.parse(str(output))  # previously: ValueError or "not well-formed"
    out = "".join(
        getattr(n, "data", "")
        for el in doc.getElementsByTagName("system-out")
        for n in el.childNodes
    )
    assert "end ]]> of cdata" in out


def test_cdash_xml_with_hostile_output_is_well_formed(failing_workspace, tmp_path):
    import glob

    from canary_cdash.xmlreporter import CDashXMLReporter

    root, workspace = failing_workspace
    dest = tmp_path / "CDASH"
    with working_dir(root):
        reporter = CDashXMLReporter(dest=str(dest))
        for job in workspace.load_jobs():
            job.measurements.data["command_line"] = "cmd --opt ']]>' \x00 \x1b[1m"
            job.status.set(outcome="FAILED", reason="bad \x1b[1mreason\x1b[0m \x00")
            reporter.data.add_job(job)
        # Previously: ValueError (']]>' in CDATA) or a file CDash rejects.
        reporter.create(buildname="b\x00uild", site="s\x07ite")
    files = glob.glob(str(dest / "*.xml"))
    assert files
    for file in files:
        xdom.parse(file)
