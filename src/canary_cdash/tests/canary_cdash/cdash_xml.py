# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import importlib.resources
import os
import subprocess
import sys
import xml.dom.minidom as dom
import zlib
from base64 import b64decode

import pytest

import _canary.config
import canary
from _canary.util.filesystem import working_dir


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.Config()
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)


def test_report_cdash(tmpdir):
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("init", ".")
        run_canary(
            "selection", "create", "-r", os.path.join(root, "docs/examples/basic"), "default"
        )
        run_canary("run", "default")
        run_canary("report", "cdash", "create")
        assert os.path.exists("TestResults/CDASH")


def test_report_cdash_missing_log_payload_is_valid_cdash_base64(tmpdir):
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("init", ".")
        run_canary(
            "selection", "create", "-r", os.path.join(root, "docs/examples/basic"), "default"
        )
        run_canary("run", "default")

        # Remove one stdout file so CDash must serialize the fallback "Log not found" payload.
        workspace = canary.Workspace.load()
        jobs = workspace.load_jobs()
        assert jobs, "expected jobs to exist after run"
        session = jobs[0].workspace.session
        stdout_file = jobs[0].workspace.joinpath(jobs[0].stdout)
        assert os.path.exists(stdout_file), "expected a stdout file for the regression case"
        os.remove(stdout_file)

        run_canary("report", "cdash", "create")

        cdash_dir = os.path.join("TestResults", "CDASH")
        test_xml = sorted(
            os.path.join(cdash_dir, name)
            for name in os.listdir(cdash_dir)
            if name.startswith("Test")
        )[0]
        doc = dom.parse(test_xml)

        values = doc.getElementsByTagName("Value")
        payload = None
        for value in values:
            parent = value.parentNode
            if (
                value.getAttribute("encoding") == "base64"
                and value.getAttribute("compression") == "gzip"
                and parent is not None
                and parent.nodeName == "Measurement"
            ):
                payload = "".join(
                    node.data for node in value.childNodes if node.nodeType == node.TEXT_NODE
                )
                break

        assert payload is not None
        decoded = cdash_decode(payload)
        assert decoded == "Log not found"


def test_report_cdash_skipped_log_payload_is_valid_cdash_base64(tmpdir):
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("init", ".")
        run_canary(
            "selection", "create", "-r", os.path.join(root, "docs/examples/basic"), "default"
        )
        run_canary("run", "default")

        workspace = canary.Workspace.load()
        jobs = workspace.load_jobs()
        assert jobs, "expected jobs to exist after run"

        job = jobs[0]
        job.set_status(outcome="SKIPPED", reason="Synthetic skip for CDash payload test")
        job.save()
        workspace.db.put_results(job)

        run_canary("report", "cdash", "create")

        cdash_dir = os.path.join("TestResults", "CDASH")
        test_xml = sorted(
            os.path.join(cdash_dir, name)
            for name in os.listdir(cdash_dir)
            if name.startswith("Test")
        )[0]
        doc = dom.parse(test_xml)

        payload = None
        for test in doc.getElementsByTagName("Test"):
            names = test.getElementsByTagName("Name")
            if not names:
                continue
            if names[0].firstChild is None or names[0].firstChild.nodeValue != job.display_name():
                continue
            for value in test.getElementsByTagName("Value"):
                parent = value.parentNode
                if (
                    value.getAttribute("encoding") == "base64"
                    and value.getAttribute("compression") == "gzip"
                    and parent is not None
                    and parent.nodeName == "Measurement"
                ):
                    payload = "".join(
                        node.data for node in value.childNodes if node.nodeType == node.TEXT_NODE
                    )
                    break
            if payload is not None:
                break

        assert payload is not None
        decoded = cdash_decode(payload)
        assert decoded == "Test skipped.  Reason: Synthetic skip for CDash payload test"


def test_report_cdash_all_log_payloads_are_zlib(tmpdir):
    """CDash decodes <Measurement> payloads with PHP's gzuncompress (zlib), and drops the
    entire Test.xml if any one payload fails.  A gzip container (1f8b) is not accepted."""
    with working_dir(tmpdir.strpath):
        root = str(importlib.resources.files("canary"))
        run_canary("init", ".")
        run_canary(
            "selection", "create", "-r", os.path.join(root, "docs/examples/basic"), "default"
        )
        run_canary("run", "default")
        run_canary("report", "cdash", "create")

        cdash_dir = os.path.join("TestResults", "CDASH")
        files = [os.path.join(cdash_dir, f) for f in os.listdir(cdash_dir) if f.startswith("Test")]
        assert files
        n = 0
        for file in files:
            doc = dom.parse(file)
            for measurement in doc.getElementsByTagName("Measurement"):
                value = measurement.getElementsByTagName("Value")[0]
                payload = "".join(
                    node.data for node in value.childNodes if node.nodeType == node.TEXT_NODE
                )
                raw = b64decode(payload.strip())
                assert raw[:2] != b"\x1f\x8b", "gzip container is not accepted by CDash"
                zlib.decompress(raw)
                n += 1
        assert n > 0


def cdash_decode(payload: str) -> str:
    """Decode a <Measurement> payload the same way CDash does (base64 + gzuncompress)."""
    return zlib.decompress(b64decode(payload.strip())).decode("utf-8")


def run_canary(command, *args, cwd=None):
    cmd = [sys.executable, "-m", "canary", "-d", "-r", "cpus:6", "-r", "gpus:0"]
    if cwd:
        cmd.extend(["-C", cwd])
    cmd.append(command)
    cmd.extend(args)
    subprocess.run(cmd)
