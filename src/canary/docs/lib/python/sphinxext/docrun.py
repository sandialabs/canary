# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Sphinx ``doc-run`` directive.

This extension is inspired by ``sphinxcontrib.programoutput`` by Sebastian
Wiesner, which provided directives for executing commands while building Sphinx
documentation and embedding their output as literal blocks. This implementation
keeps that general idea, but is a Canary-maintained refactor with a
GitLab-CI-like script model, JSON cache files, before/after script support,
explicit display controls, temporary execution directories, and modern Python
internals.

Template Variables
------------------
Commands in before_script, script, and after_script support template variable
expansion using Python's string.Template syntax. The following variables are
available:

- ${doc_source_dir}: Directory containing the current RST file being processed
- ${doc_name}: Name of the current document (without .rst extension)

"""

import dataclasses
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from importlib import resources
from pathlib import Path
from string import Template
from typing import Any
from typing import Iterable
from typing import Literal

import yaml
from docutils import nodes
from docutils.parsers import rst
from docutils.parsers.rst.directives import flag
from docutils.parsers.rst.directives import unchanged
from docutils.statemachine import StringList
from sphinx.util import logging as sphinx_logging

__version__ = "0.17"

CACHE_SCHEMA = 3
EXECUTION_MODEL = "temporary-root-script-list-v1"

COPY_EXAMPLES_SETUP = "copy-examples"
LINK_EXAMPLES_SETUP = "link-examples"
BUILTIN_COMMANDS = {COPY_EXAMPLES_SETUP, LINK_EXAMPLES_SETUP}
DOCRUN_SKIP_ENV = "DOCRUN_SKIP_EXECUTION"
DOCRUN_SKIP_MESSAGE_ENV = "CANARY_DOCS_SKIP_DOCRUN_MESSAGE"
DEFAULT_SKIP_MESSAGE = "COMMAND NOT RUN (doc-run execution disabled)"

logger = sphinx_logging.getLogger("sphinxext.docrun")

DisplayToken = Literal["command", "stdout", "stderr", "none"]
DISPLAY_TOKENS: set[str] = {"command", "stdout", "stderr", "none"}

CopyMode = Literal["copy", "link"]
EllipsisSpec = tuple[int | None, int | None] | None
EllipsisSpecs = EllipsisSpec | list[EllipsisSpec]


class doc_run_output(nodes.Element):
    """Placeholder node replaced by script output during ``doctree-read``."""


def canary_examples_dir() -> Path:
    """Return the installed path to Canary's bundled examples directory.

    The ``doc-run`` directive recognizes built-in script commands
    ``copy-examples`` and ``link-examples``. Both use this path as the source
    for the examples tree.
    """
    return Path(str(resources.files("canary").joinpath("docs/examples")))


def _container_wrapper(
    directive: rst.Directive, child_node: nodes.Node, caption: str
) -> nodes.container:
    """Wrap a directive node in a Sphinx literal-block container with a caption."""
    container_node = nodes.container("", literal_block=True, classes=["literal-block-wrapper"])
    parsed = nodes.Element()
    directive.state.nested_parse(StringList([caption], source=""), directive.content_offset, parsed)

    if isinstance(parsed[0], nodes.system_message):  # pragma: no cover
        raise ValueError("Invalid caption: %s" % parsed[0].astext())

    assert isinstance(parsed[0], nodes.Element)
    caption_node = nodes.caption(parsed[0].rawsource, "", *parsed[0].children)
    caption_node.source = child_node.source
    caption_node.line = child_node.line

    container_node += caption_node
    container_node += child_node
    return container_node


def _parse_ellipsis_slice(value: Any) -> EllipsisSpec:
    """Parse one ellipsis specification.

    Accepted forms:

    - ``None`` / ``null`` / ``~`` / ``none``: no ellipsis
    - ``4``: replace lines ``[4:]`` with ``...``
    - ``"4,10"``: replace lines ``[4:10]`` with ``...``
    - ``[4, 10]``: replace lines ``[4:10]`` with ``...``
    - ``[4]``: replace lines ``[4:]`` with ``...``
    """
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        if text.lower() in {"", "none", "null", "~"}:
            return None

        parts = [int(v.strip()) for v in text.split(",")]
        if len(parts) > 2:
            raise ValueError("too many ellipsis slice parts")
        padded: list[int | None] = [*parts, None, None]
        return padded[0], padded[1]

    if isinstance(value, int):
        return value, None

    if isinstance(value, list):
        if len(value) > 2:
            raise ValueError("too many ellipsis slice parts")
        parts: list[int | None] = []
        for item in value:
            if item is None:
                parts.append(None)
            elif isinstance(item, int):
                parts.append(item)
            else:
                raise ValueError(f"invalid ellipsis slice value: {item!r}")
        padded = [*parts, None, None]
        return padded[0], padded[1]

    raise ValueError(f"invalid ellipsis value: {value!r}")


def _ellipsis(value: str) -> EllipsisSpecs:
    """Parse the ``ellipsis`` option.

    The option may be a single legacy-style ellipsis slice or a YAML list of
    per-script ellipsis slices.
    """
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ValueError(f"ellipsis option must be valid YAML: {exc}") from exc

    # YAML list means one ellipsis spec per script command.
    if isinstance(parsed, list):
        return [_parse_ellipsis_slice(item) for item in parsed]

    # Scalar means apply the same ellipsis spec to every script command.
    return _parse_ellipsis_slice(parsed)


def _display(value: str) -> tuple[DisplayToken, ...]:
    """Parse and validate the comma-separated ``display`` option."""
    tokens = tuple(t.strip().lower() for t in value.split(",") if t.strip())
    if not tokens:
        raise ValueError("display must contain at least one token")

    unknown = [t for t in tokens if t not in DISPLAY_TOKENS]
    if unknown:
        choices = ", ".join(sorted(DISPLAY_TOKENS))
        raise ValueError(f"unknown display token(s): {', '.join(unknown)}; choose from {choices}")

    if "none" in tokens and len(tokens) > 1:
        raise ValueError("display token 'none' must be used alone")

    return tokens  # type: ignore[return-value]


def _env_json(value: str) -> dict[str, str]:
    """Parse an ``env`` option JSON object into an environment mapping."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"env must be a JSON object: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("env must be a JSON object")

    env: dict[str, str] = {}
    for key, val in parsed.items():
        if not isinstance(key, str):
            raise ValueError("env variable names must be strings")
        if not isinstance(val, str):
            raise ValueError(f"env[{key!r}] must be a string")
        env[key] = val

    return env


def _script_list(value: str) -> list[str]:
    """Parse a YAML scalar or YAML list into a list of commands.

    Examples accepted by this parser include both inline YAML:

    ``[copy-examples, canary run foo.pyt]``

    and block YAML:

    ``- copy-examples``
    ``- canary run foo.pyt``
    """
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ValueError(f"script option must be valid YAML: {exc}") from exc

    if parsed is None:
        return []

    if isinstance(parsed, str):
        return [parsed]

    if isinstance(parsed, list):
        commands: list[str] = []
        for i, item in enumerate(parsed):
            if not isinstance(item, str):
                raise ValueError(f"script item {i} must be a string")
            if item.strip():
                commands.append(item)
        return commands

    raise ValueError("script option must be a string or YAML list of strings")


def _returncode_list(value: str) -> list[int]:
    """Parse a YAML list of integers for the returncode option.

    Examples accepted by this parser include both inline YAML:

    ``[0, 1, 2]``

    and block YAML:

    ``- 0``
    ``- 1``
    ``- 2``
    """
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise ValueError(f"returncode option must be valid YAML: {exc}") from exc

    if parsed is None:
        raise ValueError("returncode option cannot be null")

    if isinstance(parsed, list):
        if not all(isinstance(item, int) and item >= 0 for item in parsed):
            raise ValueError("returncode option must be a list of non-negative integers")
        return parsed

    if isinstance(parsed, int):
        raise ValueError("returncode option must be a list of integers, got a single integer")

    raise ValueError(f"returncode option must be a list of integers, got {type(parsed).__name__}")


def _copy_mode(value: str) -> CopyMode:
    """Parse the ``copy-mode`` option for the ``canary-example`` shortcut."""
    mode = value.strip().lower()
    if mode not in {"copy", "link"}:
        raise ValueError("copy-mode must be one of: copy, link")
    return mode  # type: ignore[return-value]


@dataclasses.dataclass(frozen=True, slots=True)
class Invocation:
    """Execution-defining inputs for one ``doc-run`` invocation."""

    before_script: list[str]
    script: list[str]
    after_script: list[str]
    extraargs: str
    env: dict[str, str]
    cwd: str | None
    shell: bool
    mergestderr: bool
    hash_salt: str

    def effective_command(self, command: str) -> str:
        """Return a script command with global ``extraargs`` appended.

        ``extraargs`` is retained for compatibility with the previous
        single-command interface. In the script-list model it is appended to
        each main ``script`` command, not to ``before_script`` or
        ``after_script`` commands.
        """
        return f"{command} {self.extraargs}".strip() if self.extraargs else command

    def effective_script(self) -> list[str]:
        """Return the list of primary script commands as actually executed."""
        return [self.effective_command(command) for command in self.script]

    def hash_inputs(self) -> dict[str, Any]:
        """Return exactly the directive inputs that define cache identity."""
        return {
            "cache_schema": CACHE_SCHEMA,
            "execution_model": EXECUTION_MODEL,
            "before_script": self.before_script,
            "script": self.script,
            "after_script": self.after_script,
            "extraargs": self.extraargs,
            "effective_script": self.effective_script(),
            "env": self.env,
            "cwd": self.cwd,
            "cwd_root": "<temporary>",
            "shell": self.shell,
            "mergestderr": self.mergestderr,
            "hash_salt": self.hash_salt,
        }

    @property
    def content_hash(self) -> str:
        """Return the stable cache hash for this invocation."""
        payload = json.dumps(self.hash_inputs(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:15]


@dataclasses.dataclass(frozen=True, slots=True)
class ProcessRecord:
    """Captured result for one command in before/script/after phases."""

    command: str | None
    stdout: str
    stderr: str
    returncode: int | None

    @classmethod
    def skipped(cls, command: str | None) -> "ProcessRecord":
        """Create a record for a command that was intentionally not run."""
        return cls(command=command, stdout="", stderr="", returncode=None)

    @classmethod
    def exception(cls, command: str, exc: BaseException) -> "ProcessRecord":
        """Create a record for a command that failed before producing a process."""
        return cls(command=command, stdout="", stderr=repr(exc), returncode=None)

    @classmethod
    def from_completed_process(
        cls, command: str, cp: subprocess.CompletedProcess[str], *, stderr_is_separate: bool = True
    ) -> "ProcessRecord":
        """Create a record from a ``subprocess.run`` result."""
        return cls(
            command=command,
            stdout=cp.stdout or "",
            stderr=(cp.stderr or "") if stderr_is_separate else "",
            returncode=cp.returncode,
        )

    def to_json(self) -> dict[str, Any]:
        """Convert this process record into the cache-file schema."""
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "ProcessRecord | None":
        """Reconstruct a process record from the cache-file schema."""
        if data is None:
            return None

        return cls(
            command=data.get("command"),
            stdout=data.get("stdout") or "",
            stderr=data.get("stderr") or "",
            returncode=data.get("returncode"),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """Complete cached execution record for one directive invocation."""

    hash: str
    options: dict[str, Any]
    before_script: list[ProcessRecord]
    script: list[ProcessRecord]
    after_script: list[ProcessRecord]

    @property
    def stdout(self) -> str:
        """Return combined stdout from the primary script commands."""
        return "\n".join(record.stdout.rstrip() for record in self.script if record.stdout).rstrip()

    @property
    def stderr(self) -> str:
        """Return combined stderr from the primary script commands."""
        return "\n".join(record.stderr.rstrip() for record in self.script if record.stderr).rstrip()

    @property
    def returncode(self) -> int | None:
        """Return the last primary script return code, if one exists."""
        for record in reversed(self.script):
            if record.returncode is not None:
                return record.returncode
        return None

    def to_json(self) -> dict[str, Any]:
        """Convert this execution record into JSON cache-file data."""
        return {
            "cache_schema": CACHE_SCHEMA,
            "execution_model": EXECUTION_MODEL,
            "hash": self.hash,
            "options": self.options,
            "before_script": [record.to_json() for record in self.before_script],
            "script": [record.to_json() for record in self.script],
            "after_script": [record.to_json() for record in self.after_script],
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ExecutionRecord":
        """Reconstruct an execution record from JSON cache-file data."""
        return cls(
            hash=data["hash"],
            options=dict(data.get("options") or {}),
            before_script=[
                record
                for item in data.get("before_script", [])
                if (record := ProcessRecord.from_json(item)) is not None
            ],
            script=[
                record
                for item in data.get("script", [])
                if (record := ProcessRecord.from_json(item)) is not None
            ],
            after_script=[
                record
                for item in data.get("after_script", [])
                if (record := ProcessRecord.from_json(item)) is not None
            ],
        )


def _run_args(command: str, *, shell: bool) -> str | list[str]:
    """Return the argument object to pass to ``subprocess.run``."""
    if shell:
        return command
    return shlex.split(command)


def _merged_env(extra_env: dict[str, str]) -> dict[str, str]:
    """Merge directive environment variables on top of ``os.environ``."""
    env = dict(os.environ)
    env.update(extra_env)
    return env


def _run_process(
    command: str, *, cwd: str | Path, shell: bool, env: dict[str, str], mergestderr: bool = False
) -> ProcessRecord:
    """Run a process in ``cwd`` and return a captured process record."""
    try:
        cp = subprocess.run(
            _run_args(command, shell=shell),
            shell=shell,
            cwd=os.fspath(cwd),
            env=_merged_env(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if mergestderr else subprocess.PIPE,
            text=True,
        )  # nosec B602
    except BaseException as exc:
        return ProcessRecord.exception(command, exc)

    return ProcessRecord.from_completed_process(command, cp, stderr_is_separate=not mergestderr)


def _copy_examples(temp_root: Path) -> ProcessRecord:
    """Copy Canary's bundled examples into the temporary root as ``examples``."""
    command = COPY_EXAMPLES_SETUP
    source = canary_examples_dir()
    target = temp_root / "examples"

    try:
        if not source.exists():
            raise FileNotFoundError(source)
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)

        shutil.copytree(source, target, symlinks=True)

        # Remove .canary and TestResults if they exist in the copied examples
        for dir_name in [".canary", "TestResults"]:
            dir_path = target / dir_name
            if dir_path.exists() or dir_path.is_symlink():
                if dir_path.is_symlink():
                    dir_path.unlink()
                else:
                    shutil.rmtree(dir_path)
    except BaseException as exc:
        return ProcessRecord.exception(command, exc)

    return ProcessRecord(command=command, stdout=f"{source} -> {target}\n", stderr="", returncode=0)


def _link_examples(temp_root: Path) -> ProcessRecord:
    """Symlink Canary's bundled examples into the temporary root as ``examples``."""
    command = LINK_EXAMPLES_SETUP
    source = canary_examples_dir()
    target = temp_root / "examples"

    try:
        if not source.exists():
            raise FileNotFoundError(source)
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        target.symlink_to(source, target_is_directory=True)

        # Remove .canary and TestResults if they exist in the linked examples
        for dir_name in [".canary", "TestResults"]:
            dir_path = target / dir_name
            if dir_path.exists() or dir_path.is_symlink():
                if dir_path.is_symlink():
                    dir_path.unlink()
                else:
                    shutil.rmtree(dir_path)
    except BaseException as exc:
        return ProcessRecord.exception(command, exc)

    return ProcessRecord(command=command, stdout=f"{source} -> {target}\n", stderr="", returncode=0)


def _run_command_or_builtin(
    command: str, *, temp_root: Path, cwd: Path, shell: bool, env: dict[str, str], mergestderr: bool
) -> ProcessRecord:
    """Run a command or one of the built-in examples setup actions."""
    stripped = command.strip()

    if stripped == COPY_EXAMPLES_SETUP:
        return _copy_examples(temp_root)

    if stripped == LINK_EXAMPLES_SETUP:
        return _link_examples(temp_root)

    return _run_process(command, cwd=cwd, shell=shell, env=env, mergestderr=mergestderr)


def _resolve_cwd(temp_root: Path, cwd_option: str | None) -> Path:
    """Resolve ``:cwd:`` relative to the temporary root and require it to exist.

    A leading slash is interpreted relative to the temporary execution root, not
    relative to the filesystem root or the documentation source root. For
    example, ``:cwd: /examples`` resolves to ``<temp-root>/examples``.
    """
    raw = "." if cwd_option is None else cwd_option.strip()

    if raw in ("", ".", "/"):
        relative = Path(".")
    else:
        normalized = raw.replace("\\", "/")
        while normalized.startswith("/"):
            normalized = normalized[1:]
        relative = Path(normalized)

    if relative.is_absolute():
        raise ValueError(f"cwd must be relative to the temporary run directory: {cwd_option!r}")

    if any(part == ".." for part in relative.parts):
        raise ValueError(f"cwd escapes temporary run directory: {cwd_option!r}")

    candidate = temp_root / relative

    if not candidate.is_dir():
        raise FileNotFoundError(
            f"cwd {cwd_option!r} does not exist inside temporary run directory {temp_root}"
        )

    return candidate


def _phase_failed(records: list[ProcessRecord], *, expected_returncode: int) -> bool:
    """Return True if any command record failed relative to ``expected_returncode``."""
    for record in records:
        if record.returncode != expected_returncode:
            return True
    return False


def _options_record(
    invocation: Invocation,
    *,
    returncode: list[int],
    anyreturncode: bool,
    execution_root: str,
    execution_cwd: str | None,
) -> dict[str, Any]:
    """Return all hashed and non-hashed options written to the cache file."""
    return {
        "cache_schema": CACHE_SCHEMA,
        "execution_model": EXECUTION_MODEL,
        "before_script": invocation.before_script,
        "script": invocation.script,
        "effective_script": invocation.effective_script(),
        "after_script": invocation.after_script,
        "extraargs": invocation.extraargs,
        "env": invocation.env,
        "cwd": invocation.cwd,
        "cwd_root": "<temporary>",
        "execution_root": execution_root,
        "execution_cwd": execution_cwd,
        "shell": invocation.shell,
        "mergestderr": invocation.mergestderr,
        "hash_salt": invocation.hash_salt,
        "returncode": returncode,
        "anyreturncode": anyreturncode,
    }


def _execute(
    invocation: Invocation, *, returncode: list[int], anyreturncode: bool
) -> ExecutionRecord:
    """Execute an invocation in a fresh temporary directory."""
    with tempfile.TemporaryDirectory(prefix="sphinx-docrun-") as tmp:
        return _execute_in_directory(
            invocation, temp_root=Path(tmp), returncode=returncode, anyreturncode=anyreturncode
        )


def _is_builtin_command(command: str) -> bool:
    """Return True if command is a built-in doc-run command."""
    return command.strip() in BUILTIN_COMMANDS


def _run_builtin_command(command: str, *, temp_root: Path) -> ProcessRecord:
    """Run a built-in doc-run command."""
    stripped = command.strip()

    if stripped == COPY_EXAMPLES_SETUP:
        return _copy_examples(temp_root)

    if stripped == LINK_EXAMPLES_SETUP:
        return _link_examples(temp_root)

    return ProcessRecord.exception(command, ValueError(f"unknown built-in command: {command!r}"))


def _execute_in_directory(
    invocation: Invocation, *, temp_root: Path, returncode: list[int], anyreturncode: bool
) -> ExecutionRecord:
    """Execute before/script/after phases inside one temporary directory.

    Built-in commands operate on the temporary root. All ordinary subprocess
    commands honor ``invocation.cwd``. The cwd is resolved lazily so a
    before_script command such as ``copy-examples`` can create ``/examples``
    before ordinary commands run there.
    """
    before_records: list[ProcessRecord] = []
    script_records: list[ProcessRecord] = []
    after_records: list[ProcessRecord] = []
    resolved_cwd: Path | None = None

    def get_cwd() -> Path:
        """Resolve and cache the directive cwd relative to the temp root."""
        nonlocal resolved_cwd
        if resolved_cwd is None:
            resolved_cwd = _resolve_cwd(temp_root, invocation.cwd)
        return resolved_cwd

    def run_one(command: str, *, phase: str, mergestderr: bool = False) -> ProcessRecord:
        """Run one built-in or subprocess command for a phase."""
        if _is_builtin_command(command):
            return _run_builtin_command(command, temp_root=temp_root)

        try:
            cwd = get_cwd()
        except BaseException as exc:
            return ProcessRecord.exception(command, exc)

        return _run_process(
            command, cwd=cwd, shell=invocation.shell, env=invocation.env, mergestderr=mergestderr
        )

    try:
        for command in invocation.before_script:
            record = run_one(command, phase="before_script", mergestderr=False)
            before_records.append(record)
            if record.returncode != 0:
                break

        if not _phase_failed(before_records, expected_returncode=0):
            for command in invocation.effective_script():
                record = run_one(command, phase="script", mergestderr=invocation.mergestderr)
                script_records.append(record)

                if not anyreturncode and record.returncode != returncode:
                    break

    finally:
        for command in invocation.after_script:
            record = run_one(command, phase="after_script", mergestderr=False)
            after_records.append(record)

    return ExecutionRecord(
        hash=invocation.content_hash,
        options=_options_record(
            invocation,
            returncode=returncode,
            anyreturncode=anyreturncode,
            execution_root=os.fspath(temp_root),
            execution_cwd=None if resolved_cwd is None else os.fspath(resolved_cwd),
        ),
        before_script=before_records,
        script=script_records,
        after_script=after_records,
    )


def _read_cache(path: Path) -> ExecutionRecord:
    """Read an execution record from a JSON cache file."""
    with path.open() as fh:
        return ExecutionRecord.from_json(json.load(fh))


def _write_cache(path: Path, record: ExecutionRecord) -> None:
    """Atomically write an execution record to a JSON cache file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w") as fh:
        json.dump(record.to_json(), fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _cache_file(srcdir: str | os.PathLike[str], docname: str, content_hash: str) -> Path:
    """Return the cache path for a document-local invocation hash."""
    return Path(srcdir) / ".cache" / docname / f"{content_hash}.json"


def _record_is_usable(
    record: ExecutionRecord,
    *,
    expected_returncode: int | list[int],
    anyreturncode: bool,
    expected_script_count: int,
) -> bool:
    """Return True if a cached record can be reused for the current directive."""
    if record.options.get("cache_schema") != CACHE_SCHEMA:
        return False

    if record.options.get("execution_model") != EXECUTION_MODEL:
        return False

    for before in record.before_script:
        if before.returncode != 0:
            return False

    if len(record.script) != expected_script_count:
        return False

    for i, script in enumerate(record.script):
        if script.returncode is None:
            return False
        if not anyreturncode:
            if isinstance(expected_returncode, list):
                if script.returncode != expected_returncode[i]:
                    return False
            else:
                if script.returncode != expected_returncode:
                    return False

    return True


class DocRunDirective(rst.Directive):
    """Directive implementation for ``.. doc-run::``."""

    has_content = False
    final_argument_whitespace = False
    required_arguments = 0

    option_spec = {
        "before_script": _script_list,
        "script": _script_list,
        "after_script": _script_list,
        "skip": flag,
        "env": _env_json,
        "mergestderr": flag,
        "display": _display,
        "hash_salt": unchanged,
        "shell": flag,
        "nocache": flag,
        "anyreturncode": flag,
        "ellipsis": _ellipsis,
        "extraargs": unchanged,
        "returncode": _returncode_list,
        "cwd": unchanged,
        "caption": unchanged,
        "name": unchanged,
    }  # nosec B604

    def run(self) -> list[nodes.Node]:
        """Parse directive options and create a placeholder node."""
        sphinx_env = self.state.document.settings.env

        if "script" not in self.options:
            raise self.error("doc-run requires the :script: option")

        script = self.options["script"]
        if not script:
            raise self.error("doc-run requires at least one script command")

        invocation = Invocation(
            before_script=list(self.options.get("before_script") or []),
            script=list(script),
            after_script=list(self.options.get("after_script") or []),
            extraargs=self.options.get("extraargs", ""),
            env=dict(self.options.get("env") or {}),
            cwd=self.options.get("cwd"),
            shell="shell" in self.options,
            mergestderr="mergestderr" in self.options,
            hash_salt=self.options.get("hash_salt", ""),
        )

        docname = sphinx_env.docname
        content_hash = invocation.content_hash
        _note_hash_seen(self.state.document, docname=docname, content_hash=content_hash)

        node = doc_run_output()
        node.line = self.lineno
        node["docname"] = docname
        node["hash"] = content_hash
        node["before_script"] = invocation.before_script
        node["script"] = invocation.script
        node["effective_script"] = invocation.effective_script()
        node["after_script"] = invocation.after_script
        node["extraargs"] = invocation.extraargs
        node["env"] = invocation.env
        node["cwd"] = invocation.cwd
        node["use_shell"] = invocation.shell
        node["mergestderr"] = invocation.mergestderr
        node["hash_salt"] = invocation.hash_salt
        node["display"] = self.options.get("display", ("command", "stdout"))
        node["skip"] = "skip" in self.options
        node["nocache"] = "nocache" in self.options or os.getenv("CANARY_DOCS_NOCACHE") is not None
        node["anyreturncode"] = "anyreturncode" in self.options
        node["returncode"] = self.options.get("returncode", [0] * len(script))

        if "ellipsis" in self.options:
            ellipsis = self.options["ellipsis"]
            if isinstance(ellipsis, list) and len(ellipsis) != len(script):
                raise self.error(
                    "ellipsis list length must match script length "
                    f"({len(ellipsis)} != {len(script)})"
                )
            node["ellipsis"] = ellipsis

        if "returncode" in self.options:
            returncode = self.options["returncode"]
            if isinstance(returncode, list):
                if len(returncode) != len(script):
                    raise self.error(
                        "returncode list length must match script length "
                        f"({len(returncode)} != {len(script)})"
                    )
                for i, code in enumerate(returncode):
                    if not isinstance(code, int):
                        raise self.error(
                            f"returncode[{i}] must be an integer, got {type(code).__name__}"
                        )
            else:
                raise self.error(
                    f"returncode must be a list of integers, got {type(returncode).__name__}"
                )
            node["returncode"] = returncode

        output_node: nodes.Node = node
        if "caption" in self.options:
            caption = self.options["caption"] or invocation.effective_script()[0]
            output_node = _container_wrapper(self, node, caption)

        self.add_name(output_node)
        return [output_node]


class CanaryExampleDirective(DocRunDirective):
    """Shortcut directive for running commands in Canary's examples directory."""

    option_spec = dict(DocRunDirective.option_spec)
    option_spec.pop("before_script", None)
    option_spec.pop("cwd", None)
    option_spec["copy-mode"] = _copy_mode

    def run(self) -> list[nodes.Node]:
        """Inject examples setup/cwd defaults and delegate to ``doc-run``."""
        copy_mode: CopyMode = self.options.pop("copy-mode", "copy")

        if copy_mode == "link":
            self.options["before_script"] = [LINK_EXAMPLES_SETUP]
        else:
            self.options["before_script"] = [COPY_EXAMPLES_SETUP]

        self.options["cwd"] = "/examples"

        return super().run()


class DocRunCache:
    """In-memory cache wrapper backed by per-invocation JSON files."""

    def __init__(self) -> None:
        """Initialize the per-build in-memory cache."""
        self.records: dict[tuple[str, str], ExecutionRecord] = {}

    def get(
        self,
        *,
        invocation: Invocation,
        cache_file: Path,
        nocache: bool,
        returncode: list[int],
        anyreturncode: bool,
    ) -> ExecutionRecord:
        """Return a usable cached record or execute and cache a fresh record."""
        key = (str(cache_file), invocation.content_hash)

        if not nocache and key in self.records:
            record = self.records[key]
            if _record_is_usable(
                record,
                expected_returncode=returncode,
                anyreturncode=anyreturncode,
                expected_script_count=len(invocation.script),
            ):
                return record

        if not nocache and cache_file.exists():
            try:
                record = _read_cache(cache_file)
            except Exception:
                logger.warning("Ignoring unreadable doc-run cache file %s", cache_file)
            else:
                if _record_is_usable(
                    record,
                    expected_returncode=returncode,
                    anyreturncode=anyreturncode,
                    expected_script_count=len(invocation.script),
                ):
                    self.records[key] = record
                    return record

                logger.debug(
                    "Ignoring unsuccessful doc-run cache file %s; executing fresh", cache_file
                )

        record = _execute(invocation, returncode=returncode, anyreturncode=anyreturncode)
        _write_cache(cache_file, record)
        self.records[key] = record
        return record


def _prompt_template_as_unicode(app: Any) -> str:
    """Return the prompt template as text, decoding bytes if necessary."""
    tmpl = app.config.docrun_prompt_template
    if isinstance(tmpl, bytes):
        for enc in "utf-8", sys.getfilesystemencoding():
            try:
                tmpl = tmpl.decode(enc)
            except UnicodeError:  # pragma: no cover
                pass
            else:
                app.config.docrun_prompt_template = tmpl
                break
    return tmpl


def traverse(node: nodes.Node, arg: Any) -> Iterable[nodes.Node]:
    """Return matching descendants using the docutils/Sphinx-compatible API."""
    if hasattr(node, "findall"):
        return node.findall(arg)
    return node.traverse(arg)


def _apply_ellipsis(text: str, strip_lines: tuple[int | None, int | None] | None) -> str:
    """Replace a selected range of output lines with an ellipsis marker."""
    if strip_lines is None:
        return text.rstrip()

    start, stop = strip_lines
    lines = text.rstrip().splitlines()
    lines[start:stop] = ["..."]
    return "\n".join(lines)


def _ellipsis_for_index(value: EllipsisSpecs | None, index: int) -> EllipsisSpec:
    """Return the ellipsis spec to apply to one script command."""
    if value is None:
        return None
    if isinstance(value, list):
        return value[index]
    return value


def _literal(text: str, *, language: str = "console") -> nodes.literal_block:
    """Create a console literal block from text."""
    node = nodes.literal_block(text, text)
    node["language"] = language
    return node


def _render_nodes(app: Any, node: doc_run_output, record: ExecutionRecord) -> list[nodes.Node]:
    """Render the script transcript into one console block."""
    if tuple(node["display"]) == ("none",):
        return [nodes.meta()]

    parts: list[str] = []
    prompt_template = _prompt_template_as_unicode(app)
    ellipsis_specs = node.get("ellipsis")

    for i, script_record in enumerate(record.script):
        strip_lines = _ellipsis_for_index(ellipsis_specs, i)

        for token in node["display"]:
            if token == "command":
                command = script_record.command or ""
                text = prompt_template.format(
                    command=command, output="", returncode=script_record.returncode
                ).rstrip()
                if text:
                    parts.append(text)

            elif token == "stdout":
                text = _apply_ellipsis(script_record.stdout or "", strip_lines)
                if text:
                    parts.append(text)

            elif token == "stderr":
                text = _apply_ellipsis(script_record.stderr or "", strip_lines)
                if text:
                    parts.append(text)

            elif token == "none":
                return [nodes.meta()]

            else:  # pragma: no cover - validated by option parser
                raise ValueError(f"unknown display token {token!r}")

    if not parts:
        return [nodes.meta()]

    return [_literal("\n".join(parts))]


def _expand_template_variables(
    commands: list[str], *, doc_source_dir: str, doc_name: str
) -> list[str]:
    """Expand template variables in command strings.

    Supports the following variables:
    - ${doc_source_dir}: Directory containing the current RST file
    - ${doc_name}: Name of the current document (without extension)
    """
    # Ensure variables are strings
    doc_source_dir = str(doc_source_dir) if doc_source_dir is not None else ""
    doc_name = str(doc_name) if doc_name is not None else ""
    examples = canary_examples_dir()

    context = {"doc_source_dir": doc_source_dir, "doc_name": doc_name, "examples": examples}

    expanded_commands = []
    for command in commands:
        if not command:
            continue

        try:
            template = Template(command)
            expanded = template.safe_substitute(**context)
            expanded_commands.append(expanded)
        except Exception as exc:
            logger.warning("Failed to expand template variables in command %r: %s", command, exc)
            expanded_commands.append(command)

    return expanded_commands


def _make_invocation_from_node(node: doc_run_output) -> Invocation:
    """Reconstruct invocation identity from a placeholder node."""
    return Invocation(
        before_script=list(node.get("before_script") or []),
        script=list(node.get("script") or []),
        after_script=list(node.get("after_script") or []),
        extraargs=node.get("extraargs", ""),
        env=dict(node.get("env") or {}),
        cwd=node.get("cwd"),
        shell=bool(node["use_shell"]),
        mergestderr=bool(node["mergestderr"]),
        hash_salt=node.get("hash_salt", ""),
    )


def _failure_reason(node: doc_run_output, record: ExecutionRecord) -> str | None:
    """Return a build-failure explanation for an execution record, if any."""
    for before in record.before_script:
        if before.returncode != 0:
            return (
                f"before_script command {before.command!r} failed with return code "
                f"{before.returncode}"
            )

    for i, script in enumerate(record.script):
        command_rc = script.returncode

        if command_rc is None:
            return f"script command {script.command!r} was not run"

        if not node["anyreturncode"]:
            expected_rc = (
                node["returncode"][i]
                if isinstance(node["returncode"], list)
                else node["returncode"]
            )
            if command_rc != expected_rc:
                return (
                    f"script command {script.command!r} returned unexpected code "
                    f"{command_rc} != {expected_rc}"
                )

    return None


def _error_node(
    doctree: nodes.document, node: doc_run_output, message: str
) -> nodes.system_message:
    """Create a high-level system message node for command failures."""
    error_node = doctree.reporter.error(message, base_node=node)
    error_node["level"] = 6
    return error_node


def _note_hash_seen(document: nodes.document, *, docname: str, content_hash: str) -> None:
    """Warn when two directives in the same document parse share a cache hash.

    The tracking state is intentionally stored on the transient docutils
    document, not on the persistent Sphinx environment.  Sphinx may reuse the
    environment across incremental rebuilds, and storing this on ``env`` causes
    a single unchanged directive to look like a duplicate when a source file is
    rebuilt.
    """
    attr = "_docrun_seen_hashes"

    if not hasattr(document, attr):
        seen: set[str] = set()
        setattr(document, attr, seen)
    else:
        seen = getattr(document, attr)

    if content_hash in seen:
        logger.warning(
            "doc-run directives in %s produced identical cache hash %s; "
            "they will share one cache entry. If this is unintentional, review "
            "their execution options or add :hash_salt: to disambiguate.",
            docname,
            content_hash,
        )
    else:
        seen.add(content_hash)


def _truthy_env(name: str) -> bool:
    """Return True if environment variable ``name`` is set to a truthy value."""
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _skip_message(app: Any) -> str:
    """Return the message used when doc-run execution is disabled."""
    env_message = os.getenv(DOCRUN_SKIP_MESSAGE_ENV)
    if env_message:
        return env_message
    return str(getattr(app.config, "docrun_skip_message", DEFAULT_SKIP_MESSAGE))


def _skip_execution_enabled(app: Any, node: doc_run_output) -> bool:
    """Return True if this doc-run node should render without executing."""
    if bool(node.get("skip_execution", False)):
        return True
    if bool(getattr(app.config, "docrun_skip_execution", False)):
        return True
    return _truthy_env(DOCRUN_SKIP_ENV)


def _skipped_record(command: str, *, returncode: int, message: str) -> ProcessRecord:
    """Return a non-executed process record for one command.

    Both stdout and stderr are populated so ``display=stdout`` and
    ``display=stderr`` both make it obvious that the command was intentionally
    not run.
    """
    text = message.rstrip() + "\n"
    return ProcessRecord(command=command, stdout=text, stderr=text, returncode=returncode)


def _execute_skipped(
    invocation: Invocation, *, returncode: int | list[int], message: str
) -> ExecutionRecord:
    """Return a synthetic execution record without running any commands.

    This record is deliberately not cached by ``DocRunCache``. It is intended
    for restricted build environments where examples cannot be executed.
    """
    before_records = [
        _skipped_record(command, returncode=0, message=message)
        for command in invocation.before_script
    ]

    script_returncodes = (
        returncode if isinstance(returncode, list) else [returncode] * len(invocation.script)
    )
    script_records = [
        _skipped_record(command, returncode=script_returncodes[i], message=message)
        for i, command in enumerate(invocation.effective_script())
    ]

    after_records = [
        _skipped_record(command, returncode=0, message=message)
        for command in invocation.after_script
    ]

    return ExecutionRecord(
        hash=invocation.content_hash,
        options={
            **invocation.hash_inputs(),
            "execution_skipped": True,
            "skip_message": message,
            "returncode": returncode,
            "anyreturncode": True,
        },
        before_script=before_records,
        script=script_records,
        after_script=after_records,
    )


def run_doc_commands(app: Any, doctree: nodes.document) -> None:
    """Execute all ``doc-run`` placeholder nodes and replace them."""
    cache = app.env.docrun_cache

    for node in traverse(doctree, doc_run_output):
        assert isinstance(node, doc_run_output)

        # Get the source directory for the current document
        doc_source_dir = str(Path(app.env.srcdir) / app.env.docname)
        if not doc_source_dir.endswith(".rst"):
            doc_source_dir = doc_source_dir + ".rst"
        doc_source_dir = os.path.dirname(doc_source_dir)

        # Get document name without extension
        doc_name = os.path.splitext(app.env.docname)[0]

        # Expand template variables in all commands
        invocation = _make_invocation_from_node(node)
        expanded_invocation = Invocation(
            before_script=_expand_template_variables(
                invocation.before_script, doc_source_dir=doc_source_dir, doc_name=doc_name
            ),
            script=_expand_template_variables(
                invocation.script, doc_source_dir=doc_source_dir, doc_name=doc_name
            ),
            after_script=_expand_template_variables(
                invocation.after_script, doc_source_dir=doc_source_dir, doc_name=doc_name
            ),
            extraargs=invocation.extraargs,
            env=invocation.env,
            cwd=invocation.cwd,
            shell=invocation.shell,
            mergestderr=invocation.mergestderr,
            hash_salt=invocation.hash_salt,
        )

        cache_path = _cache_file(app.env.srcdir, node["docname"], node["hash"])

        try:
            if _skip_execution_enabled(app, node):
                record = _execute_skipped(
                    expanded_invocation, returncode=node["returncode"], message=_skip_message(app)
                )
            else:
                record = cache.get(
                    invocation=expanded_invocation,
                    cache_file=cache_path,
                    nocache=bool(node["nocache"]),
                    returncode=node["returncode"],
                    anyreturncode=bool(node["anyreturncode"]),
                )
        except Exception as exc:
            node.replace_self(_error_node(doctree, node, f"doc-run failed: {exc}"))
            continue

        if reason := _failure_reason(node, record):
            message = (
                f"{reason}; stdout={record.stdout!r}; stderr={record.stderr!r}; cache={cache_path}"
            )
            node.replace_self(_error_node(doctree, node, message))
            continue

        node.replace_self(_render_nodes(app, node, record))


def init_cache(app: Any) -> None:
    """Initialize the per-build doc-run cache on the Sphinx environment."""
    if not hasattr(app.env, "docrun_cache"):
        app.env.docrun_cache = DocRunCache()


def setup(app: Any) -> dict[str, bool]:
    """Register the Sphinx directives, config values, and build event hooks."""
    app.add_config_value("docrun_prompt_template", "$ {command}\n{output}", "env")
    app.add_config_value("docrun_skip_execution", False, "env")
    app.add_config_value("docrun_skip_message", DEFAULT_SKIP_MESSAGE, "env")
    app.add_directive("doc-run", DocRunDirective)
    app.add_directive("canary-example", CanaryExampleDirective)
    app.connect("builder-inited", init_cache)
    app.connect("doctree-read", run_doc_commands)
    return {"parallel_read_safe": True}
