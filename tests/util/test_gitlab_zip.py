# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import zipfile

from _canary.util import gitlab


def make_zip_with_traversal(zip_path):
    with zipfile.ZipFile(zip_path, "w") as z:
        # Add a safe file
        z.writestr("safe.txt", "safe content")
        # Add a traversal file
        z.writestr("../evil.txt", "evil content")


def test_zip_slip_extraction(tmp_path):
    # Create a zip with traversal
    zip_path = tmp_path / "test.zip"
    make_zip_with_traversal(str(zip_path))

    # Patch urlopen to return the zip bytes
    class DummyResponse:
        def read(self):
            with open(zip_path, "rb") as f:
                return f.read()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    # Monkeypatch urlopen in gitlab module
    import _canary.util.gitlab as gitlab_mod

    gitlab_mod.urlopen = lambda req: DummyResponse()
    # Call get_job_artifacts, which will extract the zip
    outdir = tmp_path / "out"
    os.makedirs(outdir, exist_ok=True)
    files = gitlab.get_job_artifacts("http://dummy", "proj", "jobid", dest=str(outdir))
    # Check if evil.txt was written outside outdir
    evil_path = tmp_path.parent / "evil.txt"
    assert not evil_path.exists(), "Zip Slip: evil.txt should NOT be extracted outside target dir"
    # For now, this will fail until extraction is hardened
