# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Pydantic models for canary server request and response validation.

All endpoints use structured request schemas with Pydantic validation.
"""

from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from .argv import Dest

#: The choices of ``canary run --only``.
Only = Literal["all", "changed", "failed", "not_pass", "not_run"]

# ==============================================================================
# Work Endpoint Request Models (subprocess, via work lane)
# ==============================================================================


class RunRequest(BaseModel):
    """Request for /canary/run endpoint (subprocess, async)."""

    model_config = ConfigDict(extra="forbid")

    pathspec: Annotated[list[str], Dest("runpaths")] = Field(
        default_factory=list,
        description="Paths, spec ids or a selection tag (none: the workspace's tests)",
    )
    keyword: Annotated[str | None, Dest("keyword_exprs")] = Field(
        default=None, description="Keyword expression like 'fast and not slow'"
    )
    owner: Annotated[str | None, Dest("owners")] = Field(
        default=None, description="Filter by test owner"
    )
    parameter: Annotated[str | None, Dest("parameter_expr")] = Field(
        default=None, description="Parameter expression like 'cpus<8'"
    )
    regex: Annotated[str | None, Dest("regex_filter")] = Field(
        default=None, description="Regular expression match in test assets"
    )
    only: Annotated[Only | None, Dest("only")] = Field(
        default=None, description="Which tests to run (failed, not_pass, changed, etc.)"
    )
    on_options: Annotated[list[str], Dest("on_options")] = Field(
        default_factory=list, description="Generation options like ['dbg', 'opt']"
    )
    workers: Annotated[int | None, Dest("workers")] = Field(
        default=None, description="Number of parallel workers"
    )
    timeout: Annotated[str | None, Dest("timeout")] = Field(
        default=None, description="Timeout spec like 'session=10m' or 'test=5m'"
    )
    fail_fast: Annotated[bool, Dest("fail_fast")] = Field(
        default=False, description="Stop after first failure"
    )
    view: Annotated[str | None, Dest("view")] = Field(
        default=None, description="View spec like 'mode=symlink,only=failed'"
    )


# ==============================================================================
# Work Endpoint Request Models (worker child, via _canary.app)
#
# Fields are the application functions' parameters (friendly names allowed).
# Paths are relative to the request's cwd.
# ==============================================================================


class CollectRequest(BaseModel):
    """Request for /canary/collect: find and generate test cases under *roots*."""

    model_config = ConfigDict(extra="forbid")

    roots: list[str] = Field(..., description="Paths to search for tests", min_length=1)
    on_options: list[str] = Field(
        default_factory=list, description="Generation options like ['dbg', 'opt']"
    )


class SelectRequest(BaseModel):
    """Request for /canary/select: create, rename or delete the selection *tag*."""

    model_config = ConfigDict(extra="forbid")

    tag: str = Field(..., min_length=1, description="The selection to create, rename to, or delete")
    delete: bool = Field(default=False, description="Delete the selection")
    rename_from: str | None = Field(default=None, description="Rename this selection to tag")
    from_tag: str | None = Field(default=None, description="Select from this selection's tests")
    from_root: list[str] = Field(
        default_factory=list, description="Only tests whose files are under these paths"
    )
    keyword: str | None = Field(default=None, description="Keyword expression")
    owner: str | None = Field(default=None, description="Filter by test owner")
    parameter: str | None = Field(default=None, description="Parameter expression")
    regex: str | None = Field(default=None, description="Regular expression match in test files")

    @model_validator(mode="after")
    def _one_operation(self) -> "SelectRequest":
        filters = (
            self.from_tag,
            self.from_root,
            self.keyword,
            self.owner,
            self.parameter,
            self.regex,
        )
        if (self.delete or self.rename_from) and any(filters):
            raise ValueError("delete and rename_from take no selection filters")
        if self.delete and self.rename_from:
            raise ValueError("give delete or rename_from, not both")
        return self


class RebaselineRequest(BaseModel):
    """Request for /canary/rebaseline: accept the latest results of *targets* as baselines."""

    model_config = ConfigDict(extra="forbid")

    targets: list[str] = Field(
        ..., description="Job ids or names, or results directories", min_length=1
    )
    keyword: str | None = Field(default=None, description="Keyword expression to filter targets")


# ==============================================================================
# Read Endpoint Request Models (in-process, via read lane)
# ==============================================================================


class StatusRequest(BaseModel):
    """Request for /canary/status: the latest result of every job (or of *spec_ids*)."""

    model_config = ConfigDict(extra="forbid")

    spec_ids: list[str] | None = Field(
        default=None,
        min_length=1,
        description="Only these jobs (ID prefixes or names); omit the field for every job",
    )


#: The description of a route's trailing ``{path:path}``.
PATH_INTO = "In the route: keys into the document, by '/' (e.g. measurements/loss); none for all"


class QueryJobRequest(BaseModel):
    """Request for /canary/query/job/{job_id}[/{path}]: one run of a job, or part of it."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, description="In the route: job ID (a prefix) or name")
    path: str = Field(default="", description=PATH_INTO)
    session_id: str | None = Field(
        default=None,
        description="The job's run in this session (or 'latest'); default its latest run",
    )


class QueryJobLogRequest(BaseModel):
    """Request for /canary/query/job/{job_id}/log: what a run of a job printed."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, description="In the route: job ID (a prefix) or name")
    session_id: str | None = Field(
        default=None,
        description="The job's run in this session (or 'latest'); default its latest run",
    )
    stream: Literal["stdout", "stderr"] = Field(
        default="stdout", description="stdout (canary-out.txt; it holds stderr too unless split)"
    )
    tail: int | None = Field(default=None, ge=1, description="Only the last this many lines")


class QuerySessionRequest(BaseModel):
    """Request for /canary/query/session/{session_id}[/{path}]: a session, or part of it."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        ..., min_length=1, description="In the route: session name, or 'latest'"
    )
    path: str = Field(default="", description=PATH_INTO)


class QuerySessionsRequest(BaseModel):
    """Request for /canary/query/sessions: every session's summary, oldest first."""

    model_config = ConfigDict(extra="forbid")


class QueryJobsRequest(BaseModel):
    """Request for /canary/query/jobs: the latest result of every job."""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(
        default=None, description="Only jobs whose latest result is from this session"
    )


class QueryFailuresRequest(BaseModel):
    """Request for /canary/query/failures: jobs that failed or aborted in a session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="latest", description="Session name, or 'latest'")
    log_tail: int | None = Field(
        default=None, ge=1, description="Add each job's last this many lines of output (log_tail)"
    )


class LocationRequest(BaseModel):
    """Request for /canary/location/{job_id}: where a job's files are."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, description="In the route: job ID (a prefix) or name")


class QueryDBRequest(BaseModel):
    """Request for /canary/query/db: one read-only SQL ``SELECT``."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(..., description="A single SELECT statement; ? marks a parameter")
    params: list[str | int | float | bool | None] = Field(
        default_factory=list, description="The values of the statement's ? parameters, in order"
    )
    parse_json: bool = Field(
        default=False,
        description="Return JSON text columns (measurements, timekeeper, specs.data) as objects",
    )


class QueryDBSchemaRequest(BaseModel):
    """Request for /canary/query/db/schema[/{path}]: the database's tables and columns."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        default="", description=PATH_INTO.replace("measurements/loss", "results/columns")
    )


class QueryDBStatsRequest(BaseModel):
    """Request for /canary/query/db/stats (no fields)."""

    model_config = ConfigDict(extra="forbid")


class LearnRequest(BaseModel):
    """Request for /canary/learn/capabilities and /canary/learn/skills."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(
        default=".",
        description="Query path, as for canary learn: 'ext.pyt.parameters', "
        "'pyt.canary-pyt-authoring'; '.' for everything",
    )
    list_keys: bool = Field(default=False, description="The keys below topic, not its data")


# ==============================================================================
# Envelope and result
# ==============================================================================


class Envelope(BaseModel):
    """What a caller submits: the route, its body, and where to run it."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    method: Literal["GET", "POST", "PUT"] = Field(
        default="POST", description="GET only reads: a work route refuses it (405)"
    )
    path: str = Field(..., description="Endpoint route, e.g. '/canary/run'")
    request: dict[str, Any] = Field(default_factory=dict, description="The endpoint's body")
    cwd: str = Field(default=".", description="Working directory, relative to the anchor")
    env: dict[str, str] = Field(
        default_factory=dict, description="Variables set on top of the server's environment"
    )


State = Literal["done", "rejected", "cancelled", "failed"]


class Result(BaseModel):
    """A request's result document (``requests/<id>/result.json``), written once, last."""

    version: Literal[1] = 1
    id: str
    path: str
    status_code: int
    state: State
    data: Any = None
    error: str | None = None
    cwd: str
    user: str
    submitted: float
    started: float | None = None
    finished: float
