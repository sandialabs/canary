# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

from ..core.status import Outcome
from ..execution.testexec import ExecutionSpace
from ..session.workspace import Workspace

_TRACEBACK_START_RE = re.compile(r"^Traceback \(most recent call last\):\s*$", re.MULTILINE)
_FRAME_RE = re.compile(
    r'^  File "(?P<file>.+?)", line (?P<line>\d+), in (?P<function>[^\n]+)\n(?:    .*\n)?',
    re.MULTILINE,
)
_EXCEPTION_LINE_RE = re.compile(
    r"^(?P<type>[\w.]+(?:Error|Exception)|SystemExit|KeyboardInterrupt):\s*(?P<message>.*)$"
)
_COMMAND_NOT_FOUND_RE = re.compile(r"(?P<message>/(?:bin/)?sh:\s+.+?: command not found)")
_SEGFAULT_RE = re.compile(r"(?P<message>Segmentation fault(?: \([^\)]*\))?)")
_MPI_ABORT_RE = re.compile(r"(?P<message>(?:MPI_ABORT|mpirun noticed that process rank).*)")
_EXODIFF_RE = re.compile(
    r"(?P<message>(?:exodiff: Files are different|Error: exodiff found that .*|vdiff found .*failed))"
)
_SECONDARY_TRACEBACK_MARKERS = (
    "During handling of the above exception",
    "The above exception was the direct cause of the following exception",
)
_DEFAULT_LOG_CANDIDATES = ("execute.log", "canary-out.txt")
_DEFAULT_FRAME_FILTER = re.compile(r"(site-packages|src)")
_PATH_RE = re.compile(r"(?P<path>(?:/[\w.\-]+)+)")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
_FLOAT_RE = re.compile(r"(?<![\w.])-?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?")
_INT_RE = re.compile(r"(?<![\w.])-?\d+(?![\w.])")


@dataclasses.dataclass(slots=True)
class JobLogView:
    id: str
    name: str
    stdout: str
    workspace: ExecutionSpace


def job_log_candidates(job: Any) -> list[str]:
    names: list[str] = []
    for candidate in (getattr(job, "stdout", None), *list(_DEFAULT_LOG_CANDIDATES)):
        if candidate and candidate not in names:
            names.append(str(candidate))
    return names


def list_existing_logs(job: Any) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for name in job_log_candidates(job):
        path = job.workspace.joinpath(name)
        if not path.exists() or not path.is_file():
            continue
        stat = path.stat()
        logs.append({"name": name, "path": str(path), "size": stat.st_size, "mtime": stat.st_mtime})
    return logs


def tail_lines(path: Path, n: int | None = None) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if n is None or n <= 0 or len(lines) <= n:
        return lines
    return lines[-n:]


def collect_failure_groups(
    workspace: Workspace,
    rows: list[dict[str, Any]],
    *,
    group_by: str = "signature",
    frame_filter: str | None = None,
    include_pass_with_errors: bool = False,
    log_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    matcher = re.compile(frame_filter) if frame_filter else _DEFAULT_FRAME_FILTER
    groups: dict[str, dict[str, Any]] = {}

    for row in rows:
        outcome = row["status"].outcome.name
        is_pass = row["status"].category.value == "PASS"
        if outcome == Outcome.BLOCKED.name:
            blocker = blocked_root_signature(workspace, row)
            if blocker is not None:
                key = blocker["signature_normalized"]
                bucket = groups.setdefault(
                    key,
                    {
                        "signature": blocker["signature"],
                        "signature_normalized": blocker["signature_normalized"],
                        "exception_type": blocker.get("exception_type"),
                        "frame": blocker.get("frame"),
                        "count": 0,
                        "outcomes": {},
                        "jobs": [],
                        "secondary_errors": [],
                    },
                )
                bucket["count"] += 1
                bucket["outcomes"][outcome] = bucket["outcomes"].get(outcome, 0) + 1
                bucket["jobs"].append(
                    {
                        "id": row["id"],
                        "name": row["spec_name"],
                        "exec_dir": str(workspace.sessions_dir / row["session"] / row["workspace"]),
                        "log": "dependency",
                        "log_line": None,
                    }
                )
                continue
        if outcome not in {
            Outcome.FAILED.name,
            Outcome.ERROR.name,
            Outcome.BROKEN.name,
            Outcome.DIFFED.name,
        }:
            if not include_pass_with_errors or not is_pass:
                continue

        job = job_from_result_row(workspace, row)

        analysis = analyze_job_failure(
            workspace,
            job,
            row,
            frame_filter=matcher,
            log_names=log_names,
            include_pass_with_errors=include_pass_with_errors,
        )
        if analysis is None:
            continue

        key = group_key(analysis, group_by)
        bucket = groups.setdefault(
            key,
            {
                "signature": analysis["signature"],
                "signature_normalized": analysis["signature_normalized"],
                "exception_type": analysis.get("exception_type"),
                "frame": analysis.get("frame"),
                "count": 0,
                "outcomes": {},
                "jobs": [],
                "secondary_errors": [],
            },
        )
        bucket["count"] += 1
        bucket["outcomes"][outcome] = bucket["outcomes"].get(outcome, 0) + 1
        bucket["jobs"].append(
            {
                "id": job.id,
                "name": job.name,
                "exec_dir": str(job.workspace.dir),
                "log": analysis["log"],
                "log_line": analysis.get("log_line"),
            }
        )
        for secondary in analysis.get("secondary_errors", []):
            if secondary not in bucket["secondary_errors"]:
                bucket["secondary_errors"].append(secondary)

    return sorted(groups.values(), key=lambda item: (-item["count"], item["signature_normalized"]))


def failure_signature_for_row(
    workspace: Workspace,
    row: dict[str, Any],
    *,
    frame_filter: str | None = None,
    include_pass_with_errors: bool = False,
    log_names: list[str] | None = None,
) -> dict[str, Any] | None:
    matcher = re.compile(frame_filter) if frame_filter else _DEFAULT_FRAME_FILTER
    job = job_from_result_row(workspace, row)
    return analyze_job_failure(
        workspace,
        job,
        row,
        frame_filter=matcher,
        log_names=log_names,
        include_pass_with_errors=include_pass_with_errors,
    )


def blocked_root_signature(workspace: Workspace, row: dict[str, Any]) -> dict[str, Any] | None:
    graph = workspace.db.get_dependency_graph()
    upstream_ids = workspace.db.get_upstream_ids({row["id"]})
    if not upstream_ids:
        return None
    rows = {
        result["id"]: result for result in workspace.db.get_results(list(upstream_ids)).values()
    }
    failing = [result for result in rows.values() if result["status"].category.value == "FAIL"]
    if not failing:
        return None
    signatures = [failure_signature_for_row(workspace, result) for result in failing]
    signatures = [item for item in signatures if item is not None]
    if not signatures:
        return None
    counts: dict[str, tuple[int, dict[str, Any]]] = {}
    for signature in signatures:
        key = signature["signature_normalized"]
        count, _ = counts.get(key, (0, signature))
        counts[key] = (count + 1, signature)
    _, best = max(counts.values(), key=lambda item: item[0])
    return best


def job_from_result_row(workspace: Workspace, row: dict[str, Any]) -> Any:
    if not hasattr(workspace, "db") or not hasattr(workspace.db, "load_specs"):
        return workspace.find_job(row["id"])
    specs = workspace.db.load_specs([row["id"]])
    if not specs:
        return workspace.find_job(row["id"])
    spec = specs[0]
    return JobLogView(
        id=row["id"],
        name=row.get("spec_name") or spec.name,
        stdout=getattr(spec, "stdout", "canary-out.txt"),
        workspace=ExecutionSpace(
            root=workspace.sessions_dir / row["session"],
            path=Path(row["workspace"]),
            session=row["session"],
        ),
    )


def analyze_job_failure(
    workspace: Workspace,
    job: Any,
    row: dict[str, Any],
    *,
    frame_filter: re.Pattern[str],
    log_names: list[str] | None = None,
    include_pass_with_errors: bool = False,
) -> dict[str, Any] | None:
    candidates = log_names or job_log_candidates(job)
    for name in candidates:
        path = job.workspace.joinpath(name)
        if not path.exists() or not path.is_file():
            continue
        analysis = analyze_failure_log(
            workspace, path, frame_filter=frame_filter, status_reason=row["status"].reason or ""
        )
        if analysis is None:
            continue
        if row["status"].category.value == "PASS" and not include_pass_with_errors:
            continue
        analysis["log"] = name
        return analysis

    reason = row["status"].reason or row["status"].outcome.name
    if not reason:
        return None
    return {
        "signature": reason,
        "signature_normalized": normalize_signature(reason, workspace),
        "exception_type": row["status"].outcome.name,
        "frame": None,
        "secondary_errors": [],
        "log": getattr(job, "stdout", "canary-out.txt"),
        "log_line": None,
    }


def analyze_failure_log(
    workspace: Workspace, path: Path, *, frame_filter: re.Pattern[str], status_reason: str
) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = parse_tracebacks(text)
    if blocks:
        primary, secondary = choose_primary_traceback(blocks)
        frame = pick_frame(primary["frames"], frame_filter, workspace)
        signature = primary["exception_line"]
        return {
            "signature": signature,
            "signature_normalized": normalize_signature(signature, workspace),
            "exception_type": primary.get("exception_type"),
            "frame": frame,
            "secondary_errors": [block["exception_line"] for block in secondary],
            "log_line": primary["line"],
        }

    for pattern, exception_type in (
        (_COMMAND_NOT_FOUND_RE, "CommandError"),
        (_SEGFAULT_RE, "SignalError"),
        (_MPI_ABORT_RE, "MPIAbort"),
        (_EXODIFF_RE, "DiffError"),
    ):
        match = pattern.search(text)
        if match:
            message = match.group("message").strip()
            return {
                "signature": message,
                "signature_normalized": normalize_signature(message, workspace),
                "exception_type": exception_type,
                "frame": None,
                "secondary_errors": [],
                "log_line": text[: match.start()].count("\n") + 1,
            }

    if status_reason:
        return {
            "signature": status_reason,
            "signature_normalized": normalize_signature(status_reason, workspace),
            "exception_type": None,
            "frame": None,
            "secondary_errors": [],
            "log_line": None,
        }
    return None


def parse_tracebacks(text: str) -> list[dict[str, Any]]:
    matches = list(_TRACEBACK_START_RE.finditer(text))
    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.start() : end]
        lines = segment.splitlines()
        exception_line = ""
        exception_type = None
        for line in reversed(lines):
            stripped = line.strip()
            if not stripped:
                continue
            parsed = _EXCEPTION_LINE_RE.match(stripped)
            if parsed:
                exception_line = stripped
                exception_type = parsed.group("type")
                break
        if not exception_line:
            continue
        frames = []
        for frame_match in _FRAME_RE.finditer(segment):
            frames.append(
                {
                    "file": frame_match.group("file"),
                    "line": int(frame_match.group("line")),
                    "function": frame_match.group("function").strip(),
                }
            )
        blocks.append(
            {
                "exception_line": exception_line,
                "exception_type": exception_type,
                "frames": frames,
                "line": text[: match.start()].count("\n") + 1,
                "text": segment,
            }
        )
    return blocks


def choose_primary_traceback(
    blocks: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if len(blocks) == 1:
        return blocks[0], []
    for block in blocks:
        text = block["text"]
        if any(marker in text for marker in _SECONDARY_TRACEBACK_MARKERS):
            continue
        if block["exception_type"] == "UnboundLocalError":
            continue
        return block, [item for item in blocks if item is not block]
    return blocks[0], blocks[1:]


def pick_frame(
    frames: list[dict[str, Any]], frame_filter: re.Pattern[str], workspace: Workspace
) -> dict[str, Any] | None:
    for frame in reversed(frames):
        if frame_filter.search(frame["file"]):
            return normalize_frame(frame, workspace)
    if not frames:
        return None
    return normalize_frame(frames[-1], workspace)


def normalize_frame(frame: dict[str, Any], workspace: Workspace) -> dict[str, Any]:
    file = frame["file"]
    try:
        file = str(Path(file).resolve().relative_to(workspace.root.parent))
    except Exception:
        file = str(file)
    return {"file": file, "line": frame["line"], "function": frame["function"]}


def normalize_signature(signature: str, workspace: Workspace) -> str:
    normalized = signature
    for prefix in (str(workspace.root.parent), str(workspace.root)):
        normalized = normalized.replace(prefix, "<workspace>")
    normalized = _PATH_RE.sub("<path>", normalized)
    normalized = _HEX_RE.sub("<hex>", normalized)
    normalized = _FLOAT_RE.sub("<float>", normalized)
    normalized = _INT_RE.sub("<int>", normalized)
    return normalized.strip()


def group_key(analysis: dict[str, Any], group_by: str) -> str:
    if group_by == "signature":
        return analysis["signature_normalized"]
    if group_by == "exception":
        return analysis.get("exception_type") or analysis["signature_normalized"]
    if group_by == "frame":
        frame = analysis.get("frame")
        return (
            analysis["signature_normalized"]
            if frame is None
            else f"{frame['file']}:{frame['line']}"
        )
    if group_by == "reason":
        return analysis["signature"]
    if group_by == "file_path":
        frame = analysis.get("frame")
        return analysis["signature_normalized"] if frame is None else frame["file"]
    raise ValueError(f"Unsupported failure group key: {group_by}")
