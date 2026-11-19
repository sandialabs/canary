# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""--banner/--no-banner before the subcommand wins over the subcommand's default."""

import subprocess
import sys

PASSING = (
    'import sys\ndef test():\n    return 0\nif __name__ == "__main__":\n    sys.exit(test())\n'
)


def _banner_shown(cwd, *args) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "canary", *args], cwd=cwd, capture_output=True, text=True
    )
    return "version:" in proc.stdout + proc.stderr


def test_global_banner_flag_overrides_the_subcommand_default(tmp_path):
    (tmp_path / "ok.pyt").write_text(PASSING)
    assert _banner_shown(tmp_path, "run", "--only", "all", ".")  # run defaults to a banner
    assert not _banner_shown(tmp_path, "--no-banner", "run", "--only", "all", ".")
    assert not _banner_shown(tmp_path, "info")  # other commands default to none
    assert _banner_shown(tmp_path, "--banner", "info")
