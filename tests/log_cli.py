# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from _canary.cli.log import display_file


def test_display_file_tolerates_non_utf8_bytes(tmp_path: Path, capsys) -> None:
    f = tmp_path / "bad.log"
    f.write_bytes(b"ok\n\xff\xfe\n")

    display_file(f)

    out = capsys.readouterr().out
    assert "bad.log:" in out
    assert "ok" in out
