# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from .claude import CLAUDE_GUIDANCE_PATH
from .claude import append_or_refresh_claude_guidance
from .claude import claude_bootstrap_files
from .common import can_refresh_managed_file
from .common import generic_bootstrap_files
from .opencode import opencode_bootstrap_files


def write_agent_bootstrap(
    target: str, *, brief: bool = False, force: bool = False, append: bool = False
) -> None:
    files = bootstrap_file_map(target, brief=brief)
    ensure_bootstrap_targets_available(files, force=force, append=append)

    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if target == "claude" and path == CLAUDE_GUIDANCE_PATH and append:
            append_or_refresh_claude_guidance(path, text)
        else:
            path.write_text(text, encoding="utf-8")


def bootstrap_file_map(target: str, *, brief: bool) -> dict[Path, str]:
    if target == "generic":
        return generic_bootstrap_files(brief=brief)
    if target == "opencode":
        return opencode_bootstrap_files(brief=brief)
    if target == "claude":
        return claude_bootstrap_files(brief=brief)
    raise ValueError(f"Unsupported agent bootstrap target: {target}")


def ensure_bootstrap_targets_available(
    files: dict[Path, str], *, force: bool, append: bool = False
) -> None:
    if CLAUDE_GUIDANCE_PATH in files and CLAUDE_GUIDANCE_PATH.exists() and not append and not force:
        raise FileExistsError(
            "CLAUDE.md exists. To overwrite it, re-run with --force. "
            "To append or refresh Canary guidance, re-run with --append."
        )

    conflicts = [
        path
        for path, text in files.items()
        if path != CLAUDE_GUIDANCE_PATH
        and path.exists()
        and not can_refresh_managed_file(path, text)
    ]
    if conflicts and not force:
        lines = ["Canary agent bootstrap would overwrite existing files:"]
        lines.extend(f"  {path}" for path in conflicts)
        lines.append("Re-run with --force to overwrite them.")
        raise FileExistsError("\n".join(lines))
