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
        default=None, description="Filter to these specific spec IDs"
    )


class QueryJobRequest(BaseModel):
    """Request for /canary/query/job: one job's result in a session."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="Job ID to query")
    session_id: str = Field(default="latest", description="Session name, or 'latest'")


class QuerySessionRequest(BaseModel):
    """Request for /canary/query/session: a session's outcome counts (and its jobs)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default="latest", description="Session name, or 'latest'")
    expand_jobs: bool = Field(default=False, description="Include every job's result")


class QuerySessionsRequest(BaseModel):
    """Request for /canary/query/sessions: every session's name, oldest first."""

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


class QueryDBRequest(BaseModel):
    """Request for /canary/query/db: one read-only SQL ``SELECT``."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(..., description="A single SELECT statement")


# ==============================================================================
# Envelope and result
# ==============================================================================


class Envelope(BaseModel):
    """What a caller submits: the route, its body, and where to run it."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
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
