# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Conformance: a caller with a POSIX shell and nothing else drives a real server.

The script runs under ``env -i PATH=/usr/bin:/bin``.  It first proves that neither the
``canary`` command nor the ``canary`` Python package is reachable, so it cannot pass by
accident, then submits a run, a status read, a rejected request and a cancel, using only
``inbox/``, ``requests/<id>/`` and ``server.json``.
"""

import subprocess
import sys
import time
from pathlib import Path

from _canary.service.fs.testing import server_dir
from _canary.service.fs.testing import start_server_process

CALLER = r"""
set -u
S=$1
fail() { echo "FAIL: $*" >&2; exit 1; }

command -v canary >/dev/null 2>&1 && fail "canary is on PATH"
for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import canary' 2>/dev/null; then
        fail "$py can import canary"
    fi
done

[ -f "$S/server.json" ] || fail "no server.json"
grep -q '"state": "running"' "$S/server.json" || fail "server.json: not running"

submit() {  # ID JSON: write inbox/ID.json.tmp, then rename it
    printf '%s\n' "$2" > "$S/inbox/$1.json.tmp" && mv "$S/inbox/$1.json.tmp" "$S/inbox/$1.json"
}
wait_for() {  # FILE PATTERN: until FILE exists and contains PATTERN
    n=0
    until [ -f "$1" ] && grep -q "$2" "$1"; do
        n=$((n + 1)); [ "$n" -gt 600 ] && fail "timed out waiting for $2 in $1"
        sleep 0.2
    done
}
result() { wait_for "$S/requests/$1/result.json" '"state"'; cat "$S/requests/$1/result.json"; }

submit sh-run '{"version": 1, "path": "/canary/run", "request": {"pathspec": ["ok"]}}'
r=$(result sh-run)
echo "$r" | grep -q '"state": "done"' || fail "run: $r"
echo "$r" | grep -q '"exit_code": 0' || fail "run exit code: $r"
grep -q "1 pass" "$S/requests/sh-run/stdout" || fail "run output"

submit sh-status '{"path": "/canary/status"}'
r=$(result sh-status)
echo "$r" | grep -q '"state": "done"' || fail "status: $r"
echo "$r" | grep -q '"name": "ok"' || fail "status data: $r"

submit sh-bad '{"path": "/canary/no-such-route"}'
r=$(result sh-bad)
echo "$r" | grep -q '"status_code": 404' || fail "unknown route: $r"
echo "$r" | grep -q '"state": "rejected"' || fail "unknown route state: $r"

submit sh-slow '{"path": "/canary/run", "request": {"pathspec": ["slow"]}}'
wait_for "$S/requests/sh-slow/status.json" '"state": "running"'
touch "$S/requests/sh-slow/cancel"
r=$(result sh-slow)
echo "$r" | grep -q '"state": "cancelled"' || fail "cancel: $r"
echo "$r" | grep -q '"status_code": 499' || fail "cancel status code: $r"

echo CONFORMS
"""

#: What a request may change, under the server directory.
PUBLIC = ("inbox", "requests/sh-")
#: The server's own files there.
PRIVATE = ("server.json", "server.lock", "queue", "accepting")


def test_a_posix_shell_caller_needs_nothing_else(root, tmp_path_factory):
    workspace = root.parent
    script = tmp_path_factory.mktemp("caller") / "caller.sh"
    script.write_text(CALLER)
    srv = start_server_process(workspace)
    sdir = server_dir(root)
    marker = time.time()
    time.sleep(0.05)
    try:
        proc = subprocess.run(
            ["env", "-i", "PATH=/usr/bin:/bin", "sh", str(script), str(sdir)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        stopped = subprocess.run(
            [sys.executable, "-m", "canary", "server", "stop"], cwd=workspace, capture_output=True
        )
        srv.wait(30)
    assert proc.returncode == 0 and "CONFORMS" in proc.stdout, proc.stdout + proc.stderr
    assert stopped.returncode == 0

    # find -newer: everything the four requests changed under the server directory
    changed = [
        p.relative_to(sdir).as_posix()
        for p in Path(sdir).rglob("*")
        if p.is_file() and p.stat().st_mtime > marker
    ]
    assert changed, "the sweep found nothing"
    stray = [p for p in changed if not p.startswith(PUBLIC + PRIVATE)]
    assert stray == []
    assert not list((sdir / "inbox").iterdir())
