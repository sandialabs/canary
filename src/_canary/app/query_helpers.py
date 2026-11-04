# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from ..session.workspace import Workspace


def resolve_session_dir(workspace: Workspace, session: str) -> Path:
    """Resolve a session name, prefix, or ``latest`` to its directory path."""
    if session == "latest":
        latest = workspace.refs_dir / "latest"
        if not latest.exists():
            raise FileNotFoundError(latest)
        rel = latest.read_text().strip()
        return (workspace.refs_dir / rel).resolve()

    candidate = workspace.sessions_dir / session
    if candidate.is_dir():
        return candidate

    matches = sorted(p for p in workspace.sessions_dir.glob(f"{session}*") if p.is_dir())
    if not matches:
        raise ValueError(f"{session!r}: no matching session found")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches[:8])
        if len(matches) > 8:
            names += ", ..."
        raise ValueError(f"{session!r}: ambiguous session prefix; matches: {names}")
    return matches[0]
